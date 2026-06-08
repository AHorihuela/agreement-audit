"""Deterministic citation grounding — the anti-misquotation primitive (self-contained, zero deps).

A quote is only trustworthy if it is *actually present in the source*, as a substantive, word-bounded
span. The extraction agents return quotes; we never trust them blindly — we re-verify every quote
against the parsed source bytes here, in code. A quote that fails is dropped and never shown.

Scope: grounding proves PRESENCE (the quote occurs in the source, on word boundaries, at/above a
minimum length). It does NOT judge whether a present quote supports the claim — that is the verifier
agents' job. Grounding shrinks the misquotation surface; the verifier + a human close it.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

# Quotes shorter than this (after stripping) are non-substantive: a bare "a" / "60" is not a citation.
# Kept low so legitimate short terms-of-art / acronyms (e.g. "MFN") still ground.
MIN_QUOTE_CHARS = 3


@dataclass(frozen=True)
class GroundingResult:
    grounded: bool
    match_type: str                   # "exact" | "normalized" | "none" | "too_short"
    char_start: Optional[int] = None
    char_end: Optional[int] = None


def _normalize(text: str) -> str:
    """Forgiving normalization for the fallback check only: collapse whitespace, unify quotes/dashes.
    NFC (not NFKC) so ligatures/fractions aren't silently folded; case is PRESERVED (a verbatim legal
    quote that differs only in case is not the same text). Catches reflow/typography, not paraphrase."""
    text = unicodedata.normalize("NFC", text)
    text = (text
            .replace("‘", "'").replace("’", "'")
            .replace("“", '"').replace("”", '"')
            .replace("–", "-").replace("—", "-")
            .replace(" ", " "))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _word_bounded_index(haystack: str, needle: str) -> Optional[int]:
    """First index of `needle` in `haystack` not glued mid-word on an alphanumeric edge. Prevents
    "art" matching inside "party" while allowing punctuation-edged quotes (e.g. "$5,000,000")."""
    start = haystack.find(needle)
    while start != -1:
        end = start + len(needle)
        left_ok = start == 0 or not (haystack[start - 1].isalnum() and needle[0].isalnum())
        right_ok = end == len(haystack) or not (haystack[end].isalnum() and needle[-1].isalnum())
        if left_ok and right_ok:
            return start
        start = haystack.find(needle, start + 1)
    return None


def verify_quote(source: str, quote: str) -> GroundingResult:
    """Is `quote` genuinely present in `source` as a substantive, word-bounded span? Exact match (with
    offsets) when possible, else a normalized match (offsets unreliable), else not grounded."""
    if not quote or not quote.strip():
        return GroundingResult(grounded=False, match_type="none")
    if len(quote.strip()) < MIN_QUOTE_CHARS:
        return GroundingResult(grounded=False, match_type="too_short")

    idx = _word_bounded_index(source, quote)
    if idx is not None:
        return GroundingResult(grounded=True, match_type="exact", char_start=idx, char_end=idx + len(quote))
    if _word_bounded_index(_normalize(source), _normalize(quote)) is not None:
        return GroundingResult(grounded=True, match_type="normalized")
    return GroundingResult(grounded=False, match_type="none")


if __name__ == "__main__":  # tiny self-check: python3 scripts/ground.py
    src = "Section 5. Either party may terminate upon sixty (60) days notice."
    assert verify_quote(src, "sixty (60) days notice").grounded is True
    assert verify_quote(src, "thirty (30) days notice").grounded is False   # not in source -> dropped
    assert verify_quote(src, "a").grounded is False                          # too short
    print("ground.py self-check passed")
