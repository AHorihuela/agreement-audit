"""The grounding gate — the one hard guarantee. A quote shown to a lawyer must be present verbatim in
the source; anything else must NOT ground (and must never crash)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude/skills/agreement-audit/scripts"))
import ground  # noqa: E402

SRC = "Section 5. Either party may terminate upon sixty (60) days notice. Governed by Delaware."


def test_exact_quote_grounds():
    g = ground.verify_quote(SRC, "sixty (60) days notice")
    assert g.grounded and g.match_type == "exact"


def test_quote_not_in_source_fails():
    assert ground.verify_quote(SRC, "thirty (30) days notice").grounded is False


def test_too_short_quote_fails():
    assert ground.verify_quote(SRC, "a").grounded is False


def test_empty_and_whitespace_quotes_never_ground():
    assert ground.verify_quote(SRC, "").grounded is False
    assert ground.verify_quote(SRC, "   ").grounded is False


def test_empty_needle_guard_no_indexerror():
    assert ground._word_bounded_index("abc", "") is None   # would IndexError without the guard


def test_word_boundary_rejects_midtoken_match():
    assert ground.verify_quote("the party gathered", "art").grounded is False   # inside "party"
    assert ground.verify_quote("the art show", "art").grounded is True          # word-bounded


def test_normalized_fallback_for_reflow():
    g = ground.verify_quote("governed\nby   Delaware", "governed by Delaware")
    assert g.grounded and g.match_type == "normalized"


def test_case_difference_does_not_ground():
    assert ground.verify_quote("the Party shall", "the party shall").grounded is False
