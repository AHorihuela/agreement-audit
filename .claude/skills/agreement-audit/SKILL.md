---
name: agreement-audit
description: Audit a folder of legal agreements — extract a set of clauses across every contract with verbatim-grounded citations, adversarial cross-checks, a coverage receipt proving every document was examined, and a human-review queue. Returns the findings in chat AND a Word report, and answers follow-up questions about the results. Runs on your Claude Code subscription (the agents) + local Python (parsing + the deterministic grounding gate). Token-heavy multi-agent run — invoke manually.
allowed-tools: Bash, Workflow, Write, Read
disable-model-invocation: true
---

# Agreement clause audit

Run a grounded, multi-agent audit over a folder of agreements, then **report the findings in chat,
write a Word report, and stay available for follow-up questions.** The expensive part (extraction +
verification) runs as Claude Code subagents → the user's subscription. Parsing and the **deterministic
verbatim-grounding gate** run as local Python, so the one hard guarantee — every quote shown is
actually in the source — is decided by code, never by an agent's say-so.

## Steps (when invoked as `/agreement-audit [docs_dir] [clauses…]`)

1. **Resolve scope + write the config.** Default `docs_dir` = `agreements`; default clauses = governing
   law, exclusivity, term, termination notice, MFN. **Scope can be a whole folder, a single agreement,
   or a named subset** — write `.audit/audit_config.json` accordingly:
   - whole folder → `{"docs_dir": "agreements", "fields": [{"key": "...", "label": "...", "question": "..."}, …]}`
   - **one agreement** → point `docs_dir` at the file: `{"docs_dir": "agreements/acme.pdf", "fields": […]}`
   - a specific subset → `{"files": ["agreements/a.pdf", "agreements/b.docx"], "fields": […]}`
   If the user names specific documents or clauses, build the scope from that.
   **This config — not the `args` global — is how scope reaches the workflow.**
   **Cost guard (read first):** ~1 extract + 2 verify agents per (doc × clause). A large corpus
   (e.g. 25 docs × 5 clauses ≈ 280 agents / millions of subscription tokens, ~10+ min) is expensive.
   For a first run or a spot-check, scope `docs_dir` to a **small sample** (or fewer clauses) and
   **confirm with the user before auditing the whole corpus.**

2. **Run the workflow** (subscription-billed) — scope read from the config, no args:
   `Workflow({ name: "agreement-audit" })`  (if the name doesn't resolve, use
   `Workflow({ scriptPath: ".claude/workflows/agreement-audit.js" })`). It runs `audit_prep`, fans out
   one agent per (document × clause) to extract `{value, verbatim quote, found, confidence}`, then runs
   two diverse-lens verifier agents per finding (a finding is "clean" only if **both** agree; any
   dissent → review queue). It returns `{ doc_ids, skipped, fields, findings }`.

3. **Persist the result:** `Write` the workflow's returned object to `.audit/findings.json`.

4. **Run the deterministic consolidation** (the misquotation guarantee + the receipt — code, not an
   agent):
   `Bash: python3 scripts/audit_report.py --findings .audit/findings.json --md .audit --out .audit/report.md --docx .audit/report.docx`
   It re-grounds **every** quote, **drops** any not verbatim-present, and writes a Markdown record plus
   the **Word deliverable** (`.audit/report.docx`): coverage receipt, color-coded grid, per-document
   detail with the verbatim quotes, and a review queue with reviewer sign-off space.

5. **Report the findings in chat** (do not just point at the file): show the **coverage receipt**
   (N examined / grounded / review / dropped / not found), the **doc × clause grid** as a readable
   Markdown table (status emoji + short value per cell), and the **review queue** in full (each flagged
   item with the clause, the extracted answer, the verbatim quote, and *why* it was flagged — review
   reasons distinguish *refuted* / *not verified* / *source not loaded* / *low confidence*). Call out
   any documents that **could not be parsed** (the skipped list, with reasons). If **zero** documents
   parsed, say so plainly — an empty run is not a clean audit. Then name the Word report path
   (`.audit/report.docx`). State plainly, without softening:
   - Grounding proves each quote is **present in the source**, not that the conclusion is **correct**.
   - The verify step + review queue surface likely errors, but a **lawyer must adjudicate** the queue
     and **spot-check a sample** — the true error rate is unknown until checked against ground truth.
   - The verifier agents are Claude (same family as the extractor): they catch over-citation and
     obvious mis-citation, but same-family checking is **self-consistency, not ground truth**.

6. **Answer follow-up questions** about the audit, conversationally, until the user is done. Read
   `.audit/findings.json` and answer **only from it** (it already holds the grounded quotes):
   - Filters / lookups ("which deals have an MFN?", "list the governing-law states", "show the
     termination clause for X") — answer from the findings, and **quote the verbatim text** when citing.
   - "Why was X flagged?" — give the `verify_reason` for that cell.
   - A clause **not in this run** (e.g. "what about assignment / change-of-control?") — that wasn't
     audited; **offer to run a scoped re-audit** for that clause (write a new config with just that
     field + the relevant docs, re-run the workflow). Do NOT answer a new clause from memory — it must
     go through the grounded pipeline.
   Never present a quote you haven't confirmed is in `.audit/<doc>.md`; if in doubt, re-ground it.

## Notes
- **Requirements:** Python 3.10+, `pip install -r requirements.txt` (python-docx, PyMuPDF), and run
  Claude Code from this repo (the workflow calls `scripts/`). Put the contracts in `agreements/`
  (or pass another `docs_dir`). `.audit/` and `agreements/` hold confidential text — both are
  **gitignored**; never commit real contracts or the generated report.
- **Scaling:** start small (a few docs, a few clauses); expand once the report shape + review-queue
  load look right on a sample.
