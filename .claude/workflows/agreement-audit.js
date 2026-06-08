export const meta = {
  name: "agreement-audit",
  description: "Multi-agent clause audit across a folder of agreements: parse locally, extract each clause per document, adversarially verify each quote supports the answer, and return findings for a deterministic grounded report.",
  phases: [
    { title: "Prepare", detail: "parse agreements to text (local Python, no API)" },
    { title: "Extract", detail: "one agent per (document × clause)" },
    { title: "Verify", detail: "diverse-lens agents check the quote supports the answer" },
  ],
}

// Scope (docs + clauses) is resolved by audit_prep from .audit/audit_config.json (written by the
// skill) — NOT from the workflow `args` global, which is not reliably plumbed to a saved/scriptPath
// workflow. The workflow fans out over whatever Prepare returns.
const MD_DIR = ".audit"
const CONFIG = `${MD_DIR}/audit_config.json`

const PREP_SCHEMA = {
  type: "object", additionalProperties: false,
  properties: {
    doc_ids: { type: "array", items: { type: "string" } },
    skipped: { type: "array", items: { type: "string" } },
    fields: { type: "array", items: {
      type: "object", additionalProperties: false,
      properties: { key: { type: "string" }, label: { type: "string" }, question: { type: "string" } },
      required: ["key", "label", "question"] } },
  },
  required: ["doc_ids", "skipped", "fields"],
}
const EXTRACT_SCHEMA = {
  type: "object", additionalProperties: false,
  properties: { found: { type: "boolean" }, value: { type: "string" },
                quote: { type: "string" }, confidence: { type: "number" } },
  required: ["found", "value", "quote", "confidence"],
}
const VERDICT_SCHEMA = {
  type: "object", additionalProperties: false,
  properties: { supports: { type: "boolean" }, reason: { type: "string" } },
  required: ["supports", "reason"],
}

phase("Prepare")
const prep = await agent(
  `Parse the agreements + resolve the audit scope. Run EXACTLY this (local parse — no API call):\n` +
  `  python3 scripts/audit_prep.py --config ${JSON.stringify(CONFIG)} --out ${JSON.stringify(MD_DIR)}\n\n` +
  `It writes one <doc_id>.md per agreement under ${MD_DIR}/ and prints a JSON object ` +
  `{"doc_ids":[...],"skipped":[...],"fields":[{key,label,question},...]}. Return that object exactly.`,
  { label: "prepare", phase: "Prepare", schema: PREP_SCHEMA })
const docIds = (prep && prep.doc_ids) || []
const FIELDS = (prep && prep.fields) || []
log(`Auditing ${docIds.length} agreements × ${FIELDS.length} clauses = ${docIds.length * FIELDS.length} cells.`)

phase("Extract")
const tasks = []
for (const d of docIds) for (const f of FIELDS) tasks.push({ doc: d, field: f })
const extracted = (await parallel(tasks.map((t) => () =>
  agent(
    `You are auditing ONE clause in ONE agreement. Read the full source:\n` +
    `  cat "${MD_DIR}/${t.doc}.md"\n\n` +
    `QUESTION: ${t.field.question}\n\n` +
    `Answer ONLY from this document. Return:\n` +
    `- found: false if the clause is genuinely ABSENT — do NOT guess or infer.\n` +
    `- value: a concise answer (e.g. the state; "exclusive"/"non-exclusive"; "60 days"; "yes"/"no").\n` +
    `- quote: the SINGLE most on-point passage, copied VERBATIM, character-for-character, from the ` +
    `source text — do NOT paraphrase, normalize, or fix typos/linebreaks (it will be re-checked against ` +
    `the source byte-for-byte). Cite one passage, not several.\n` +
    `- confidence: 0..1.\n` +
    `If not found: found=false, value="not found", quote="".`,
    { label: `extract:${t.doc}:${t.field.key}`, phase: "Extract", schema: EXTRACT_SCHEMA })
    .then((r) => ({ doc: t.doc, field: t.field.key, label: t.field.label, question: t.field.question, ...r }))
))).filter(Boolean)

phase("Verify")
const LENSES = [
  "Adopt a SKEPTICAL prior: assume the quote does NOT support the answer. Look hard for a different value/scope/party, an off-topic span, or a wrong clause. Conclude supports=true only if a does-not-support reading is untenable.",
  "Adopt a CHARITABLE prior: assume the quote DOES support the answer when read in its surrounding context. Conclude supports=false only if the support genuinely fails.",
]
const found = extracted.filter((x) => x.found && (x.quote || "").trim())
const verified = (await parallel(found.map((x) => () =>
  parallel(LENSES.map((lens, i) => () =>
    agent(
      `Does the QUOTE support the ANSWER to the QUESTION, read in its source context?\n\n` +
      `Read the source: cat "${MD_DIR}/${x.doc}.md"\n\n` +
      `QUESTION: ${x.question}\nANSWER: ${x.value}\nQUOTE: «${x.quote}»\n\n` +
      `${lens}\nReturn supports (does the quote back the answer's specific assertion?) + a one-sentence reason.`,
      { label: `verify:${x.doc}:${x.field}:${i}`, phase: "Verify", schema: VERDICT_SCHEMA })
  )).then((vs) => {
    const v = vs.filter(Boolean)
    // Conservative / adversarial: "supported" only if EVERY lens agrees; any refutation -> human review.
    const supports = v.length > 0 && v.every((z) => z.supports)
    const dissent = v.find((z) => !z.supports)
    return { key: `${x.doc}::${x.field}`, supports, reason: dissent ? dissent.reason : (v[0] || {}).reason || "" }
  })
))).filter(Boolean)
const vmap = {}
for (const r of verified) vmap[r.key] = r

const findings = extracted.map((x) => {
  const vr = vmap[`${x.doc}::${x.field}`]
  return {
    doc: x.doc, field: x.field, label: x.label, value: x.value, quote: x.quote,
    found: x.found, confidence: x.confidence,
    verify_supports: vr ? vr.supports : (x.found ? true : null),
    verify_reason: vr ? vr.reason : "",
  }
})

return {
  doc_ids: docIds, skipped: (prep && prep.skipped) || [],
  fields: FIELDS.map((f) => ({ key: f.key, label: f.label })), findings,
}
