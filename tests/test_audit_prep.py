"""Input selection: the audit must run on a single agreement, a named subset, a glob, or a whole
folder — from anywhere on disk — and must surface bad/odd inputs instead of silently dropping them."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import audit_prep  # noqa: E402


def _run(monkeypatch, capsys, argv) -> dict:
    monkeypatch.setattr(sys, "argv", ["audit_prep.py"] + argv)
    audit_prep.main()
    return json.loads(capsys.readouterr().out)


def test_single_file_selects_just_that_file(tmp_path):
    f = tmp_path / "acme.md"
    f.write_text("x", encoding="utf-8")
    (tmp_path / "beta.md").write_text("y", encoding="utf-8")
    assert audit_prep.select_files(str(f), None) == [f]          # the one file, not the folder


def test_directory_selects_all_files(tmp_path):
    (tmp_path / "a.md").write_text("x", encoding="utf-8")
    (tmp_path / "b.pdf").write_text("y", encoding="utf-8")
    got = {p.name for p in audit_prep.select_files(str(tmp_path), None)}
    assert got == {"a.md", "b.pdf"}


def test_explicit_files_list(tmp_path):
    a, b = tmp_path / "a.md", tmp_path / "b.docx"
    got = audit_prep.select_files(str(tmp_path), [str(a), str(b)])
    assert got == [a, b]                                          # exactly the named subset


def test_missing_directory_yields_nothing(tmp_path):
    assert audit_prep.select_files(str(tmp_path / "nope"), None) == []          # dir typo -> empty run


def test_missing_file_like_path_is_surfaced(tmp_path):
    missing = tmp_path / "ghost.pdf"
    assert audit_prep.select_files(str(missing), None) == [missing]             # file typo -> "file not found"


def test_tilde_paths_expand_for_external_files(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    f = tmp_path / "homedoc.md"
    f.write_text("x", encoding="utf-8")
    assert audit_prep.select_files("~/homedoc.md", None) == [f]                 # ~ expands -> resolves
    assert audit_prep.select_files(None, ["~/homedoc.md"]) == [f]               # in the files list too


def test_safe_doc_id_neutralizes_shell_metacharacters():
    out = audit_prep.safe_doc_id("a$(whoami)`id`;rm -rf ~")
    assert not (set('$`";|&<>()\\') & set(out)) and "~" not in out      # injection chars gone
    assert audit_prep.safe_doc_id("Acme Rights Agreement v1.2") == "Acme Rights Agreement v1.2"  # normal name unchanged
    assert audit_prep.safe_doc_id("") == "document"                     # never empty


def test_glob_expands(tmp_path):
    (tmp_path / "a.docx").write_text("x", encoding="utf-8")
    (tmp_path / "b.docx").write_text("y", encoding="utf-8")
    (tmp_path / "c.txt").write_text("z", encoding="utf-8")
    got = {p.name for p in audit_prep.select_files(str(tmp_path / "*.docx"), None)}
    assert got == {"a.docx", "b.docx"}                                  # glob expands; c.txt excluded


def test_dir_mode_surfaces_unsupported_but_ignores_dotfiles(tmp_path, monkeypatch, capsys):
    (tmp_path / "good.md").write_text("Governed by Delaware.", encoding="utf-8")
    (tmp_path / "contract.rtf").write_text("x", encoding="utf-8")       # real wrong-type file -> surfaced
    (tmp_path / ".DS_Store").write_text("x", encoding="utf-8")          # OS noise -> ignored
    out = _run(monkeypatch, capsys, ["--docs", str(tmp_path), "--out", str(tmp_path / "work")])
    skipped = {s["doc_id"] for s in out["skipped"]}
    assert "good" in out["doc_ids"]
    assert "contract" in skipped and ".DS_Store" not in skipped and "DS_Store" not in skipped


def test_named_missing_file_is_surfaced(tmp_path, monkeypatch, capsys):
    out = _run(monkeypatch, capsys, ["--docs", str(tmp_path / "ghost.pdf"), "--out", str(tmp_path / "work")])
    assert out["doc_ids"] == [] and out["skipped"][0]["doc_id"] == "ghost"
    assert "not found" in out["skipped"][0]["reason"]


def test_stale_sources_wiped_each_run(tmp_path, monkeypatch, capsys):
    work = tmp_path / "work"
    (work / "sources").mkdir(parents=True)
    (work / "sources" / "old.md").write_text("stale text from a prior run", encoding="utf-8")
    (tmp_path / "new.md").write_text("Governed by Delaware.", encoding="utf-8")
    _run(monkeypatch, capsys, ["--docs", str(tmp_path / "new.md"), "--out", str(work)])
    assert not (work / "sources" / "old.md").exists()                  # stale source can't be grounded against
    assert (work / "sources" / "new.md").exists()


def test_cross_folder_same_stem_raises(tmp_path, monkeypatch):
    a, b = tmp_path / "a" / "contract.md", tmp_path / "b" / "contract.txt"
    a.parent.mkdir(); b.parent.mkdir()
    a.write_text("x", encoding="utf-8"); b.write_text("y", encoding="utf-8")
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"files": [str(a), str(b)]}), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["audit_prep.py", "--config", str(cfg), "--out", str(tmp_path / "w")])
    with pytest.raises(SystemExit):                                    # same stem from different folders
        audit_prep.main()
