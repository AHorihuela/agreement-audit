---
name: agreement-audit
description: Audit legal agreements — a whole folder, a single agreement, or specific files anywhere on disk — for the clauses you ask about in natural language (e.g. "explain the non-compete in ~/Downloads/acme.pdf"), with verbatim-grounded citations, adversarial cross-checks, a coverage receipt proving every document was examined, and a human-review queue. Returns the findings in chat AND a Word report, and answers follow-up questions. The agents run on your Claude Code subscription; parsing and the deterministic grounding gate are local Python. Invoke manually.
allowed-tools: Bash, Workflow, Write, Read
disable-model-invocation: true
---

# Agreement clause audit

Run a grounded, multi-agent audit over a folder of agreements, then **report the findings in chat,
write a Word report, and stay available for follow-up questions.** Extraction + verification run as
Claude Code subagents; parsing and the **deterministic verbatim-grounding gate** run as local Python,
so the one hard guarantee — every quote shown is actually in the source — is decided by code, never by
an agent's say-so.

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

   **Scope:** for a large folder, **confirm the scope with the user (or start with a sample)** before
   auditing the whole corpus, so the run matches what they actually want.

2. **Parse the documents (local, no API).** Run the parser yourself — it self-locates via the skill
   directory, so this works from any folder, installed per-project or globally:
   `Bash: python3 "${CLAUDE_SKILL_DIR}/scripts/audit_prep.py" --config .audit/audit_config.json --out .audit`
   It writes the parsed text to `.audit/sources/<doc_id>.md`, a `.audit/manifest.json` (doc_ids, skipped,
   fields), and prints the same. Note any **skipped** docs (with reasons) for the chat summary.

3. **Audit each (document × clause)** — two paths:
   - **Multi-agent (default, best):** `Workflow({ name: "agreement-audit" })`. It reads
     `.audit/manifest.json`, fans out one agent per (doc × clause) to extract `{value, verbatim quote,
     found, confidence}`, then two diverse-lens verifier agents per finding (clean only if **both**
     agree; any dissent → review queue), and returns `{ doc_ids, fields, findings }`. If invoking by
     name fails, retry with `Workflow({ scriptPath: "<CLAUDE_SKILL_DIR>/workflows/agreement-audit.js" })`
     (resolve `${CLAUDE_SKILL_DIR}` first via a quick `echo`).
   - **Inline fallback** (small scope, or a surface without the Workflow tool): do it yourself — read
     each `.audit/sources/<doc_id>.md` and, per clause, produce `{doc, field, label, value, verbatim
     quote, found, confidence}` with `verify_supports: null` (no independent adversarial check ran — the
     report marks these "not verified"). Quote VERBATIM; the deterministic gate in step 4 drops anything
     not actually in the source.

4. **Assemble findings + write the report.** Build `.audit/findings.json` = the manifest's `doc_ids`,
   `skipped`, and `fields` **plus** the `findings` array (from the workflow's return, or your inline
   findings), and `Write` it. Then **ask where to save the Word report** (`AskUserQuestion`):
   **(a) next to the agreement** (the referenced file's folder), **(b) the Desktop** (`~/Desktop`), or
   **(c) here in the repo** (`.audit/`). Build the path inside an **existing** directory with a
   descriptive name, e.g. `<agreement-or-folder-name> — clause audit.docx`. Then run the deterministic
   consolidation (the misquotation guarantee + receipt — code, not an agent):
   `Bash: python3 "${CLAUDE_SKILL_DIR}/scripts/audit_report.py" --findings .audit/findings.json --md .audit/sources --out .audit/report.md --docx "<chosen path>"`
   It re-grounds **every** quote, **drops** any not verbatim-present, and writes the **Word deliverable**
   (coverage receipt, color-coded grid, per-document detail with the verbatim quotes, a review queue with
   reviewer sign-off space) to the chosen path — which may be anywhere on disk (the report holds the
   contract's text, so keeping it next to the source or on the Desktop is fine and often preferable).
   A Markdown record also goes to `.audit/`. **Tell the user the exact saved path** (re-running overwrites it).

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
   parsed, say so plainly — an empty run is not a clean audit. Then name the **exact saved path** of the
   Word report. State plainly, without softening:
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
   Never present a quote you haven't confirmed is in `.audit/sources/<doc>.md`; if in doubt, re-ground it.

## Notes
- **Requirements:** Python 3.10+ with `python-docx` and `PyMuPDF` installed (the parser + grounding gate
  are local Python; the Word report needs python-docx). The scripts self-locate via `${CLAUDE_SKILL_DIR}`
  and the workflow is script-free, so the skill works **installed per-project OR globally** (see the
  README's "Install globally"). Documents may live **anywhere on disk**; `.audit/` (working files +
  sources + the Markdown record) holds confidential text and is gitignored.
- **Scaling:** start small (a few docs, a few clauses); expand once the report shape + review-queue
  load look right on a sample.
