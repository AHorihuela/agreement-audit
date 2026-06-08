# Agreement Audit

A Claude Code skill that audits a folder of legal agreements for the clauses you care about — and does
it in a way a lawyer can trust. It reads every contract, pulls the answer for each clause **with a
verbatim quote**, has independent agents check that the quote actually supports the answer, and then a
deterministic gate **drops any quote that isn't word-for-word in the source.** You get the findings in
chat, a Word report for the team, and a review queue of anything that needs a human.

It's built for the four ways contract Q&A normally goes wrong:

- **Fabricated quotes** — a quote shown is *guaranteed* present in the source (checked in code), or it's dropped.
- **Missed documents** — every file is examined and counted; the report carries a coverage receipt.
- **Guessing instead of abstaining** — a clause that genuinely isn't there is recorded as "not found," not invented.
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
   .md/.txt                                                         clean only if both agree
```

1. **Parse** every agreement to text locally (`python-docx`, PyMuPDF) — no upload, no API cost.
2. **Extract** one clause per document with a dedicated agent that must return a *verbatim* quote (or honestly say "not found").
3. **Verify** each finding with two agents reading opposite priors; a finding is "clean" only if both agree the quote supports the answer — any dissent goes to the review queue.
4. **Ground** every quote in code against the source bytes; a quote that isn't present verbatim is dropped, never shown.
5. **Report** the results in chat and as a Word document, then answer follow-up questions.

The extraction and verification run on your **Claude Code subscription**. Parsing and the grounding
gate are local Python — free, and the part that gives the hard guarantee.

## Installation

### Easiest: let Claude Code set it up

Open [Claude Code](https://claude.com/claude-code) and paste this (point it at wherever you keep
projects):

> Clone https://github.com/AHorihuela/agreement-audit into my Dev folder, set up a Python virtual
> environment, install its requirements, then confirm the `/agreement-audit` skill is available.

Claude Code clones the repo, creates the venv, installs the parsers (`python-docx`, PyMuPDF), and the
skill (`.claude/skills/agreement-audit`) is **auto-discovered** the moment you're working in that
folder — no restart. From then on, run Claude Code **from the `agreement-audit` folder** and use
`/agreement-audit`.

### Manual

```bash
git clone https://github.com/AHorihuela/agreement-audit.git
cd agreement-audit
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Then open Claude Code in this folder.

> **Clone-and-run, not a prompt-only plugin.** The grounding gate and the report run as real local
> code, so the scripts and your contracts live together in the repo — run Claude Code **from the repo
> folder** (that's how the skill finds `scripts/` and your `agreements/`). Copying just the `SKILL.md`
> elsewhere will not work.

## Usage

**What happens when you run `/agreement-audit`:**

1. It confirms the **scope** — which folder of contracts and which clauses (defaults: governing law,
   exclusivity, term, termination notice, MFN). On a big corpus it warns you and suggests a sample first.
2. It **reads every contract** and, for each clause, has one agent pull the answer with a *verbatim quote*.
3. **Two more agents** check each quote actually supports the answer; disagreement → the review queue.
4. A deterministic gate **re-checks every quote in the source** and drops any that isn't word-for-word.
5. It **shows you the results in chat** — a coverage receipt, the doc × clause grid, and the review
   queue — and writes a **Word report** to `.audit/report.docx`.
6. You can then **ask follow-up questions** about the results (answered from the grounded findings).

**Try it first** on the included synthetic sample (safe — not a real contract):

```
/agreement-audit examples
```

Then put your own contracts in `agreements/` (`.docx`, `.pdf`, `.md`, `.txt`) and run:

```
/agreement-audit
```

Audits every contract in `agreements/` for the default clauses (governing law, exclusivity, term,
termination notice, MFN). **Start small** — point it at a handful of docs first; a large corpus is a
long, token-heavy run (it will tell you and ask before doing the whole set).

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
which deals have an MFN clause?
show me the termination language for the Blues amendment
why was the Cavaliers exclusivity flagged for review?
what about assignment?        ← not in the run → it offers to re-audit that clause
```

## What you get

- **In chat:** the coverage receipt, the doc × clause grid, and the full review queue.
- **`/.audit/report.docx`** — a Word report for the team: coverage receipt, a color-coded grid, a
  per-agreement section with the **verbatim quote under each clause** (so a reviewer can verify it and
  add Word comments), and a **"Needs human review"** queue with reviewer-decision / notes sign-off space.
- **`/.audit/report.md`** — the same content as Markdown, for diffs/records.

| Mark | Meaning |
|------|---------|
| ✓ | Grounded — the quote is present in the source verbatim (proves the quote is real, **not** that the conclusion is correct) |
| ⚠ | Needs review — the quote may not support the answer (a verifier dissented, or low confidence) |
| ⛔ | Dropped — the cited quote was **not** found in the source and was removed |
| — | Not found — the clause is genuinely absent from this agreement |

## Cost & privacy

- **Roughly 1 extract + 2 verify agents per (document × clause)**, billed to your Claude Code
  subscription. A full corpus of large contracts is a multi-million-token run — scope to a sample first.
- **Your contracts never get committed.** `agreements/` and `.audit/` (parsed text + the report) are
  gitignored. Confirm your organization's data-handling policy before running any real agreement
  through a model.

## License

MIT
