---
name: agreement-audit
description: Audit legal agreements — a whole folder, a single agreement, or specific files anywhere on disk — for the clauses you ask about in natural language (e.g. "explain the non-compete in ~/Downloads/acme.pdf"), with verbatim-grounded citations, adversarial cross-checks, a coverage receipt proving every document was examined, and a human-review queue. Returns the findings in chat AND a Word report, and answers follow-up questions. Runs on your Claude Code subscription (the agents) + local Python (parsing + the deterministic grounding gate). Token-heavy multi-agent run — invoke manually.
allowed-tools: Bash, Workflow, Write, Read
disable-model-invocation: true
---

# Agreement clause audit

Run a grounded, multi-agent audit over a folder of agreements, then **report the findings in chat,
write a Word report, and stay available for follow-up questions.** The expensive part (extraction +
verification) runs as Claude Code subagents → the user's subscription. Parsing and the **deterministic
verbatim-grounding gate** run as local Python, so the one hard guarantee — every quote shown is
actually in the source — is decided by code, never by an agent's say-so.

## Steps

The invocation is **natural language**, e.g.
`/agreement-audit — read the agreement in contracts/acme.pdf and explain the non-compete clause`
or `/agreement-audit — across the contracts in deals/, which have an MFN and what's the governing law?`

1. **Read the request: resolve the path(s) and the clause(s)/question(s).** Parse the user's prose for:
   - **Where** — the path they name (phrases like "in <path>", "the agreement at <path>", "the
     contracts in <folder>"). A folder → `docs_dir`; a single file → `docs_dir` set to that file;
     several named files → `files: [...]`. If they name no path, default `docs_dir` to `agreements`.
     The path can be **anywhere on disk** — an absolute path (`/Users/you/Downloads/acme.pdf`), a
     `~/...` home path, or a path relative to the current folder. The documents do **not** need to live
     inside this repo; the audit reads them in place and writes only its working copies to `.audit/`.
   - **What** — the clause(s) / question(s) they ask about. Build **one `fields` entry per question**:
     `key` = a short slug (`non_compete`), `label` = a short human label (`Non-compete`), `question` =
     the user's ask rewritten as a clear, self-contained question. Keep their intent: a factual ask
     ("what's the governing law") → a crisp question; an **explain/describe** ask ("explain the nature
     of the non-compete") → keep that framing, so the answer is a short grounded explanation, not a
     one-word value. If the user names **no specific clause**, use the default set: governing law,
     exclusivity, term, termination notice, MFN.
   - Then `Write` `.audit/audit_config.json` = `{"docs_dir" | "files": …, "fields": [{key,label,question}, …]}`.
     **This config — not the `args` global — is how scope reaches the workflow.**

   Example — "read the agreement in contracts/acme.pdf and explain the non-compete clause" →
   ```json
   {"docs_dir": "contracts/acme.pdf",
    "fields": [{"key": "non_compete", "label": "Non-compete",
                "question": "Explain the nature of the non-compete clause."}]}
   ```

   **Cost guard:** ~1 extract + 2 verify agents per (doc × clause). One agreement × one clause is tiny;
   a large corpus (e.g. 25 docs × 5 clauses ≈ 280 agents / millions of subscription tokens, ~10+ min) is
   not — for a big folder, **confirm with the user before auditing the whole corpus**, or suggest a sample.

2. **Run the workflow** (subscription-billed) — scope read from the config, no args:
   `Workflow({ name: "agreement-audit" })`  (if the name doesn't resolve, use
   `Workflow({ scriptPath: ".claude/workflows/agreement-audit.js" })`). It runs `audit_prep`, fans out
   one agent per (document × clause) to extract `{value, verbatim quote, found, confidence}`, then runs
   two diverse-lens verifier agents per finding (a finding is "clean" only if **both** agree; any
   dissent → review queue). It returns `{ doc_ids, skipped, fields, findings }`.

3. **Persist the result:** `Write` the workflow's returned object to `.audit/findings.json`.

4. **Ask where to save the Word report, then run the deterministic consolidation.** First ask the user
   where the report should go (use `AskUserQuestion`): **(a) next to the agreement** (the referenced
   file's folder, or the docs folder), **(b) the Desktop** (`~/Desktop`), or **(c) here in the repo**
   (`.audit/`). Build the path from their choice with a descriptive filename, e.g.
   `<agreement-or-folder-name> — clause audit.docx`. Then (the misquotation guarantee + receipt — code,
   not an agent):
   `Bash: python3 scripts/audit_report.py --findings .audit/findings.json --md .audit/sources --out .audit/report.md --docx "<chosen path>"`
   It re-grounds **every** quote, **drops** any not verbatim-present, and writes the **Word deliverable**
   (coverage receipt, color-coded grid, per-document detail with the verbatim quotes, a review queue with
   reviewer sign-off space) to the chosen location — which may be **anywhere on disk** (the report holds
   the contract's text, so keeping it next to the source or on the Desktop, not in this repo, is fine and
   often preferable). Build the path **inside an existing directory** (the agreement's folder, `~/Desktop`)
   — don't invent a deep new tree from a typo. A Markdown record also goes to `.audit/`. **Tell the user
   the exact saved path** (and that re-running overwrites it).

5. **Report the findings in chat.** The chat response must contain the **actual analysis** — the
   grounded answer(s), the verbatim quotes, and the review queue — **not merely a pointer to the saved
   file**. (The file and the chat carry the same analysis; the file is for keeping/sharing.) If the
   request was a **single targeted question** (one clause, one or a few documents), **lead with the
   direct grounded answer** —
   the explanation, the **verbatim quote**, and the verify status — in prose; the grid + Word report are
   still produced but secondary. For a **portfolio audit** (many docs/clauses), show the **coverage
   receipt** (N examined / grounded / review / dropped / not found), the **doc × clause grid** as a
   readable Markdown table (status emoji + short value per cell), and the **review queue** in full (each flagged
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
