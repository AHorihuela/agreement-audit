# Agreement Audit

A Claude Code skill that audits a folder of legal agreements for the clauses you care about, in a way a
lawyer can trust. It reads every contract, pulls the answer for each clause **with a
verbatim quote**, has independent agents check that the quote actually supports the answer, and then a
deterministic gate **drops any quote that isn't word-for-word in the source.** You get the findings in
chat, a Word report for the team, and a review queue of anything that needs a human.

It's built for the four ways contract Q&A normally goes wrong:

- **Fabricated quotes** — a quote shown is *guaranteed* present in the source (checked in code), or it's dropped.
- **Missed documents** — every file is examined and counted; the report carries a coverage receipt, and a
  cell whose extraction silently failed is flagged "not returned," never passed off as "clause absent."
- **Guessing instead of abstaining** — a clause that genuinely isn't there is recorded as "not found," not
  invented — and every "not found" gets an independent re-search of the document before it's believed.
- **Right quote, wrong conclusion** — independent skeptical/charitable verifiers flag mismatches for human review.

What it does **not** do: replace a lawyer. Grounding proves a quote is *present*, not that the
conclusion is *correct*. The verifiers are Claude (same family as the extractor), so they catch
over-citation and obvious mis-citation but are self-consistency, not ground truth. **A human signs off,
and the true error rate is unknown until you check a sample against ground truth.** The report says so,
plainly, on every page.

## How it works

```
agreements/ ──▶ parse (local)  ──▶  extract per (doc × clause)  ──▶  adversarial verify  ──▶  ground gate (code)  ──▶  report + chat
   .docx           no API           1 agent each, with a            2 agents per finding      drop any quote not        Word + grid +
   .pdf            python only       VERBATIM quote                 (skeptical + charitable)   verbatim in source        review queue
   .md/.txt                                                         + a re-search per
                                                                     "not found"
```

1. **Parse** every agreement to text locally (`python-docx`, PyMuPDF) — no upload, no API.
2. **Extract** one clause per document with a dedicated agent that must read the *whole* document and return a *verbatim* quote (or honestly say "not found").
3. **Verify** each finding with two agents reading opposite priors; a finding is "clean" only if both return and agree the quote supports the answer — a dissent, or one verifier failing to answer, goes to the review queue. Every **"not found" is re-searched** by an independent agent; a disputed absence is queued too.
4. **Ground** every quote in code against the source bytes; a quote that isn't present verbatim is dropped, never shown. Exactly-located quotes carry their **PDF page number**.
5. **Report** the results in chat and as a Word document, then answer follow-up questions.

Extraction and verification run as Claude Code subagents (on your subscription); parsing and the
grounding gate are local Python — the part that gives the hard guarantee.

## Installation

### Global install — works in any session, including Cowork (recommended)

Make `/agreement-audit` available in **every** Claude Code / Cowork session, from any folder:

```bash
git clone https://github.com/AHorihuela/agreement-audit.git
cd agreement-audit
./install.sh
```

