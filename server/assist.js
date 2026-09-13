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

function amountOf(rec) {
  const m = AMOUNT_RE.exec(rec['金額'] ?? '')
  return m ? Number(m[1].replace(/,/g, '')) : null
}

function variantOf(defn, rec) {
  if (defn.variant_field) return rec[defn.variant_field] ?? null
  // fin_purchase_order_management: the order type is not on the list screen
  // (Day 4 §6), so it can only come from a record fetch. Until that endpoint
  // is known the variant is genuinely unavailable, and is reported as such
  // rather than guessed.
  return null
}

export function draftComment(defn, rec) {
  const tpl = defn.comment_template
  const amount = amountOf(rec)
  const values = {
    variant: variantOf(defn, rec),
    amount: amount === null ? null : amount.toLocaleString('en-US'),
    date: rec['期間・詳細'] ?? rec['対象年月'] ?? null,
    item: rec['項目'] ?? null,
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
  const variant = variantOf(defn, rec)
  const amount = amountOf(rec)
  const { comment, missing } = draftComment(defn, rec)

  const reasons = []
  let needsReview = false

  if (variant === null && defn.variant_source === 'record_detail') {
    needsReview = true
    reasons.push(
      'この画面の一覧に区分が表示されないため、レコードを開くまで分類できません ' +
        '(list view does not expose the variant - record fetch required)',
    )
  } else if (variant && !defn.variants.includes(variant)) {
    needsReview = true
    reasons.push(`未知の区分 '${variant}' (variant not in the definition)`)
  }

  const excField = defn.exception_field
  if (excField && (defn.exception_values ?? []).includes(rec[excField])) {
    needsReview = true
    reasons.push(
      `${excField}='${rec[excField]}' は要確認 (flagged exception - handled manually)`,
    )
  }

  if (defn.rule?.threshold == null && amount !== null) {
    reasons.push(
      '規程上限が未設定のため金額判定は行っていません ' +
        '(no policy threshold configured - amount not checked)',
    )
  }

  if (missing.length) {
    needsReview = true
    reasons.push(`コメント未生成: ${missing.join(', ')} (unresolved slots)`)
  }

  return { record: rec, variant, amount, comment, needs_review: needsReview, reasons }
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
