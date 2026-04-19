"""Text cleaning and chunking for seq2seq summarization."""
from __future__ import annotations

import re


CHARS_PER_TOKEN = 3.5  # conservative estimate for German legal text

# Default limits (mT5: 512 token max; BART: 1024 token max)
# Pipeline overrides these via chunk(text, token_limit=…)
_DEFAULT_TOKEN_LIMIT = 400
_DEFAULT_OVERLAP_TOKENS = 40

# Legacy constants kept for imports elsewhere
CHUNK_SIZE = int(_DEFAULT_TOKEN_LIMIT * CHARS_PER_TOKEN)
OVERLAP_SIZE = int(_DEFAULT_OVERLAP_TOKENS * CHARS_PER_TOKEN)


def clean(text: str) -> str:
    """Remove artifacts typical in court-ruling PDFs."""
    # 1. Normalize form-feeds
    text = re.sub(r"\f", "\n", text)

    # 2. Undo hyphenation at line breaks BEFORE anything else collapses newlines.
    #    Handles regular hyphen and soft-hyphen (\xad).
    #    Case A: hyphen followed by newline then word chars (standard PDF split)
    text = re.sub(r"([a-zäöüßA-ZÄÖÜ])-\n\s*([a-zäöüßA-ZÄÖÜ])", r"\1\2", text)
    #    Case B: hyphen at end of page/string (next part on next page → no \n visible)
    #    Only remove trailing hyphens that are preceded by ≥3 word chars and followed
    #    by a newline or form-feed boundary (PyMuPDF page join).
    text = re.sub(r"([a-zäöüßA-ZÄÖÜ]{3,})-(\n|$)", r"\1\2", text)
    # also catch soft-hyphen
    text = re.sub(r"\xad[\n\s]*", "", text)

    # 4. Remove standalone page-header/footer lines that are only digits
    #    (paragraph numbers like "1\n", "22\n" etc.)
    text = re.sub(r"(?m)^\s*\d{1,3}\s*$", "", text)

    # 5. Remove inline "- Seite N von M -" page markers — case-insensitive
    text = re.sub(r"-?\s*[Ss][Ee][Ii][Tt][Ee]\s+\d+\s+[Vv][Oo][Nn]\s+\d+\s*-?", " ", text,
                  flags=re.IGNORECASE)

    # 6. Remove non-breaking spaces
    text = text.replace("\xa0", " ")

    # 7. Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)

    # 8. Normalise line breaks: keep paragraph breaks, collapse single newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)

    # 9. After line-break collapse, lone paragraph numbers remain as " NN " between
    #    sentences (e.g. "…unzuständig. 22 a) Nach §100 …").  Remove them.
    #    Match: sentence-end punctuation + space + 1–3 digits + space + uppercase/paren.
    text = re.sub(r"([.!?] )\d{1,3} (?=[A-ZÄÖÜ(])", r"\1", text)
    # Also at very start of text
    text = re.sub(r"^\d{1,3} (?=[A-ZÄÖÜ(])", "", text)

    text = text.strip()
    return text


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk(text: str, token_limit: int = _DEFAULT_TOKEN_LIMIT,
          overlap_tokens: int = _DEFAULT_OVERLAP_TOKENS) -> list[str]:
    """
    Split text into overlapping chunks sized for the model's token budget.

    Args:
        token_limit:    Max tokens per chunk (mT5: 400, BART: 800).
        overlap_tokens: Context overlap between chunks (keeps coherence).
    """
    chunk_size   = int(token_limit    * CHARS_PER_TOKEN)
    overlap_size = int(overlap_tokens * CHARS_PER_TOKEN)

    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end >= len(text):
            chunks.append(text[start:].strip())
            break

        # Search for a sentence boundary in the last 50% of the chunk.
        # German legal texts have long nested sentences — a narrower window
        # often finds nothing and causes mid-sentence cuts.
        search_start = start + int(chunk_size * 0.5)
        boundary = _find_sentence_boundary(text, search_start, end)

        # Fallback: search the entire chunk from the beginning
        if boundary == -1:
            boundary = _find_sentence_boundary(text, start, end)

        # Last resort: hard cut at chunk end
        if boundary == -1:
            boundary = end

        chunks.append(text[start:boundary].strip())
        start = boundary - overlap_size

    return [c for c in chunks if c]


def _find_sentence_boundary(text: str, from_pos: int, to_pos: int) -> int:
    """Return position just after the last sentence-ending punctuation in range."""
    segment = text[from_pos:to_pos]
    last = None
    for pattern in (r"[.!?]\s", r"[.!?]$"):
        for m in re.finditer(pattern, segment):
            last = m
    if last:
        return from_pos + last.end()
    return -1
