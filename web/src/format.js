// Field-name helpers. The portal's own column names are Japanese and the
// operators read them daily, so they are shown verbatim rather than
// translated — an invented English label would be a second vocabulary to
// learn. English appears only in the tool's own chrome.

const SUBJECT_FIELDS = ['氏名']
const DETAIL_FIELDS = ['申請種別', '区分', '項目', '種別']
const HIDDEN_FIELDS = new Set(['ID', 'ステータス'])

export const subjectOf = (rec) =>
  SUBJECT_FIELDS.map((f) => rec[f]).find(Boolean) ?? rec['社員ID'] ?? '—'

export const detailOf = (rec) =>
  DETAIL_FIELDS.map((f) => rec[f]).filter(Boolean).join(' · ')

export const visibleFields = (rec) =>
  Object.entries(rec).filter(
    ([k, v]) => !HIDDEN_FIELDS.has(k) && !k.startsWith('_') && v !== '' && v != null,
  )

export const yen = (n) =>
  n == null ? null : '¥' + n.toLocaleString('ja-JP')

export const clock = (d) =>
  d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
