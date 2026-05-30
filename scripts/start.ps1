<#
.SYNOPSIS
    Run Concierge natively -no Docker for app services.
    Docker is used only for infra: postgres, redis, minio, vault, pgadmin.

.DESCRIPTION
    Sequence:
      1.  Load .env into process environment
      2.  Docker check
      3.  Detect port 5432 conflict (native postgres -> use 5433 instead)
      4.  Start infra via Docker Compose (no build needed)
      5.  Wait for Vault, seed it via seed.sh
      6.  Patch Vault secrets: replace docker hostnames with 127.0.0.1
      7.  Override inter-service URLs in process env
      8.  Wait for Postgres, patch pg_hba.conf (trust), run Alembic migrations
      9.  Launch backend / model-server / guardrails / streamlit in separate windows
      10. Wait for backend /healthz, open browser

.EXAMPLE
    .\scripts\start.ps1
    Right-click -> "Run with PowerShell"
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

# ── Helpers ───────────────────────────────────────────────────────────────────

function Write-Step { param([string]$Msg) Write-Host ""; Write-Host "==> $Msg" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Msg) Write-Host "    OK  $Msg" -ForegroundColor Green }

function Abort {
    param([string]$Msg)
    Write-Host ""
    Write-Host "    ERR $Msg" -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

function Wait-Http {
    param([string]$Url, [int]$MaxSeconds = 60, [int]$Interval = 4)
    $elapsed = 0
    while ($elapsed -lt $MaxSeconds) {
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
            if ($r.StatusCode -eq 200) { return $true }
        } catch { }
        Start-Sleep -Seconds $Interval
        $elapsed += $Interval
        Write-Host "    ... ${elapsed}/${MaxSeconds}s"
    }
    return $false
}

function Import-DotEnv {
    param([string]$Path)
    foreach ($raw in Get-Content $Path) {
        $line = $raw.Trim()
        if (-not $line -or $line.StartsWith('#') -or $line -notmatch '=') { continue }
        $key, $val = $line.Split('=', 2)
        $val = $val.Trim().Trim('"').Trim("'")
        [System.Environment]::SetEnvironmentVariable($key.Trim(), $val, 'Process')
    }
}

function Update-VaultSecret {
    # Read a KV v2 secret, apply $Overrides hashtable, write it back.
    param([string]$SecretPath, [hashtable]$Overrides)
    $headers = @{ "X-Vault-Token" = $env:VAULT_TOKEN }
    $url = "http://localhost:8200/v1/secret/data/$SecretPath"
    $current = Invoke-RestMethod -Uri $url -Headers $headers -Method Get
    $data = $current.data.data
    foreach ($k in $Overrides.Keys) { $data.$k = $Overrides[$k] }
    $body = @{ data = $data } | ConvertTo-Json -Depth 10
    Invoke-RestMethod -Uri $url -Headers $headers -Method Post -Body $body -ContentType "application/json" | Out-Null
    Write-Ok "Patched $SecretPath"
}

function Open-ServiceWindow {
    param([string]$Title, [string]$WorkDir, [string]$Command)
    $script = "`$host.UI.RawUI.WindowTitle = '$Title'; Set-Location '$WorkDir'; $Command"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $script
    Write-Ok "Launched: $Title"
}

# ── 1. .env ───────────────────────────────────────────────────────────────────

Write-Step ".env check"
$EnvFile = Join-Path $ProjectRoot ".env"
if (-not (Test-Path $EnvFile)) {
    $example = Join-Path $ProjectRoot ".env.example"
    if (Test-Path $example) {
        Copy-Item $example $EnvFile
        Write-Warning "Copied .env.example -> .env  - fill in your secrets then re-run."
        Read-Host "Press Enter to close"; exit 1
    }
    Abort ".env not found and no .env.example to copy from."
}
Import-DotEnv $EnvFile
Write-Ok ".env loaded."

# ── 2. Docker check ───────────────────────────────────────────────────────────

Write-Step "Docker check"
docker info 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Abort "Docker is not running. Start Docker Desktop and re-run." }
Write-Ok "Docker is running."

# ── 3. Port 5432 conflict detection ───────────────────────────────────────────
#
#  If a native Windows PostgreSQL is already bound on 5432, Docker's port-forward
#  loses the race and psycopg2 hits the wrong server.  In that case, map the
#  Docker container to 5433 instead (docker-compose reads POSTGRES_HOST_PORT).

Write-Step "Checking for port 5432 conflicts..."
$port5432InUse = (netstat -ano 2>$null) -match '^\s+TCP\s+[\d.:]+:5432\s+[\d.:]+:0\s+LISTENING'
if ($port5432InUse) {
    $pgHostPort = 5433
    Write-Host "    Port 5432 is already in use (native PostgreSQL). Using 5433 instead." -ForegroundColor Yellow
} else {
    $pgHostPort = 5432
    Write-Ok "Port 5432 is free."
}
[System.Environment]::SetEnvironmentVariable('POSTGRES_HOST_PORT', "$pgHostPort", 'Process')

