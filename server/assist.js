/**
 * The assist logic: given a pending record, propose a decision and draft the
 * completion comment the operator would otherwise type.
 *
 * This is the part that saves time. Day 3 measured what an execution is made
 * of - a median ~10s of clicking through a record and writing a templated
 * sentence, with at least one copy-paste per execution. The comment is the
 * deliverable of the work and is fully determined by fields already on the
 * record, so it can be drafted rather than typed.
 *
 * What it does NOT do is decide. Every proposal carries needsReview, and the
 * API never submits on its own. Two reasons, both from the data:
 *
 *   - the submit transport is unverified (Day 4 §5): we know what a submit
 *     does, not how to make one safely;
 *   - policy limits are unknown. Every observed expense case was approved, so
 *     the logs show ranges and never a threshold. A tool that auto-approved
 *     against an inferred limit would be inventing the rule it enforces.
 */

const AMOUNT_RE = /([\d,]+)\s*円/
const CASE_RE = /(INV-\d{4}-\d+|PO-\d{4}-\d+)/

function amountOf(rec) {
  const m = AMOUNT_RE.exec(rec['金額'] ?? '')
  return m ? Number(m[1].replace(/,/g, '')) : null
}

// The case reference is embedded in a label rather than given its own column
// - 区分 reads "請求書承認 INV-2026-7344".
function caseRefOf(rec) {
  for (const v of Object.values(rec)) {
    if (typeof v !== 'string') continue
    const m = CASE_RE.exec(v)
    if (m) return m[1]
  }
  return null
}

// The value as held on the record - this is what gets validated against the
// definition's `variants` list.
function rawVariantOf(defn, rec) {
  if (defn.variant_field) return rec[defn.variant_field] ?? null
  // fin_purchase_order_management: the order type is not on the list screen
  // (Day 4 §6), so it can only come from a record fetch. Until that endpoint
  // is known the variant is genuinely unavailable, and is reported as such
  // rather than guessed.
  return null
}

// The phrase that goes into the comment. Some processes write something other
// than the stored value: fin_invoice_matching holds 種別 = 定常/調整 and
// writes 差異なし承認 / 差異あり要確認. Keeping the two separate matters -
// validating the mapped phrase against the raw list rejected every record.
function commentVariantOf(defn, rec) {
  const raw = rawVariantOf(defn, rec)
  if (raw && defn.variant_map) return defn.variant_map[raw] ?? raw
  return raw
}

export function draftComment(defn, rec) {
  const tpl = defn.comment_template
  const amount = amountOf(rec)
  const values = {
    variant: commentVariantOf(defn, rec),
    amount: amount === null ? null : amount.toLocaleString('en-US'),
    date: rec['期間・詳細'] ?? rec['対象年月'] ?? null,
    item: rec['項目'] ?? null,
    case: caseRefOf(rec),
    qty: null,
    urgency: null,
  }
  const slots = [...tpl.matchAll(/\{(\w+)\}/g)].map((m) => m[1])
  const missing = slots.filter((s) => !values[s])
  if (missing.length) return { comment: null, missing }
  return {
    comment: tpl.replace(/\{(\w+)\}/g, (_, s) => values[s]),
    missing: [],
  }
}

export function propose(defn, rec) {
  const variant = rawVariantOf(defn, rec)
  const amount = amountOf(rec)
  const { comment, missing } = draftComment(defn, rec)

  // Kept separate: a `blocker` is why a person must handle the case, a `note`
  // is context the operator should see but which does not stop the draft.
  // Mixing them put "no policy threshold configured" under a heading that
  // said the record needed attention, on records that were perfectly ready.
  const blockers = []
  const notes = []
  let needsReview = false

  if (variant === null && defn.variant_source === 'record_detail') {
    needsReview = true
    blockers.push(
      'この画面の一覧に区分が表示されないため、レコードを開くまで分類できません ' +
        '(list view does not expose the variant - record fetch required)',
    )
  } else if (variant && !defn.variants.includes(variant)) {
    needsReview = true
    blockers.push(`未知の区分 '${variant}' (variant not in the definition)`)
  }

  const excField = defn.exception_field
  if (excField && (defn.exception_values ?? []).includes(rec[excField])) {
    needsReview = true
    blockers.push(
      `${excField}='${rec[excField]}' は要確認 (flagged exception - handled manually)`,
    )
  }

  if (defn.rule?.threshold == null && amount !== null) {
    notes.push(
      '規程上限が未設定のため金額判定は行っていません ' +
        '(no policy threshold configured - amount not checked)',
    )
  }

  if (missing.length) {
    needsReview = true
    blockers.push(`コメント未生成: ${missing.join(', ')} (unresolved slots)`)
  }

  // A process whose comment asserts a document was checked cannot have that
  // checked by the tool - the portal names the file but never its contents.
  if (defn.requires_document_check) {
    notes.push(
      '関連書類の確認は自動化できません。承認前に書類をご確認ください ' +
        '(the referenced document must be opened by a person)',
    )
  }

  return {
    record: rec, variant, amount, comment,
    needs_review: needsReview,
    blockers, notes,
    reasons: [...blockers, ...notes],   // kept for compatibility
  }
}

export function buildQueue(client, process) {
  const defn = client._defn(process)
  const items = client.listRecords(process).map((r) => propose(defn, r))
  const ready = items.filter((i) => !i.needs_review).length
  return {
    process,
    display_name: defn.display_name,
    states: defn.states,
    confirmation: defn.confirmation,
    counts: client.counts(process),
    total_pending: items.length,
    ready,
    needs_review: items.length - ready,
    items,
  }
}
