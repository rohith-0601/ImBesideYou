/**
 * Tests for the drafting logic.
 *
 * Run: node --test server/
 *
 * Two reasons this exists rather than relying on the replay in
 * src/replay.py. The replay measures accuracy against 601 real executions and
 * is the stronger evidence, but it can only test branches that *occurred*
 * during the recording. Some did not:
 *
 *   - 要注意 urgency on a purchase order appears in 7 completion comments but
 *     in no captured detail pane, so the routing it triggers is unverifiable
 *     from data alone;
 *   - the refusal paths (empty comment, unknown variant, missing fetch) are
 *     by definition things operators never did.
 *
 * The fixtures below are shaped exactly like real records - field names and
 * values are copied from portal/records.json and portal/detail_contract.json,
 * not invented - so a test passing here means the same thing it would mean
 * against the portal.
 */

import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { propose, draftComment } from './assist.js'
import { loadDefinitions } from './portalClient.js'

const DEFS = loadDefinitions()

describe('comment drafting', () => {
  it('fills the leave template from list fields alone', () => {
    const rec = {
      ID: 'P2-07040532-009', 社員ID: 'E2002', 氏名: '石田 美奈',
      申請種別: '年次有給休暇', 期間・詳細: '2026-07-15', 部署: '開発部',
      ステータス: '申請中',
    }
    const item = propose(DEFS.hr_leave_application, rec)
    assert.equal(
      item.comment,
      '勤怠申請確認。種別：年次有給休暇。取得日：2026-07-15。問題なし承認。',
    )
    assert.equal(item.needs_review, false)
  })

  it('formats the amount with separators, from the raw 円 string', () => {
    const rec = {
      ID: 'P1-07010448-002', 社員ID: 'E2004', 氏名: '江口 さくら',
      区分: '出張旅費', 金額: '61,460円', 種別: '定常', ステータス: '未処理',
    }
    const item = propose(DEFS.hr_expense_settlement, rec)
    assert.match(item.comment, /金額：61,460円/)
  })

  it('maps 種別 to the phrase the operator writes, not the stored value', () => {
    // fin_invoice_matching stores 定常/調整 but writes 差異なし承認/差異あり要確認.
    // Validating the mapped phrase against the raw variant list once rejected
    // every record; this guards that regression.
    const rec = {
      ID: 'P6-07010448-004', 社員ID: 'V3007', 氏名: '福岡システム設計',
      区分: '請求書承認 INV-2026-7347', 金額: '1,832,962円',
      種別: '定常', ステータス: '未処理',
    }
    const item = propose(DEFS.fin_invoice_matching, rec)
    assert.equal(
      item.comment,
      '請求書照合完了。INV-2026-7347　金額：1,832,962円。差異なし承認。',
    )
    assert.equal(item.needs_review, false)
  })
})

