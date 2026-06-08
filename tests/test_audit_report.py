"""The consolidation gate (audit_report.classify): re-ground every quote, bucket honestly, and keep
the coverage receipt consistent with what the grid actually shows."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import audit_report  # noqa: E402


def _src(tmp_path, doc_id, text):
    (tmp_path / f"{doc_id}.md").write_text(text, encoding="utf-8")


def test_tristate_verify_and_grounding_buckets(tmp_path):
    _src(tmp_path, "d1", "Governed by the State of Delaware. Term of five (5) years. Exclusive rights granted.")
    data = {"doc_ids": ["d1"], "skipped": [],
            "fields": [{"key": "gov", "label": "Gov"}, {"key": "term", "label": "Term"},
                       {"key": "exc", "label": "Exc"}, {"key": "mfn", "label": "MFN"},
                       {"key": "ren", "label": "Ren"}],
            "findings": [
                {"doc": "d1", "field": "gov", "value": "Delaware", "quote": "Governed by the State of Delaware",
                 "found": True, "verify_supports": True, "confidence": 0.9},                      # answer
                {"doc": "d1", "field": "term", "value": "5y", "quote": "Term of five (5) years",
                 "found": True, "verify_supports": False, "verify_reason": "wrong clause", "confidence": 0.9},  # refuted
                {"doc": "d1", "field": "exc", "value": "exclusive", "quote": "Exclusive rights granted",
                 "found": True, "verify_supports": None, "confidence": 0.9},                       # NOT verified
                {"doc": "d1", "field": "mfn", "value": "New York", "quote": "governed by New York",
                 "found": True, "verify_supports": True, "confidence": 0.9},                       # fake quote -> dropped
                {"doc": "d1", "field": "ren", "value": "not found", "quote": "", "found": False},  # not found
            ]}
    R = audit_report.classify(data, str(tmp_path))
    g = R["grid"]["d1"]
    assert g["gov"]["status"] == "answer"
    assert g["term"]["status"] == "review"        # a real refutation
    assert g["exc"]["status"] == "review"         # verifier never ran
    assert g["mfn"]["status"] == "ungrounded"     # grounding gate fires before verify
    assert g["ren"]["status"] == "not_found"
    assert R["counts"] == {"answer": 1, "review": 2, "ungrounded": 1, "no_source": 0, "not_found": 1}
    whys = " ".join(r["why"] for r in R["review"])
    assert "VERIFY REFUTED" in whys and "NOT VERIFIED" in whys and "DROPPED" in whys


def test_missing_source_is_no_source_not_misquote(tmp_path):
    data = {"doc_ids": ["d2"], "skipped": [], "fields": [{"key": "gov", "label": "Gov"}],
            "findings": [{"doc": "d2", "field": "gov", "value": "X", "quote": "anything",
                          "found": True, "verify_supports": True}]}
    R = audit_report.classify(data, str(tmp_path))      # no d2.md on disk
    assert R["grid"]["d2"]["gov"]["status"] == "no_source"
    assert any("SOURCE NOT LOADED" in r["why"] for r in R["review"])


def test_duplicate_cell_not_double_counted(tmp_path):
    _src(tmp_path, "d3", "Governed by Delaware.")
    f = {"doc": "d3", "field": "gov", "value": "Delaware", "quote": "Governed by Delaware",
         "found": True, "verify_supports": True}
    data = {"doc_ids": ["d3"], "skipped": [], "fields": [{"key": "gov", "label": "Gov"}],
            "findings": [f, dict(f, value="dup")]}
    R = audit_report.classify(data, str(tmp_path))
    assert R["counts"]["answer"] == 1                   # tallied from the grid, not per-finding


def test_malformed_finding_ignored_not_crash(tmp_path):
    _src(tmp_path, "d4", "Governed by Delaware.")
    data = {"doc_ids": ["d4"], "skipped": [], "fields": [{"key": "gov", "label": "Gov"}],
            "findings": [
                {"doc": "d4", "field": "gov", "value": "Delaware", "quote": "Governed by Delaware",
                 "found": True, "verify_supports": True},
                {"value": "orphan", "found": True},     # missing doc + field
            ]}
    R = audit_report.classify(data, str(tmp_path))
    assert R["malformed"] == 1 and R["counts"]["answer"] == 1


def test_field_not_in_fields_does_not_inflate_counts(tmp_path):
    _src(tmp_path, "d5", "Governed by Delaware. Assignment permitted.")
    data = {"doc_ids": ["d5"], "skipped": [], "fields": [{"key": "gov", "label": "Gov"}],
            "findings": [
                {"doc": "d5", "field": "gov", "value": "Delaware", "quote": "Governed by Delaware",
                 "found": True, "verify_supports": True},
                {"doc": "d5", "field": "assignment", "value": "permitted", "quote": "Assignment permitted",
                 "found": True, "verify_supports": True},   # field not in `fields`
            ]}
    R = audit_report.classify(data, str(tmp_path))
    assert sum(R["counts"].values()) == 1 and R["counts"]["answer"] == 1   # only the rendered cell counts
