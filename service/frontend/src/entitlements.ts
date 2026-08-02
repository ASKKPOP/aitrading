// Frontend mirror of the tier feature gates in service/server/entitlements.py
// (Henry, 2026-08-02) — keep the two in step. The server enforces; this only
// shapes what the UI offers.
//
//   junior:       ⓪ 1-symbol delegation, spot only; system default AI; no
//                 one-off AI Analyst.
//   pro:          + ① simple mode, futures/leverage, own AI by API key,
//                 AI Analyst.
//   professional: + ② N-symbol Full Auto fleets.
//   enterprise:   everything (contract tier).
//
// An unknown/absent plan gets the junior shape — fail closed, matching the
// server. The membership gate already keeps no-plan users out of the app.
export type PlanFeatures = {
  simpleMode: boolean   // ① 간편
  fleetMode: boolean    // ② N종목 자동 편성
  leverage: boolean     // futures / leverage on ⓪ and ①
  analyst: boolean      // AI 애널리스트로 만들기 — 지금 분석
  llmChange: boolean    // own AI by API key (settings LLM target)
}

// Display names + localized per-plan feature detail, shared by the subscribe
// page (registration/upgrade), the settings Membership card and /my-trading.
// TrMap entries are rendered with tr(language, m) at the call site.
import type { TrMap } from './i18n'

export const PLAN_NAMES: Record<string, string> = {
  junior: 'Junior', pro: 'Pro', professional: 'Professional', enterprise: 'Enterprise',
}

export const PLAN_FEATURE_BULLETS: Record<string, TrMap[]> = {
  junior: [
    { ko: '⓪ 1종목 AI 위임 — 현물(spot) 전용', en: '⓪ 1-symbol AI delegation — spot only', ja: '⓪ 1銘柄AI委任 — 現物(スポット)のみ', th: '⓪ มอบหมาย AI 1 เหรียญ — สปอตเท่านั้น', vi: '⓪ Ủy quyền AI 1 mã — chỉ giao ngay (spot)', id: '⓪ Pendelegasian AI 1 simbol — hanya spot' },
    { ko: '시스템 기본 AI 사용', en: 'System default AI', ja: 'システム既定のAIを使用', th: 'ใช้ AI เริ่มต้นของระบบ', vi: 'Dùng AI mặc định của hệ thống', id: 'AI bawaan sistem' },
    { ko: '이메일 · SMS 알림', en: 'Email & SMS alerts', ja: 'メール · SMS通知', th: 'แจ้งเตือนอีเมลและ SMS', vi: 'Cảnh báo qua email & SMS', id: 'Peringatan email & SMS' },
  ],
  pro: [
    { ko: 'Junior의 모든 기능 포함', en: 'Everything in Junior', ja: 'Junior の全機能を含む', th: 'ทุกอย่างใน Junior', vi: 'Mọi tính năng của Junior', id: 'Semua fitur Junior' },
    { ko: '⓪ 1종목 위임 — 현물 + 선물(레버리지)', en: '⓪ 1-symbol delegation — spot + futures (leverage)', ja: '⓪ 1銘柄委任 — 現物 + 先物(レバレッジ)', th: '⓪ มอบหมาย 1 เหรียญ — สปอต + ฟิวเจอร์ส (เลเวอเรจ)', vi: '⓪ Ủy quyền 1 mã — spot + hợp đồng tương lai (đòn bẩy)', id: '⓪ Pendelegasian 1 simbol — spot + futures (leverage)' },
    { ko: '① 간편 모드', en: '① Simple mode', ja: '① かんたんモード', th: '① โหมดง่าย', vi: '① Chế độ đơn giản', id: '① Mode sederhana' },
    { ko: '자체 AI 연결 (내 API 키)', en: 'Bring your own AI (your API key)', ja: '自分のAIを接続 (APIキー)', th: 'เชื่อม AI ของคุณเอง (คีย์ API)', vi: 'Kết nối AI riêng (khóa API của bạn)', id: 'Pakai AI sendiri (kunci API Anda)' },
    { ko: 'AI 애널리스트 — 지금 분석', en: 'AI Analyst — analyze now', ja: 'AIアナリスト — 今すぐ分析', th: 'นักวิเคราะห์ AI — วิเคราะห์ตอนนี้', vi: 'Nhà phân tích AI — phân tích ngay', id: 'Analis AI — analisis sekarang' },
  ],
  professional: [
    { ko: 'Pro의 모든 기능 포함', en: 'Everything in Pro', ja: 'Pro の全機能を含む', th: 'ทุกอย่างใน Pro', vi: 'Mọi tính năng của Pro', id: 'Semua fitur Pro' },
    { ko: '② N종목 자동 편성 (Full Auto)', en: '② N-symbol Full Auto fleets', ja: '② N銘柄の完全自動編成', th: '② จัดพอร์ตอัตโนมัติ N เหรียญ (Full Auto)', vi: '② Tự động hoàn toàn N mã', id: '② Armada Full Auto N simbol' },
  ],
  enterprise: [
    { ko: 'Professional의 모든 기능 포함', en: 'Everything in Professional', ja: 'Professional の全機能を含む', th: 'ทุกอย่างใน Professional', vi: 'Mọi tính năng của Professional', id: 'Semua fitur Professional' },
    { ko: '맞춤 계약 · 전담 지원', en: 'Custom contract · dedicated support', ja: 'カスタム契約 · 専任サポート', th: 'สัญญาแบบกำหนดเอง · ทีมดูแลเฉพาะ', vi: 'Hợp đồng tùy chỉnh · hỗ trợ riêng', id: 'Kontrak khusus · dukungan khusus' },
  ],
}

export function planFeatures(planCode: string | null | undefined): PlanFeatures {
  const p = (planCode || '').toLowerCase()
  const proPlus = p === 'pro' || p === 'professional' || p === 'enterprise'
  const professionalPlus = p === 'professional' || p === 'enterprise'
  return {
    simpleMode: proPlus,
    fleetMode: professionalPlus,
    leverage: proPlus,
    analyst: proPlus,
    llmChange: proPlus,
  }
}
