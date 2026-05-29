import pytest

from app.security.origin import is_origin_allowed, normalize_origin


class TestNormalizeOrigin:
    def test_exact_valid_origin_passes(self) -> None:
        result = normalize_origin("https://example.com")
        assert result == "https://example.com"

    def test_trailing_slash_is_stripped(self) -> None:
        result = normalize_origin("https://example.com/")
        assert result == "https://example.com"

    def test_uppercase_host_scheme_normalizes(self) -> None:
        result = normalize_origin("HTTPS://EXAMPLE.COM:8080")
        assert result == "https://example.com:8080"

    def test_preserves_explicit_port(self) -> None:
        result = normalize_origin("http://example.com:3000")
        assert result == "http://example.com:3000"

    def test_raises_on_non_http_scheme(self) -> None:
        with pytest.raises(ValueError, match="Unsupported scheme"):
            normalize_origin("ftp://example.com")

    def test_raises_on_missing_hostname(self) -> None:
        with pytest.raises(ValueError, match="hostname"):
            normalize_origin("https://")

    def test_raises_on_path(self) -> None:
        with pytest.raises(ValueError, match="path"):
            normalize_origin("https://example.com/foo")

    def test_raises_on_query(self) -> None:
        with pytest.raises(ValueError, match="query"):
            normalize_origin("https://example.com?x=1")

    def test_raises_on_fragment(self) -> None:
        with pytest.raises(ValueError, match="fragment"):
            normalize_origin("https://example.com#section")

    def test_raises_on_userinfo(self) -> None:
        with pytest.raises(ValueError, match="userinfo"):
            normalize_origin("https://user@example.com")


class TestIsOriginAllowed:
    def test_empty_allowlist_returns_true(self) -> None:
        assert is_origin_allowed("https://evil.com", []) is True

    def test_missing_origin_with_nonempty_list_returns_false(self) -> None:
        assert is_origin_allowed(None, ["https://example.com"]) is False

    def test_exact_allowed_origin_passes(self) -> None:
        assert is_origin_allowed("https://example.com", ["https://example.com"]) is True

    def test_normalized_allowed_origin_passes(self) -> None:
        assert (
            is_origin_allowed("https://EXAMPLE.COM/", ["HTTPS://example.com"]) is True
        )

    def test_different_port_fails(self) -> None:
        assert (
            is_origin_allowed("https://example.com:3000", ["https://example.com:8080"])
            is False
        )

    def test_invalid_origin_returns_false(self) -> None:
        assert is_origin_allowed("not-a-url", ["https://example.com"]) is False

    def test_invalid_configured_origin_is_ignored(self) -> None:
        assert (
            is_origin_allowed("https://safe.com", ["    ", "https://safe.com"]) is True
        )

    def test_non_http_origin_returns_false(self) -> None:
        assert is_origin_allowed("ftp://example.com", ["https://example.com"]) is False

    def test_origin_with_path_rejected_even_if_host_allowed(self) -> None:
        assert (
            is_origin_allowed("https://example.com/foo", ["https://example.com"])
            is False
        )