# ── 4. Infra only ─────────────────────────────────────────────────────────────

Write-Step "Starting infra (postgres, redis, minio, vault, pgadmin, demo sites)..."
Set-Location $ProjectRoot
docker compose up -d postgres redis minio vault pgadmin demo-clingroup demo-academy
if ($LASTEXITCODE -ne 0) { Abort "docker compose up failed for infra." }

# ── 5. Wait for Vault ─────────────────────────────────────────────────────────

Write-Step "Waiting for Vault..."
if (-not (Wait-Http "http://localhost:8200/v1/sys/health" -MaxSeconds 60)) {
    Abort "Vault did not become healthy. Check: docker compose logs vault"
}
Write-Ok "Vault healthy."

# ── 6. Seed Vault ─────────────────────────────────────────────────────────────

Write-Step "Seeding Vault via seed.sh..."
$SeedFile = Join-Path $ProjectRoot "seed.sh"
if (-not (Test-Path $SeedFile)) { Abort "seed.sh not found at repo root." }

$gitBash = @(
    "$env:ProgramFiles\Git\bin\bash.exe",
    "$env:ProgramFiles\Git\usr\bin\bash.exe",
    "${env:ProgramFiles(x86)}\Git\bin\bash.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $gitBash) { Abort "Git Bash not found. Install Git for Windows: https://git-scm.com/download/win" }

& $gitBash seed.sh
if ($LASTEXITCODE -ne 0) { Abort "Vault seeding failed. Fix the error above and re-run." }
Write-Ok "Vault seeded."

# ── 7. Patch Vault secrets: docker hostnames -> 127.0.0.1 ────────────────────
#
#  seed.sh writes docker-internal hostnames (postgres, redis, minio).
#  Native services must use 127.0.0.1 since they are not on the docker network.

Write-Step "Patching Vault secrets for local hostnames..."
Update-VaultSecret "concierge/database" @{ host = "127.0.0.1"; port = $pgHostPort }
Update-VaultSecret "concierge/redis"    @{ url      = "redis://127.0.0.1:6379" }
Update-VaultSecret "concierge/minio"    @{ endpoint = "127.0.0.1:9000" }

# ── 8. Override inter-service URLs in process env ─────────────────────────────
#
#  pydantic-settings reads these as env vars, overriding config.py defaults
#  which point to docker service names (model-server:8001, guardrails:8002).

[System.Environment]::SetEnvironmentVariable('VAULT_ADDR',       'http://localhost:8200', 'Process')
[System.Environment]::SetEnvironmentVariable('MODEL_SERVER_URL', 'http://localhost:8001', 'Process')
[System.Environment]::SetEnvironmentVariable('GUARDRAILS_URL',   'http://localhost:8002', 'Process')
[System.Environment]::SetEnvironmentVariable('BACKEND_URL',      'http://localhost:8000', 'Process')

# ── 9. Wait for Postgres, patch pg_hba, run migrations ───────────────────────

Write-Step "Waiting for Postgres..."
$pgUser = $env:POSTGRES_USER
$pgDb   = $env:POSTGRES_DB
$pgReady = $false
for ($i = 0; $i -lt 30; $i += 3) {
    $cId = (docker compose ps -q postgres 2>$null | Select-Object -First 1)
    if ($cId) {
        docker exec $cId pg_isready -U $pgUser -d $pgDb 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) { $pgReady = $true; break }
    }
    Start-Sleep -Seconds 3
    Write-Host "    ... $i/30s"
}
if ($pgReady) { Write-Ok "Postgres ready." }
else { Write-Warning "Postgres not confirmed ready -migrations may fail." }

# Patch pg_hba.conf so that TCP connections from the host (which arrive via
# Docker Desktop NAT, not from 127.0.0.1) are accepted without password.
# scram-sha-256 over Docker Desktop's NAT layer fails even with the right
# password; trust is safe here because only local dev uses this script.
Write-Step "Patching pg_hba.conf for local dev (host trust)..."
$cId = (docker compose ps -q postgres 2>$null | Select-Object -First 1)
if ($cId) {
    docker exec $cId sh -c "sed -i 's/host all all all scram-sha-256/host all all all trust/' /var/lib/postgresql/data/pg_hba.conf && psql -U $pgUser -d $pgDb -c 'SELECT pg_reload_conf();'" 2>&1 | Out-Null
    Write-Ok "pg_hba.conf patched and reloaded."
}

Write-Step "Running Alembic migrations..."
$encodedUser = [System.Uri]::EscapeDataString($env:POSTGRES_USER)
$encodedPass = [System.Uri]::EscapeDataString($env:POSTGRES_PASSWORD)
$dbUrl = "postgresql+asyncpg://${encodedUser}:${encodedPass}@127.0.0.1:${pgHostPort}/$($env:POSTGRES_DB)"
[System.Environment]::SetEnvironmentVariable('DATABASE_URL', $dbUrl, 'Process')

