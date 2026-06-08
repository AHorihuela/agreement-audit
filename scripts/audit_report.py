"""[/agreement-audit — final step] Deterministic consolidation + report.

Run AFTER the multi-agent workflow. For every finding it RE-GROUNDS the quote against the source with
`ground.verify_quote` — the hard misquotation gate — so grounding is decided by code here, never taken
on an agent's word. A quote that is not verbatim-present is DROPPED (never presented as fact). It then
writes the doc × clause grid, the coverage receipt, and a human-review queue.

Outputs (both optional, at least one required):
  --out  <file.md>    a Markdown record (machine/diff-friendly)
  --docx <file.docx>  a Word report for the legal team (summary grid + per-document detail with the
                      verbatim quotes + a review queue with sign-off space)

Usage:
  python3 scripts/audit_report.py --findings .audit/findings.json --md .audit \
      --out .audit/report.md --docx .audit/report.docx
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ground import verify_quote  # noqa: E402

# status -> (symbol, text-hex, fill-hex)
STATUS = {
    "answer":     ("✓", "2E6B47", "E5EFE7"),   # grounded + verifier-supported
    "review":     ("⚠", "946011", "F7ECD4"),   # grounded but refuted / unverified / low-confidence
    "ungrounded": ("⛔", "A23B2E", "F4E3DF"),   # quote not verbatim in source -> dropped
    "no_source":  ("⛔", "A23B2E", "F4E3DF"),   # the parsed source text was not loaded -> can't verify
    "not_found":  ("—", "6B6358", "EFEADF"),   # genuinely absent
}


def classify(data: dict, md_dir: str) -> dict:
    """Re-ground every finding and bucket it. The single source of truth for both writers.

    Counts are tallied from the RENDERED grid (doc_ids × fields), not per-finding, so the coverage
    receipt always matches what the grid shows — duplicate or stray findings can't inflate it.
    """
    fields = data.get("fields") or []
    findings = data.get("findings", [])
    doc_ids = data.get("doc_ids") or sorted({f.get("doc") for f in findings if f.get("doc")})
    skipped = data.get("skipped", [])
    if not fields:                                       # derive from findings if absent
        fields = [{"key": k, "label": k} for k in sorted({f.get("field") for f in findings if f.get("field")})]
    field_keys = [f["key"] for f in fields]

    _cache: dict[str, object] = {}
    def src(doc: str):
        if doc not in _cache:
            p = Path(md_dir) / f"{doc}.md"
            _cache[doc] = p.read_text(encoding="utf-8") if p.exists() else None  # None = source missing
        return _cache[doc]

    grid = {d: {} for d in doc_ids}
    review = []
    malformed = 0
    seen = set()
    for f in findings:
        doc, key = f.get("doc"), f.get("field")
        if not doc or not key:                           # malformed finding -> log, never crash the run
            malformed += 1
            continue
        if (doc, key) in seen:                           # duplicate (doc, field) -> keep first, don't recount
            continue
        seen.add((doc, key))
        grid.setdefault(doc, {})
        label = f.get("label", key)
        if not f.get("found"):
            grid[doc][key] = {"status": "not_found", "value": "not found", "quote": "", "why": ""}
            continue
        source = src(doc)
        quote = f.get("quote") or ""
        if source is None:                               # source not on disk -> can't verify (NOT a misquote)
            grid[doc][key] = {"status": "no_source", "value": f.get("value") or "", "quote": quote,
                              "why": "Source text not loaded — could not verify."}
            review.append({"doc": doc, "key": key, "label": label, "value": f.get("value"), "quote": quote,
                           "why": "SOURCE NOT LOADED — the parsed text for this document was missing, so the "
                                  "quote could not be grounded. Check that --md points at the parsed output."})
            continue
        if not verify_quote(source, quote).grounded:     # quote not verbatim -> drop, never show as fact
            grid[doc][key] = {"status": "ungrounded", "value": f.get("value") or "", "quote": quote,
                              "why": "Quote is not verbatim in the source."}
            review.append({"doc": doc, "key": key, "label": label, "value": f.get("value"), "quote": quote,
                           "why": "DROPPED — the cited quote is not present verbatim in the source."})
            continue
        vs = f.get("verify_supports", None)              # True | False | None(not verified)
        low_conf = (f.get("confidence") if f.get("confidence") is not None else 1.0) < 0.5
        if vs is False:
            grid[doc][key] = {"status": "review", "value": f.get("value") or "(see quote)", "quote": quote,
                              "why": f.get("verify_reason") or ""}
            review.append({"doc": doc, "key": key, "label": label, "value": f.get("value"), "quote": quote,
                           "why": "VERIFY REFUTED — " + (f.get("verify_reason") or "the quote may not support the claim.")})
        elif vs is None:                                 # grounded, but support was never checked
            grid[doc][key] = {"status": "review", "value": f.get("value") or "(see quote)", "quote": quote,
                              "why": "Grounded, but support was not checked."}
            review.append({"doc": doc, "key": key, "label": label, "value": f.get("value"), "quote": quote,
                           "why": "NOT VERIFIED — the quote is present in the source, but the verifier did not "
                                  "run, so whether it supports the answer was not checked. Review manually."})
        else:                                            # grounded + supported
            grid[doc][key] = {"status": "answer", "value": f.get("value") or "(see quote)", "quote": quote,
                              "why": ""}
            if low_conf:
                review.append({"doc": doc, "key": key, "label": label, "value": f.get("value"), "quote": quote,
                               "why": "LOW CONFIDENCE — the extractor was unsure; spot-check."})

    counts = {s: 0 for s in STATUS}
    for d in doc_ids:                                    # tally the RENDERED grid -> receipt == grid
        for k in field_keys:
            counts[grid.get(d, {}).get(k, {"status": "not_found"})["status"]] += 1

    return {"doc_ids": doc_ids, "skipped": skipped, "fields": fields, "grid": grid,
            "review": review, "counts": counts, "malformed": malformed}


def _skip(s) -> tuple:
    if isinstance(s, dict):
        return s.get("doc_id", "?"), s.get("reason", "")
    return str(s), ""


def _receipt(counts: dict, n_docs: int, n_cells: int, skipped: list, malformed: int) -> str:
    dropped = counts.get("ungrounded", 0) + counts.get("no_source", 0)
    s = (f"{n_docs} agreements examined · {n_cells} clause checks · {counts.get('answer', 0)} grounded "
         f"· {counts.get('review', 0)} need review · {dropped} dropped/unverifiable "
         f"· {counts.get('not_found', 0)} not found")
    if skipped:
        s += f" · {len(skipped)} could not be parsed"
    if malformed:
        s += f" · {malformed} malformed finding(s) ignored"
    return s


# ---------- Markdown ----------

def write_md(path: str, R: dict) -> None:
    grid, fields, doc_ids = R["grid"], R["fields"], R["doc_ids"]
    cols, keys = [f["label"] for f in fields], [f["key"] for f in fields]
    n_cells = len(doc_ids) * len(keys)
    out = ["# Agreement clause audit\n",
           f"**Coverage receipt:** {_receipt(R['counts'], len(doc_ids), n_cells, R['skipped'], R['malformed'])}\n",
           "\n## Clauses across the portfolio\n",
           "| Agreement | " + " | ".join(cols) + " |",
           "|" + "---|" * (len(cols) + 1)]
    for d in doc_ids:
        row = [d]
        for k in keys:
            c = grid.get(d, {}).get(k, {"status": "not_found", "value": "—"})
            row.append(f"{STATUS[c['status']][0]} {(c['value'] or '—').replace(chr(10), ' ')[:60]}")
        out.append("| " + " | ".join(row) + " |")
    out.append("\n## Needs human review\n")
    if not R["review"]:
        out.append("_None flagged automatically — a human should still spot-check a sample._\n")
    else:
        for r in R["review"]:
            out.append(f"- **{r['doc']}** · `{r['key']}` — {r['why']}"
                       + (f" (extracted: {r['value']})" if r.get("value") else ""))
    if R["skipped"]:
        out.append("\n## Could not be parsed (not audited)\n")
        for s in R["skipped"]:
            sid, reason = _skip(s)
            out.append(f"- **{sid}** — {reason or 'no extractable text'}")
    out.append("\n---\n_Grounding (✓ quote verbatim-present) is deterministic; it proves presence, not "
               "correctness. ⚠ needs review (refuted / unverified / low-confidence). ⛔ dropped (quote not "
               "in source, or source not loaded). A lawyer signs off._\n")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(out), encoding="utf-8")


# ---------- Word ----------

def _shade(cell, fill_hex: str) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), fill_hex)
    cell._tc.get_or_add_tcPr().append(shd)


def write_docx(path: str, R: dict) -> None:
    from docx import Document
    from docx.shared import Pt, RGBColor

    grid, fields, doc_ids, review = R["grid"], R["fields"], R["doc_ids"], R["review"]
    keys = [f["key"] for f in fields]
    n_cells = len(doc_ids) * len(keys)
    doc = Document()

    doc.add_heading("Agreement Clause Audit", 0)
    doc.add_paragraph().add_run(
        f"{len(doc_ids)} agreements · generated {datetime.now():%Y-%m-%d %H:%M}").italic = True

    rc = doc.add_paragraph()
    rc.add_run("Coverage receipt: ").bold = True
    rc.add_run(_receipt(R["counts"], len(doc_ids), n_cells, R["skipped"], R["malformed"]))

    leg = doc.add_paragraph()
    leg.add_run("How to read this report. ").bold = True
    leg.add_run("✓ grounded — the quote is present in the source verbatim; this proves the quote is real, "
                "NOT that the conclusion is correct. ⚠ needs review — the verifier dissented, did not run, "
                "or the extractor was unsure. ⛔ dropped — the quote was not found in the source (removed), "
                "or the source text could not be loaded. — not found — the clause is genuinely absent. This "
                "report augments expert review; a lawyer signs off, and the true error rate is unknown until "
                "a sample is checked against ground truth.")

    h = doc.add_heading("Needs human review", level=1)
    h.runs[0].font.color.rgb = RGBColor(0xA2, 0x3B, 0x2E)
    if not review:
        doc.add_paragraph("None flagged automatically — a human should still spot-check a sample of the "
                          "grounded answers below.")
    else:
        for r in review:
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(f"{r['doc']} — {r['label']}: ").bold = True
            p.add_run(r["why"])
            if r.get("value"):
                ev = doc.add_paragraph()
                ev.paragraph_format.left_indent = Pt(24)
                ev.add_run("Extracted answer: ").bold = True
                ev.add_run(str(r["value"]))
            if r.get("quote"):
                q = doc.add_paragraph()
                q.paragraph_format.left_indent = Pt(24)
                qr = q.add_run(f"“{r['quote']}”")
                qr.italic = True
                qr.font.color.rgb = RGBColor(0x4A, 0x44, 0x3B)
            so = doc.add_paragraph()
            so.paragraph_format.left_indent = Pt(24)
            so.add_run("Reviewer decision: ____________   Notes: ").bold = True
            so.add_run("________________________________________")

    if R["skipped"]:
        doc.add_heading("Could not be parsed (not audited)", level=1)
        for s in R["skipped"]:
            sid, reason = _skip(s)
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(f"{sid}: ").bold = True
            p.add_run(reason or "no extractable text")

    doc.add_heading("Clauses across the portfolio", level=1)
    table = doc.add_table(rows=1, cols=len(fields) + 1)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    hdr[0].paragraphs[0].add_run("Agreement").bold = True
    for i, f in enumerate(fields):
        hdr[i + 1].paragraphs[0].add_run(f["label"]).bold = True
    for d in doc_ids:
        cells = table.add_row().cells
        cells[0].paragraphs[0].add_run(d).bold = True
        for i, k in enumerate(keys):
            c = grid.get(d, {}).get(k, {"status": "not_found", "value": "—"})
            sym, txt_hex, fill_hex = STATUS[c["status"]]
            cell = cells[i + 1]
            run = cell.paragraphs[0].add_run(f"{sym} {(c['value'] or '—').replace(chr(10), ' ')[:70]}")
            run.font.size = Pt(8)
            run.font.color.rgb = RGBColor.from_string(txt_hex)
            _shade(cell, fill_hex)

    doc.add_heading("Detail by agreement", level=1)
    for d in doc_ids:
        doc.add_heading(d, level=2)
        for f in fields:
            c = grid.get(d, {}).get(f["key"])
            if not c:
                continue
            p = doc.add_paragraph()
            p.add_run(f"{STATUS[c['status']][0]} {f['label']}: ").bold = True
            p.add_run(c["value"] or ("not found" if c["status"] == "not_found" else "—"))
            if c.get("quote"):
                q = doc.add_paragraph()
                q.paragraph_format.left_indent = Pt(24)
                qr = q.add_run(f"“{c['quote']}”")
                qr.italic = True
                qr.font.color.rgb = RGBColor(0x4A, 0x44, 0x3B)
            if c.get("why"):
                w = doc.add_paragraph()
                w.paragraph_format.left_indent = Pt(24)
                w.add_run(f"⚠ {c['why']}").font.color.rgb = RGBColor(0x94, 0x60, 0x11)

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--findings", required=True)
    ap.add_argument("--md", default=".audit", help="dir holding the per-doc <doc_id>.md sources")
    ap.add_argument("--out", help="Markdown report path")
    ap.add_argument("--docx", help="Word report path (for the legal team)")
    args = ap.parse_args()
    if not args.out and not args.docx:
        ap.error("provide at least one of --out (Markdown) or --docx (Word)")

    data = json.loads(Path(args.findings).read_text(encoding="utf-8"))
    R = classify(data, args.md)
    # Output may go anywhere the user chose (next to the agreement, ~/Desktop, …) — expand ~.
    out = str(Path(args.out).expanduser()) if args.out else None
    docx = str(Path(args.docx).expanduser()) if args.docx else None
    if out:
        write_md(out, R)
    if docx:
        write_docx(docx, R)
    c, n_cells = R["counts"], len(R["doc_ids"]) * len(R["fields"])
    print(f"{len(R['doc_ids'])} docs · {n_cells} checks · {c['answer']} grounded · {c['review']} review · "
          f"{c['ungrounded'] + c['no_source']} dropped · {c['not_found']} not found"
          + (f" · {R['malformed']} malformed ignored" if R["malformed"] else "")
          + (f"  -> {out}" if out else "") + (f"  -> {docx}" if docx else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