describe('exception routing', () => {
  it('routes 調整 invoices to a person and drafts nothing decisive', () => {
    const rec = {
      ID: 'P6-07010448-007', 社員ID: 'V3004', 氏名: '関西物流サービス',
      区分: '請求書承認 INV-2026-7350', 金額: '1,993,825円',
      種別: '調整', ステータス: '未処理',
    }
    const item = propose(DEFS.fin_invoice_matching, rec)
    assert.equal(item.needs_review, true)
    assert.match(item.blockers.join(' '), /調整/)
  })

  it('routes 要注意 purchase orders to a person', () => {
    // 発注変更 / 要注意 appears in 7 completion comments and in no captured
    // detail pane, so this branch has no data to replay against.
    const rec = {
      ID: 'P10-07054374-009', 社員ID: 'V3003', 氏名: '東京電子工業株式会社',
      項目: '発注管理 PO-2026-5102', 金額: '', ステータス: '未確認',
      _detail: { reason: '発注変更：事務用品　数量 87　合計 3,206,385円　要注意' },
    }
    const item = propose(DEFS.fin_purchase_order_management, rec)
    assert.equal(item.needs_review, true, 'requires a person')
    assert.match(item.blockers.join(' '), /要注意/)
  })

  it('routes 緊急 purchase orders to a person', () => {
    const rec = {
      ID: 'P10-07054374-010', 社員ID: 'V3002', 氏名: '大和商事株式会社',
      項目: '発注管理 PO-2026-5103', 金額: '', ステータス: '未確認',
      _detail: { reason: '緊急発注：測定機器　数量 40　合計 149,920円　緊急' },
    }
    const item = propose(DEFS.fin_purchase_order_management, rec)
    assert.equal(item.needs_review, true)
    assert.match(item.blockers.join(' '), /緊急/)
  })

  it('drafts a routine purchase order once the fetch supplies reason', () => {
    const rec = {
      ID: 'P10-07054374-004', 社員ID: 'V3008', 氏名: '沖縄物流センター',
      項目: '発注管理 PO-2026-5097', 金額: '', ステータス: '未確認',
      _detail: { reason: '定期発注：電子基板ユニット　数量 176　合計 842,336円　通常' },
    }
    const item = propose(DEFS.fin_purchase_order_management, rec)
    assert.equal(item.needs_review, false)
    assert.equal(
      item.comment,
      '発注管理処理。定期発注：電子基板ユニット　数量 176　合計 842,336円　通常。発注書確認・登録完了。',
    )
    assert.equal(item.from_detail, true)
  })
})

describe('refusals', () => {
  it('refuses to draft a purchase order with no detail fetched', () => {
    const rec = {
      ID: 'P10-07010448-005', 社員ID: 'V3006', 氏名: '北陸部品工業株式会社',
      項目: '発注管理 PO-2026-5238', 金額: '', ステータス: '未確認',
    }
    const item = propose(DEFS.fin_purchase_order_management, rec)
    assert.equal(item.needs_review, true)
    assert.equal(item.comment, null)
    // The blocker must name the specified field, so the operator can see this
    // is a missing integration rather than an undecidable case.
    assert.match(item.blockers.join(' '), /reason/)
  })

  it('refuses a variant the definition does not list', () => {
    const rec = {
      ID: 'P2-07040532-099', 社員ID: 'E2002', 氏名: '石田 美奈',
      申請種別: '特別研究休暇', 期間・詳細: '2026-07-15', 部署: '開発部',
      ステータス: '申請中',
    }
    const item = propose(DEFS.hr_leave_application, rec)
    assert.equal(item.needs_review, true)
    assert.match(item.blockers.join(' '), /未知の区分/)
  })

  it('reports unresolved slots rather than emitting a half-filled sentence', () => {
    const rec = {
      ID: 'P2-07040532-098', 社員ID: 'E2002', 氏名: '石田 美奈',
      申請種別: '年次有給休暇', 部署: '開発部', ステータス: '申請中',
    }
    const { comment, missing } = draftComment(DEFS.hr_leave_application, rec)
    assert.equal(comment, null)
    assert.deepEqual(missing, ['date'])
  })
})

describe('advisory notes', () => {
  it('warns that the referenced document cannot be checked by the tool', () => {
    const rec = {
      ID: 'P12-07046495-001', 社員ID: 'V3002', 氏名: '大和商事株式会社',
      申請種別: '取引基本契約 (新規締結)', 期間・詳細: '2026-07-08',
      部署: '新規締結', ステータス: '処理待ち',
    }
    const item = propose(DEFS.inv_contract_management, rec)
    assert.equal(item.needs_review, false, 'drafts, but with a warning')
    assert.match(item.notes.join(' '), /関連書類/)
  })

  it('says the amount was not checked when no threshold is configured', () => {
    const rec = {
      ID: 'P1-07010448-001', 社員ID: 'E2005', 氏名: '岡田 智也',
      区分: '交通費精算', 金額: '6,066円', 種別: '定常', ステータス: '未処理',
    }
    const item = propose(DEFS.hr_expense_settlement, rec)
    assert.match(item.notes.join(' '), /規程上限が未設定/)
  })
})