# Diagnostic: show what URL will be used (password masked) so mismatches are obvious
$maskedUrl = $dbUrl -replace '(://[^:]+:)[^@]+(@)', '$1***$2'
Write-Host "    DATABASE_URL = $maskedUrl" -ForegroundColor Gray

Push-Location (Join-Path $ProjectRoot "backend")
uv run alembic upgrade head
$migExit = $LASTEXITCODE
Pop-Location
if ($migExit -ne 0) {
    Write-Host ""
    Write-Host "    HINT: If the error is 'password authentication failed', the postgres" -ForegroundColor Yellow
    Write-Host "    volume has stale credentials. Reset it with:" -ForegroundColor Yellow
    Write-Host "        docker compose down -v" -ForegroundColor Yellow
    Write-Host "    then re-run this script." -ForegroundColor Yellow
    Abort "Alembic migrations failed."
}
Write-Ok "Migrations done."

# ── 10. Launch app services in separate windows ───────────────────────────────
#
#  Child windows inherit the current process environment, so all patched
#  env vars (VAULT_ADDR, MODEL_SERVER_URL, GUARDRAILS_URL, BACKEND_URL) are
#  already present.
#  Clear VIRTUAL_ENV so uv in each child window picks its own project venv
#  without a stale pointer from any uv run that ran in this parent window.

[System.Environment]::SetEnvironmentVariable('VIRTUAL_ENV', $null, 'Process')

Write-Step "Launching app services..."

Open-ServiceWindow "backend" `
    (Join-Path $ProjectRoot "backend") `
    "uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

Open-ServiceWindow "model-server" `
    (Join-Path $ProjectRoot "model-server") `
    "uv run uvicorn app.main:app --host 0.0.0.0 --port 8001"

# guardrails depends on nemoguardrails which requires annoy (C++ extension).
# annoy has no pre-built Windows wheels on PyPI; it needs MSVC Build Tools to compile.
# If you don't have MSVC, run guardrails in Docker instead:
#   docker compose up -d guardrails
# and comment out the Open-ServiceWindow line below.
# Install MSVC: winget install Microsoft.VisualStudio.2022.BuildTools
Write-Step "Pre-syncing guardrails deps (needs MSVC for annoy C++ extension)..."
$guardrailsDir = Join-Path $ProjectRoot "guardrails"
Push-Location $guardrailsDir
uv sync --quiet | Out-Null
$guardrailsSyncOk = $LASTEXITCODE -eq 0
Pop-Location

if ($guardrailsSyncOk) {
    Open-ServiceWindow "guardrails" $guardrailsDir `
        "uv run uvicorn app.main:app --host 0.0.0.0 --port 8002"
} else {
    Write-Host ""
    Write-Host "    guardrails uv sync failed (likely missing MSVC for annoy)." -ForegroundColor Yellow
    Write-Host "    Falling back to Docker for guardrails..." -ForegroundColor Yellow
    Set-Location $ProjectRoot
    docker compose up -d guardrails
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "guardrails running in Docker on port 8002."
        Write-Host "    To fix natively: winget install Microsoft.VisualStudio.2022.BuildTools" -ForegroundColor Gray
    } else {
        Write-Warning "guardrails Docker start also failed. Check: docker compose logs guardrails"
    }
}

Open-ServiceWindow "streamlit" `
    (Join-Path $ProjectRoot "streamlit") `
    "uv run streamlit run app.py --server.port 8501"

Open-ServiceWindow "widget" `
    (Join-Path $ProjectRoot "widget") `
    "npm install --silent; npm run dev"

# ── 11. Wait for backend, open browser ───────────────────────────────────────

Write-Step "Waiting for backend to accept requests..."
if (Wait-Http "http://localhost:8000/healthz" -MaxSeconds 90) {
    Write-Ok "Backend healthy."
} else {
    Write-Warning "Backend not ready yet -check the backend window for errors."
}

Start-Process "http://localhost:8501"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  All services launched." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Streamlit admin  : http://localhost:8501"
Write-Host "  Backend API docs : http://localhost:8000/docs"
Write-Host "  Widget dev       : http://localhost:5173"
Write-Host "  Demo - ClinGroup : http://localhost:3001"
Write-Host "  Demo - Academy   : http://localhost:3002"
Write-Host "  pgAdmin          : http://localhost:5050"
Write-Host "  MinIO console    : http://localhost:9001"
Write-Host "  Vault UI         : http://localhost:8200  (token = VAULT_TOKEN in .env)"
Write-Host ""
Write-Host "  Seed tenant CMS content (run once after creating tenants):"
Write-Host "    python scripts/seed_cms.py"
Write-Host ""
Write-Host "  Close individual service windows to stop each process."
Write-Host "  docker compose down       (stops infra + demo sites)"
Write-Host ""
Read-Host "Press Enter to close this window"