`install.sh` copies the skill (with its bundled scripts) to `~/.claude/skills/`, the script-free
workflow to `~/.claude/workflows/` — which Claude Code discovers **by name in every session** — and
installs the parsers into a **venv bundled inside the skill** (so it works on PEP-668 "externally
managed" system Pythons — Homebrew, Debian — where bare `pip install` refuses to run). Then open
Claude Code or **Claude Cowork** in *any* folder and run
`/agreement-audit`; your documents can live anywhere on disk. Or just ask Claude Code:

> Clone https://github.com/AHorihuela/agreement-audit and run its install.sh so /agreement-audit works in any session.

### Try it in-place (no global install)

```bash
git clone https://github.com/AHorihuela/agreement-audit.git
cd agreement-audit
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Open Claude Code in this folder and run `/agreement-audit` — the project skill is auto-discovered.

> The grounding gate and report run as real local code; the skill bundles its scripts and self-locates
> them via `${CLAUDE_SKILL_DIR}`, so it works installed globally or in-place. The multi-agent step needs
> the **Workflow tool** (Claude Code v2.1.154+, a paid plan; on Pro, enable *Dynamic workflows* in
> `/config`). Cowork's support for the Workflow tool isn't documented yet, so for the single-document
> case the skill **falls back to running inline without it**, which keeps the common case working there.

## Usage

**What happens when you run `/agreement-audit`:**

1. It works out the **scope** — which documents and which clauses (defaults: governing law,
   exclusivity, term, termination notice, MFN). For a big folder it confirms scope (or suggests a sample) first.
2. It **reads every contract** and, for each clause, has one agent pull the answer with a *verbatim quote*.
3. **Two more agents** check each quote actually supports the answer; disagreement → the review queue.
4. A deterministic gate **re-checks every quote in the source** and drops any that isn't word-for-word.
5. It **shows you the results in chat** — a coverage receipt, the doc × clause grid, and the review
   queue — and writes a **Word report**, asking where to save it (next to the agreement, your Desktop, or here).
6. You can then **ask follow-up questions** about the results (answered from the grounded findings).

**Just describe what you want, in plain English** — name a path (a folder, a single file, *anywhere on
disk*, including absolute or `~/...` paths outside this repo) and the clause(s) you care about:

```
/agreement-audit — read the agreement in ~/Downloads/acme-rights.pdf and explain the non-compete clause
/agreement-audit — across the contracts in ~/deals/, which have an MFN and what's the governing law?
/agreement-audit — check the termination-for-convenience terms in /Volumes/Legal/2024/*.docx
```

It figures out the path and the clauses from your sentence. If you name no clause, it runs the default
set (governing law, exclusivity, term, termination notice, MFN).

**Try it first** on the included synthetic sample (safe — not a real contract):

```
/agreement-audit examples
```

Then put your own contracts in `agreements/` (`.docx`, `.pdf`, `.md`, `.txt`) and run:

```
/agreement-audit
```

Audits every contract in `agreements/` for the default clauses (governing law, exclusivity, term,
termination notice, MFN). **Start small** — point it at a handful of docs first; for a large corpus it
confirms scope before auditing the whole set.

**Audit a single agreement** (not just a folder):

```
/agreement-audit — audit just agreements/acme-rights-agreement.pdf
```

**Scope to a sample or specific clauses:**

```
/agreement-audit — audit the 5 files in agreements/sample for governing law and termination
```

```
/agreement-audit — just check assignment and change-of-control across all agreements
```

**Ask follow-up questions after the run** (answered from the grounded findings, with the verbatim quotes):

```
which agreements have an MFN clause?
show me the termination language for one of them
why was a clause flagged for review?
what about assignment?        ← not in the run → it offers to re-audit that clause
```

## What you get

- **In chat:** the coverage receipt, the doc × clause grid, and the full review queue: the analysis
  itself, not just a pointer to a file.
- **A Word report (`.docx`) saved where you choose** (next to the agreement, your Desktop, or the repo):
  coverage receipt, a color-coded grid, a per-agreement section with the **verbatim quote under each
  clause** — with the **PDF page number** when exactly located, so a reviewer can open the source
  straight to it — and a **"Needs human review"** queue with reviewer-decision / notes sign-off space.
- **`.audit/report.md`** — the same content as Markdown, for records.

| Mark | Meaning |
|------|---------|
| ✓ | Grounded — the quote is present in the source verbatim (proves the quote is real, **not** that the conclusion is correct) |
| ⚠ | Needs review — the quote may not support the answer (a verifier dissented or didn't answer, low confidence, or a reported absence was disputed) |
| ⛔ | Dropped — the cited quote was **not** found in the source and was removed |
| — | Not found — the clause is genuinely absent from this agreement (each absence is re-searched by an independent agent) |
| ∅ | Not returned — extraction failed for this cell; it needs a re-run and is **not** evidence the clause is absent |

Parsing covers the text layer of PDFs (scanned PDFs are skipped with an OCR hint, e.g. `ocrmypdf`) and
the body text + tables of DOCX files — not footnotes, headers/footers, or text boxes. The report states
this on the page.

## Scope & privacy

- **Start with a sample.** A whole-corpus audit runs many agents — point it at a handful of documents
  first, or let it confirm scope before doing everything. A single run tops out around **250–300
  doc × clause cells** (the workflow's 1000-agent cap); shard a bigger corpus into multiple runs.
- **Your contracts never get committed.** `agreements/`, `.audit/` (parsed text), and generated reports
  (`*.docx`) are gitignored. Confirm your organization's data-handling policy before running any real
  agreement through a model.
- **Documents are untrusted input.** Contracts come from counterparties; the agents are instructed to
  treat their text as data, never as instructions. The grounding gate blocks fabricated quotes, but a
  hostile document trying to steer the analysis is residual LLM risk — which is one more reason the
  review queue ends with a human.

## License

MIT
