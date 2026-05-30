DEFAULT_CHUNK_MAX_CHARS = 300


def chunk_markdown(
    markdown: str,
    *,
    max_chars: int = DEFAULT_CHUNK_MAX_CHARS,
) -> list[str]:
    sections = [
        section.strip() for section in markdown.split("\n\n") if section.strip()
    ]
    chunks: list[str] = []
    current = ""

    for section in sections:
        section_chunks = _split_oversized_section(section, max_chars=max_chars)
        for piece in section_chunks:
            if not current:
                current = piece
                continue

            candidate = f"{current}\n\n{piece}"
            if len(candidate) <= max_chars:
                current = candidate
                continue

            chunks.append(current)
            current = piece

    if current:
        chunks.append(current)

    return [chunk for chunk in chunks if chunk.strip()]


def _split_oversized_section(section: str, *, max_chars: int) -> list[str]:
    if len(section) <= max_chars:
        return [section]

    words = section.split()
    parts: list[str] = []
    current_words: list[str] = []
    current_length = 0
    for word in words:
        word_length = len(word) + (1 if current_words else 0)
        if current_words and current_length + word_length > max_chars:
            parts.append(" ".join(current_words))
            current_words = [word]
            current_length = len(word)
            continue
        current_words.append(word)
        current_length += word_length

    if current_words:
        parts.append(" ".join(current_words))
    return parts
