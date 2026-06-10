"""The consolidation gate (audit_report.classify): re-ground every quote, bucket honestly, and keep
the coverage receipt consistent with what the grid actually shows."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude/skills/agreement-audit/scripts"))
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
    assert R["counts"] == {"answer": 1, "review": 2, "ungrounded": 1, "no_source": 0, "not_found": 1,
                           "missing": 0}
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


# --- A cell with NO finding at all is an infrastructure failure, never "the clause is absent". ---

def test_missing_cell_is_flagged_not_reported_as_absent(tmp_path):
    _src(tmp_path, "d6", "Governed by Delaware.")
    data = {"doc_ids": ["d6"], "skipped": [],
            "fields": [{"key": "gov", "label": "Gov"}, {"key": "mfn", "label": "MFN"}],
            "findings": [{"doc": "d6", "field": "gov", "value": "Delaware", "quote": "Governed by Delaware",
                          "found": True, "verify_supports": True}]}   # the mfn extract agent never returned
    R = audit_report.classify(data, str(tmp_path))
    assert R["grid"]["d6"]["mfn"]["status"] == "missing"              # NOT "not_found"
    assert R["counts"] == {"answer": 1, "review": 0, "ungrounded": 0, "no_source": 0,
                           "not_found": 0, "missing": 1}
    assert any("EXTRACTION MISSING" in r["why"] for r in R["review"])
    assert "not returned" in audit_report._receipt(R["counts"], 1, 2, [], 0)


# --- Absence claims: the riskiest output. A checked absence stays clean; a disputed or shaky one ---
# --- goes to the review queue; a refuted-absence candidate quote is itself re-grounded.          ---

def test_absence_disputed_by_verifier_goes_to_review(tmp_path):
    _src(tmp_path, "d7", "The Network shall receive most favored nation treatment as to fees.")
    data = {"doc_ids": ["d7"], "skipped": [], "fields": [{"key": "mfn", "label": "MFN"}],
            "findings": [{"doc": "d7", "field": "mfn", "value": "not found", "quote": "", "found": False,
                          "confidence": 0.9, "absence_check": "refuted",
                          "absence_quote": "most favored nation treatment as to fees",
                          "absence_reason": "Section grants MFN treatment."}]}
    R = audit_report.classify(data, str(tmp_path))
    cell = R["grid"]["d7"]["mfn"]
    assert cell["status"] == "review"
    assert cell["quote"] == "most favored nation treatment as to fees"   # candidate re-grounded + shown
    assert any("ABSENCE DISPUTED" in r["why"] for r in R["review"])


def test_absence_disputed_with_unverbatim_candidate_still_flagged(tmp_path):
    _src(tmp_path, "d8", "No MFN language here at all.")
    data = {"doc_ids": ["d8"], "skipped": [], "fields": [{"key": "mfn", "label": "MFN"}],
            "findings": [{"doc": "d8", "field": "mfn", "value": "not found", "quote": "", "found": False,
                          "confidence": 0.9, "absence_check": "refuted",
                          "absence_quote": "a fabricated candidate quote"}]}
    R = audit_report.classify(data, str(tmp_path))
    cell = R["grid"]["d8"]["mfn"]
    assert cell["status"] == "review" and cell["quote"] == ""            # flagged, fake candidate NOT shown
    assert any("could not be grounded" in r["why"] for r in R["review"])


def test_confirmed_absence_stays_clean(tmp_path):
    _src(tmp_path, "d9", "Nothing about MFN.")
    data = {"doc_ids": ["d9"], "skipped": [], "fields": [{"key": "mfn", "label": "MFN"}],
            "findings": [{"doc": "d9", "field": "mfn", "value": "not found", "quote": "", "found": False,
                          "confidence": 0.9, "absence_check": "confirmed"}]}
    R = audit_report.classify(data, str(tmp_path))
    assert R["grid"]["d9"]["mfn"]["status"] == "not_found" and R["review"] == []


def test_low_confidence_absence_is_flagged_for_review(tmp_path):
    _src(tmp_path, "d10", "Dense document.")
    data = {"doc_ids": ["d10"], "skipped": [], "fields": [{"key": "mfn", "label": "MFN"}],
            "findings": [{"doc": "d10", "field": "mfn", "value": "not found", "quote": "", "found": False,
                          "confidence": 0.3}]}
    R = audit_report.classify(data, str(tmp_path))
    assert R["grid"]["d10"]["mfn"]["status"] == "not_found"              # still reported absent…
    assert any("LOW-CONFIDENCE ABSENCE" in r["why"] for r in R["review"])  # …but queued for a human


def test_high_confidence_unchecked_absence_not_flagged(tmp_path):
    _src(tmp_path, "d11", "Nothing about MFN.")
    data = {"doc_ids": ["d11"], "skipped": [], "fields": [{"key": "mfn", "label": "MFN"}],
            "findings": [{"doc": "d11", "field": "mfn", "value": "not found", "quote": "", "found": False,
                          "confidence": 0.9}]}                            # inline path: no absence_check
    R = audit_report.classify(data, str(tmp_path))
    assert R["grid"]["d11"]["mfn"]["status"] == "not_found" and R["review"] == []


# --- Page numbers: an exact-grounded quote carries the page it sits on, so a reviewer can open ---
# --- the PDF directly instead of Ctrl-F-ing an 80-page document.                               ---

def test_exact_grounded_quote_carries_page_number(tmp_path):
    page1 = "PageOne preamble text here.\n"
    page2 = "The term is seven (7) years."
    _src(tmp_path, "d12", page1 + page2)
    data = {"doc_ids": ["d12"], "skipped": [], "fields": [{"key": "term", "label": "Term"}],
            "pages": {"d12": [0, len(page1)]},
            "findings": [{"doc": "d12", "field": "term", "value": "7 years",
                          "quote": "seven (7) years", "found": True, "verify_supports": True}]}
    R = audit_report.classify(data, str(tmp_path))
    assert R["grid"]["d12"]["term"]["page"] == 2


def test_review_queue_md_shows_page_number(tmp_path):
    page1 = "PageOne preamble.\n"
    page2 = "Most favored nation treatment applies."
    _src(tmp_path, "d13", page1 + page2)
    data = {"doc_ids": ["d13"], "skipped": [], "fields": [{"key": "mfn", "label": "MFN"}],
            "pages": {"d13": [0, len(page1)]},
            "findings": [{"doc": "d13", "field": "mfn", "value": "not found", "quote": "", "found": False,
                          "confidence": 0.9, "absence_check": "refuted",
                          "absence_quote": "Most favored nation treatment applies"}]}
    R = audit_report.classify(data, str(tmp_path))
    out = tmp_path / "r.md"
    audit_report.write_md(str(out), R)
    assert "p. 2" in out.read_text(encoding="utf-8")


# --- The corpus check is code, not prose: a findings file from a different (stale/cached) corpus ---
# --- hard-fails against the manifest, and a minimal findings file inherits the manifest's corpus. ---

def _write(p: Path, obj) -> str:
    p.write_text(json.dumps(obj), encoding="utf-8")
    return str(p)

def test_manifest_corpus_mismatch_hard_fails(tmp_path, monkeypatch):
    findings = _write(tmp_path / "f.json", {"doc_ids": ["other-corpus-doc"], "findings": []})
    manifest = _write(tmp_path / "m.json", {"doc_ids": ["d14"], "skipped": [], "fields": []})
    monkeypatch.setattr(sys, "argv", ["audit_report.py", "--findings", findings, "--manifest", manifest,
                                      "--md", str(tmp_path), "--out", str(tmp_path / "r.md")])
    with pytest.raises(SystemExit) as e:
        audit_report.main()
    assert "mismatch" in str(e.value).lower()
    assert not (tmp_path / "r.md").exists()                  # nothing reported from the wrong corpus


def test_minimal_findings_inherit_manifest_corpus(tmp_path, monkeypatch, capsys):
    _src(tmp_path, "d15", "Governed by Delaware.")
    findings = _write(tmp_path / "f.json", {"findings": [
        {"doc": "d15", "field": "gov", "value": "Delaware", "quote": "Governed by Delaware",
         "found": True, "verify_supports": True}]})
    manifest = _write(tmp_path / "m.json", {
        "doc_ids": ["d15"], "skipped": [{"doc_id": "scan", "reason": "needs OCR"}],
        "fields": [{"key": "gov", "label": "Gov", "question": "Q"}], "pages": {}})
    out = tmp_path / "r.md"
    monkeypatch.setattr(sys, "argv", ["audit_report.py", "--findings", findings, "--manifest", manifest,
                                      "--md", str(tmp_path), "--out", str(out)])
    audit_report.main()
    text = out.read_text(encoding="utf-8")
    assert "1 agreements examined" in text and "1 could not be parsed" in text   # corpus from manifest
    assert "scan" in text
