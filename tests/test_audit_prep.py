"""Input selection: the audit must run on a single agreement, a named subset, or a whole folder."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import audit_prep  # noqa: E402


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
