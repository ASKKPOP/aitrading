import { useCallback, useEffect, useRef, useState } from 'react'
import { API_BASE, useLanguage } from '../appShared'
import { statusLabel } from '../pages/RunsLivePage'
import { tr } from '../i18n'

// Plan 14 — Full Auto (fleet mode). The user sets only N and presses go; the
// AI researches every automatable market, composes N TRADINGs with
// expected-profit theses, keeps the fleet at N until the user stops it, and
// pauses everything at −30% (SMS) / stops everything at −40% (SMS).
//
// Async failure states (build_failed, partial:k/N, replenishing:k/N,
// drawdown_warning) arrive via fleet status_reason — localized here through
// the reasonLabel map, never through the API error boundary (no request is
// in flight when the worker discovers them).

type Fleet = {
  id: number; status: string; status_reason: string | null
  n_runs: number; total_budget_usd: number; risk_appetite: string
  warn_loss_frac: number; stop_loss_frac: number
  warn_latched_at: string | null; warn_acked_at: string | null
  entry_paused_reason: string | null; held_by_master: number
}
type Member = {
  run_id: number; symbol: string; market: string; status: string
  status_reason: string | null; paused_reason: string | null
  run_budget_usd: number | null; realized_pnl_usd: number | null
  thesis: { direction?: string; rationale?: string; confidence?: number } | null
}
type Entitlements = {
  plan: string | null; max_fleet_size: number; default_budget_usd: number
}

// monitorOnly: the always-visible monitor box on /automation — renders nothing
// until an active fleet exists, and never shows the creation form (the create
// modal keeps that). onSelectRun opens a member TRADING's full detail drawer
// (sparkline + event log + pause/stop) via RunsLiveSection.openRunRequest.
export function FleetPanel({ token, monitorOnly = false, onSelectRun }: {
  token: string; monitorOnly?: boolean; onSelectRun?: (runId: number) => void
}) {
  const { language } = useLanguage()
  const T = {
    title: tr(language, { ko: 'N종목 자동 편성 — AI가 전부 알아서', en: 'Full Auto — the AI does everything', ja: '完全自動 — AIがすべて実行', th: 'อัตโนมัติเต็มรูปแบบ — AI จัดการทั้งหมด', vi: 'Tự động hoàn toàn — AI làm tất cả' }),
    desc: tr(language, { ko: 'TRADING 개수만 정하세요 — AI가 전 시장을 리서치해 종목을 고르고, TRADING을 만들어 등록하고, 결과를 다음 판단에 반영하며, 멈출 때까지 개수를 유지합니다. 정지 버튼은 항상 당신에게 있습니다.', en: 'Set only how many TRADINGs — the AI researches the markets, picks the symbols, registers the TRADINGs, feeds every result into the next step, and keeps the count until you stop. You always keep the stop button.', ja: 'TRADING の数だけ設定 — AIが全市場をリサーチして銘柄を選び、TRADING を登録し、結果を次の判断に反映し、停止するまで数を維持します。', th: 'ตั้งแค่จำนวน TRADING — AI รีเสิร์ชตลาด เลือกเหรียญ สร้าง TRADING และรักษาจำนวนจนกว่าคุณจะหยุด', vi: 'Chỉ đặt số lượng TRADING — AI nghiên cứu thị trường, chọn mã, đăng ký TRADING và giữ số lượng cho đến khi bạn dừng.' }),
    nRuns: tr(language, { ko: 'TRADING 개수', en: 'Number of TRADINGs', ja: 'TRADING 数', th: 'จำนวน TRADING', vi: 'Số TRADING' }),
    budget: tr(language, { ko: '총 예산 ($) — 자동 제안됨', en: 'Total budget ($) — pre-filled', ja: '総予算 ($) — 自動提案', th: 'งบรวม ($) — เติมให้อัตโนมัติ', vi: 'Tổng ngân sách ($) — điền sẵn' }),
    advanced: tr(language, { ko: '고급 설정', en: 'Advanced', ja: '詳細設定', th: 'ขั้นสูง', vi: 'Nâng cao' }),
    risk: tr(language, { ko: '위험 성향', en: 'Risk appetite', ja: 'リスク', th: 'ความเสี่ยง', vi: 'Khẩu vị rủi ro' }),
    launch: tr(language, { ko: '🚀 플릿 시작', en: '🚀 Launch fleet', ja: '🚀 フリート開始', th: '🚀 เริ่มฟลีต', vi: '🚀 Khởi chạy' }),
    stopAll: tr(language, { ko: '⏹ 전체 정지 (청산)', en: '⏹ Stop all (flatten)', ja: '⏹ 全停止（清算）', th: '⏹ หยุดทั้งหมด (ปิดสถานะ)', vi: '⏹ Dừng tất cả (đóng lệnh)' }),
    pause: tr(language, { ko: '일시정지', en: 'Pause', ja: '一時停止', th: 'พัก', vi: 'Tạm dừng' }),
    resume: tr(language, { ko: '재개', en: 'Resume', ja: '再開', th: 'ดำเนินต่อ', vi: 'Tiếp tục' }),
    resumeWarning: tr(language, { ko: '경고 확인 후 거래 재개 (본인 책임)', en: 'Resume trading (your responsibility)', ja: '警告を確認して再開（自己責任）', th: 'ดำเนินการต่อ (ความรับผิดชอบของคุณ)', vi: 'Tiếp tục giao dịch (bạn tự chịu trách nhiệm)' }),
    needPlan: tr(language, { ko: '완전자동 플릿은 Pro 이상 요금제에서 사용할 수 있습니다', en: 'Full Auto fleets need a Pro plan or above', ja: '完全自動フリートは Pro 以上のプランで利用できます', th: 'ฟลีตอัตโนมัติต้องใช้แผน Pro ขึ้นไป', vi: 'Đội hình tự động cần gói Pro trở lên' }),
    equity: tr(language, { ko: '평가 자산', en: 'Marked equity', ja: '評価資産', th: 'มูลค่าตามราคาตลาด', vi: 'Giá trị theo thị trường' }),
    monitorTitle: tr(language, { ko: 'N종목 자동 편성 — 실시간 모니터', en: 'Full Auto — live monitor', ja: '完全自動編成 — ライブモニター', th: 'อัตโนมัติเต็มรูปแบบ — มอนิเตอร์สด', vi: 'Tự động hoàn toàn — theo dõi trực tiếp' }),
    buildingHint: tr(language, { ko: 'AI가 시장을 리서치해 TRADING을 구성하는 중입니다 — 완성되는 대로 여기에 하나씩 나타납니다', en: 'The AI is researching the markets and composing the TRADINGs — each one appears here as it is built', ja: 'AIが市場をリサーチして TRADING を構成中 — 完成し次第ここに表示されます', th: 'AI กำลังรีเสิร์ชตลาดและสร้าง TRADING — จะแสดงที่นี่ทีละรายการ', vi: 'AI đang nghiên cứu thị trường và tạo các TRADING — sẽ hiện ở đây khi hoàn thành' }),
    clickHint: tr(language, { ko: '카드를 누르면 개별 TRADING의 실시간 모니터링(차트·이벤트 로그·일시정지/정지)이 열립니다', en: 'Click a card to open that TRADING\'s live monitor (chart · event log · pause/stop)', ja: 'カードをクリックすると各 TRADING のライブモニター（チャート・イベントログ・一時停止/停止）が開きます', th: 'คลิกการ์ดเพื่อเปิดจอมอนิเตอร์สดของ TRADING นั้น (กราฟ · บันทึกเหตุการณ์ · พัก/หยุด)', vi: 'Nhấp vào thẻ để mở màn hình theo dõi trực tiếp của TRADING đó (biểu đồ · nhật ký · tạm dừng/dừng)' }),
    memberBudget: tr(language, { ko: '예산', en: 'Budget', ja: '予算', th: 'งบ', vi: 'Ngân sách' }),
    holdBanner: tr(language, { ko: '⚠️ 마스터 스위치로 전체 보류 중 — 손절/익절 청산은 계속 작동하며, 이미 실행 중인 사이클은 신규 진입 없이 마무리됩니다', en: '⚠️ Held by the master switch — protective exits (SL/TP) stay active; any cycle already executing completes without opening new positions', ja: '⚠️ マスタースイッチで保留中 — SL/TPの保護決済は動作し続けます', th: '⚠️ ถูกพักโดยสวิตช์หลัก — SL/TP ยังทำงาน', vi: '⚠️ Đang giữ bởi công tắc chính — SL/TP vẫn hoạt động' }),
  }
  // fleet status_reason → localized label (the RunsLivePage reasonLabel
  // pattern; unmapped keys render the raw string rather than nothing)
  const reasonLabel = (reason: string | null): string | null => {
    if (!reason) return null
    if (reason.startsWith('partial:')) return tr(language, { ko: `일부만 구성됨 (${reason.slice(8)})`, en: `Built ${reason.slice(8)}`, ja: `一部のみ構成 (${reason.slice(8)})`, th: `สร้างได้ ${reason.slice(8)}`, vi: `Đã tạo ${reason.slice(8)}` })
    if (reason.startsWith('replenishing:')) return tr(language, { ko: `보충 대기 중 (${reason.slice(13)})`, en: `Replenishing (${reason.slice(13)})`, ja: `補充待ち (${reason.slice(13)})`, th: `กำลังเติม (${reason.slice(13)})`, vi: `Đang bổ sung (${reason.slice(13)})` })
    const map: Record<string, any> = {
      build_failed: { ko: '구성 실패 — 후보 종목이 없습니다. 잠시 후 다시 시도하세요', en: 'Build failed — no eligible candidates; try again later', ja: '構成失敗 — 候補がありません', th: 'สร้างไม่สำเร็จ — ไม่มีตัวเลือก', vi: 'Tạo thất bại — không có ứng viên' },
      breaker: { ko: `−${Math.round((fleet?.stop_loss_frac || 0.4) * 100)}% 방어선 작동 — 전체 청산됨`, en: `−${Math.round((fleet?.stop_loss_frac || 0.4) * 100)}% stop rail fired — everything closed`, ja: `−${Math.round((fleet?.stop_loss_frac || 0.4) * 100)}% レール作動 — 全決済`, th: 'ราวหยุดทำงาน — ปิดทั้งหมด', vi: 'Ngưỡng dừng kích hoạt — đã đóng tất cả' },
      drawdown_warning: { ko: '손실 경고 — 신규 진입 정지됨', en: 'Drawdown warning — new entries paused', ja: 'ドローダウン警告 — 新規停止', th: 'เตือนขาดทุน — พักการเข้าใหม่', vi: 'Cảnh báo sụt giảm — tạm dừng lệnh mới' },
      eval_failed: { ko: '가격 데이터 문제로 평가 불가 — 진입 정지', en: 'Equity evaluation failing on stale prices — entries paused', ja: '価格データ問題で評価不可 — 停止', th: 'ประเมินไม่ได้ — พัก', vi: 'Không đánh giá được — tạm dừng' },
      user_stop: { ko: '사용자 정지', en: 'Stopped by you', ja: 'ユーザー停止', th: 'หยุดโดยผู้ใช้', vi: 'Bạn đã dừng' },
      user_master_remove: { ko: '마스터 스위치로 제거됨', en: 'Removed via master switch', ja: 'マスタースイッチで削除', th: 'ลบผ่านสวิตช์หลัก', vi: 'Đã gỡ qua công tắc chính' },
      agent_deleted: { ko: '에이전트가 삭제되어 정지됨', en: 'Stopped — agent deleted', ja: 'エージェント削除により停止', th: 'หยุด — เอเจนต์ถูกลบ', vi: 'Dừng — agent đã xóa' },
      adapt_retired: { ko: '연속 손실로 은퇴됨', en: 'Retired after consecutive losses', ja: '連続損失により引退', th: 'ปลดหลังขาดทุนต่อเนื่อง', vi: 'Nghỉ sau chuỗi thua lỗ' },
    }
    return map[reason] ? tr(language, map[reason]) : reason
  }

  const authHeaders: any = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
  const [ent, setEnt] = useState<Entitlements | null>(null)
  const [fleet, setFleet] = useState<Fleet | null>(null)
  const [members, setMembers] = useState<Member[]>([])
  const [equity, setEquity] = useState<number | null>(null)
  const [n, setN] = useState(3)
  const [budget, setBudget] = useState<number>(0)
  const [risk, setRisk] = useState('balanced')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const fl = await fetch(`${API_BASE}/fleets`, { headers: authHeaders }).then(r => r.json())
      const active = (fl.fleets || []).find((f: Fleet) => f.status !== 'stopped') || (fl.fleets || [])[0] || null
      if (active) {
        const detail = await fetch(`${API_BASE}/fleets/${active.id}`, { headers: authHeaders }).then(r => r.json())
        setFleet(detail.fleet); setMembers(detail.members || [])
        setEquity(detail.equity && detail.equity.ok ? detail.equity.equity : null)
      } else { setFleet(null); setMembers([]) }
    } catch { /* transient */ }
  }, [token])

  useEffect(() => {
    fetch(`${API_BASE}/entitlements/me`, { headers: authHeaders })
      .then(r => r.json())
      .then((e: Entitlements) => { setEnt(e); if (!budget) setBudget(e.default_budget_usd || 1000) })
      .catch(() => setEnt(null))
    load()
  }, [token])

  useEffect(() => {
    if (!fleet || fleet.status === 'stopped') {
      // Discovery poll (monitor box only): the always-visible panel mounts
      // before any fleet exists, so without this a fleet launched from the
      // create modal stays invisible until a full page reload.
      if (!monitorOnly) return
      const id = setInterval(load, 20000)
      return () => clearInterval(id)
    }
    const fast = fleet.status === 'researching' || fleet.status === 'building'
    // 5s while live — member P&L/status changes drive the card blink, so the
    // poll has to be tight enough for the box to visibly breathe.
    const id = setInterval(load, fast ? 2000 : 5000)
    return () => clearInterval(id)
  }, [fleet?.status, load, monitorOnly])

  // Member-card liveness: the panel is poll-driven, so "an event" here is a
  // change in a member's polled snapshot (status / P&L / pause reason) — blink
  // that card for 2s so activity is visible without opening the drawer.
  const [memberFlash, setMemberFlash] = useState<Record<number, number | undefined>>({})
  const memberSig = useRef<Record<number, string>>({})
  const memberTimers = useRef<Record<number, ReturnType<typeof setTimeout>>>({})
  useEffect(() => {
    members.forEach(m => {
      const sig = `${m.status}|${m.realized_pnl_usd ?? ''}|${m.paused_reason ?? ''}`
      const prev = memberSig.current[m.run_id]
      memberSig.current[m.run_id] = sig
      if (prev !== undefined && prev !== sig) {
        setMemberFlash(f => ({ ...f, [m.run_id]: (f[m.run_id] || 0) + 1 }))
        clearTimeout(memberTimers.current[m.run_id])
        memberTimers.current[m.run_id] = setTimeout(
          () => setMemberFlash(f => ({ ...f, [m.run_id]: undefined })), 2000)
      }
    })
  }, [members])
  useEffect(() => () => {
    Object.values(memberTimers.current).forEach(clearTimeout)
  }, [])

  const launch = async () => {
    setBusy(true); setError(null)
    try {
      const r = await fetch(`${API_BASE}/fleets`, {
        method: 'POST', headers: authHeaders,
        body: JSON.stringify({ n_runs: n, total_budget_usd: budget, risk_appetite: risk, idempotency_key: `ui-${Date.now()}` }),
      })
      const body = await r.json()
      if (!r.ok) { setError(body.detail || 'error'); return }
      const s = await fetch(`${API_BASE}/fleets/${body.id}/start`, { method: 'POST', headers: authHeaders })
      if (!s.ok) { setError((await s.json()).detail || 'error'); return }
      await load()
    } finally { setBusy(false) }
  }

  const act = async (path: string) => {
    if (!fleet) return
    setBusy(true)
    try { await fetch(`${API_BASE}/fleets/${fleet.id}/${path}`, { method: 'POST', headers: authHeaders, body: '{}' }); await load() }
    finally { setBusy(false) }
  }

  const chip = (active: boolean): any => ({
    padding: '7px 14px', borderRadius: 20, cursor: 'pointer', fontSize: 13,
    border: active ? '1px solid var(--accent-primary,#c26a45)' : '1px solid var(--border-color,rgba(0,0,0,0.15))',
    background: active ? 'rgba(194,106,69,0.12)' : 'transparent',
    color: active ? 'var(--accent-primary,#c26a45)' : 'inherit',
  })

  const card: any = { background: 'var(--bg-card,#fff)', border: '1px solid var(--border-color,rgba(0,0,0,0.1))', borderRadius: 12, padding: 16,
    ...(monitorOnly ? { marginBottom: 18 } : {}) }

  // The monitor box has nothing to say until a fleet is live; the creation
  // form (and the plan-gate notice) stay in the create modal only.
  if (monitorOnly && (!fleet || fleet.status === 'stopped')) return null

  if (ent && ent.max_fleet_size <= 0) {
    if (monitorOnly) return null
    return <div style={card}><div style={{ fontSize: 13, color: 'var(--text-secondary,#8a8073)' }}>🚀 {T.needPlan}</div></div>
  }

  const warned = !!(fleet && fleet.warn_latched_at && !fleet.warn_acked_at)
  const pnl = fleet && equity !== null ? equity - fleet.total_budget_usd : null

  return (
    <div style={card}>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>🚀 {monitorOnly ? T.monitorTitle : T.title}</div>
      {!monitorOnly && (
        <div style={{ fontSize: 12.5, color: 'var(--text-secondary,#8a8073)', marginBottom: 14 }}>{T.desc}</div>
      )}

      {!fleet || fleet.status === 'stopped' ? (
        <>
          <div style={{ display: 'flex', gap: 16, alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: 10 }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
              {T.nRuns} {ent ? `(max ${ent.max_fleet_size})` : ''}
              <input type="number" min={1} max={ent?.max_fleet_size || 25} value={n}
                onChange={e => setN(Number(e.target.value))}
                style={{ padding: '9px 12px', borderRadius: 8, border: '1px solid var(--border-color,rgba(0,0,0,0.15))', width: 120, background: 'transparent', color: 'inherit' }} />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
              {T.budget}
              <input type="number" min={50} value={budget}
                onChange={e => setBudget(Number(e.target.value))}
                style={{ padding: '9px 12px', borderRadius: 8, border: '1px solid var(--border-color,rgba(0,0,0,0.15))', width: 160, background: 'transparent', color: 'inherit' }} />
            </label>
            <button onClick={launch} disabled={busy || n < 1}
              style={{ padding: '11px 24px', borderRadius: 9, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 700, fontSize: 14, cursor: 'pointer', opacity: busy ? 0.6 : 1 }}>
              {T.launch}
            </button>
            {error && <span style={{ color: '#f0663f', fontSize: 12.5 }}>⚠️ {error}</span>}
          </div>
          <button onClick={() => setShowAdvanced(v => !v)}
            style={{ background: 'none', border: 'none', color: 'var(--text-muted,#a89f92)', fontSize: 12, cursor: 'pointer', padding: 0 }}>
            {showAdvanced ? '▾' : '▸'} {T.advanced}
          </button>
          {showAdvanced && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: 12, marginBottom: 6 }}>{T.risk}</div>
              <div style={{ display: 'flex', gap: 8 }}>
                {['stable', 'balanced', 'aggressive'].map(k => (
                  <button key={k} style={chip(risk === k)} onClick={() => setRisk(k)}>{k}</button>
                ))}
              </div>
            </div>
          )}
          {fleet && fleet.status === 'stopped' && fleet.status_reason && (
            <div style={{ marginTop: 12, fontSize: 12.5, color: 'var(--text-secondary,#8a8073)' }}>
              ℹ️ {reasonLabel(fleet.status_reason)}
            </div>
          )}
        </>
      ) : (
        <>
          {!!fleet.held_by_master && (
            <div style={{ fontSize: 12.5, marginBottom: 10, padding: '8px 12px', borderRadius: 8, background: 'rgba(240,102,63,0.1)' }}>{T.holdBanner}</div>
          )}
          <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', alignItems: 'center', marginBottom: 10 }}>
            <span style={{ fontWeight: 700, textTransform: 'uppercase', fontSize: 12.5 }}>
              {fleet.status}{fleet.status_reason ? ` · ${reasonLabel(fleet.status_reason)}` : ''}
            </span>
            {equity !== null && (
              <span style={{ fontSize: 13 }}>
                {T.equity}: ${equity.toFixed(2)}
                {pnl !== null && (
                  <b style={{ color: pnl >= 0 ? '#2e9e6b' : '#f0663f', marginLeft: 6 }}>
                    {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}
                  </b>
                )}
              </span>
            )}
            <span style={{ fontSize: 11.5, color: 'var(--text-muted,#a89f92)' }}>
              −{Math.round(fleet.warn_loss_frac * 100)}% ⚠︎ / −{Math.round(fleet.stop_loss_frac * 100)}% ⏹
            </span>
          </div>
          {warned && (
            <div style={{ marginBottom: 10, padding: '10px 12px', borderRadius: 8, background: 'rgba(240,102,63,0.12)', fontSize: 12.5 }}>
              ⚠️ {reasonLabel('drawdown_warning')}
              <button onClick={() => act('resume-warning')} disabled={busy}
                style={{ marginLeft: 12, padding: '5px 12px', borderRadius: 7, border: '1px solid #f0663f', background: 'transparent', color: '#f0663f', fontSize: 12, cursor: 'pointer' }}>
                {T.resumeWarning}
              </button>
            </div>
          )}
          {members.length === 0 && (fleet.status === 'researching' || fleet.status === 'building') && (
            <div style={{ fontSize: 12.5, color: 'var(--text-secondary,#8a8073)', marginBottom: 12 }}>
              ⏳ {T.buildingHint}
            </div>
          )}
          {members.length > 0 && onSelectRun && (
            <div style={{ fontSize: 11.5, color: 'var(--text-muted,#a89f92)', marginBottom: 6 }}>
              💡 {T.clickHint}
            </div>
          )}
          <style>{`
            @keyframes sp-run-flash {
              0% { box-shadow: 0 0 0 2.5px var(--sp-flash-color), 0 0 18px 2px var(--sp-flash-color); }
              70% { box-shadow: 0 0 0 2px var(--sp-flash-color), 0 0 8px 0 transparent; }
              100% { box-shadow: 0 0 0 0 transparent; }
            }
            @keyframes sp-live-pulse { 0%, 100% { opacity: 1 } 50% { opacity: .25 } }
          `}</style>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(210px,1fr))', gap: 8, marginBottom: 12 }}>
            {members.map(m => (
              <div key={m.run_id}
                onClick={onSelectRun ? () => onSelectRun(m.run_id) : undefined}
                style={{ border: '1px solid var(--border-color,rgba(0,0,0,0.1))', borderRadius: 9, padding: '9px 11px', fontSize: 12.5,
                  cursor: onSelectRun ? 'pointer' : undefined, position: 'relative' }}>
                {memberFlash[m.run_id] != null && (
                  <div key={memberFlash[m.run_id]} style={{ position: 'absolute', inset: 0, borderRadius: 9,
                    pointerEvents: 'none', ['--sp-flash-color' as any]: 'rgba(12,163,12,0.85)',
                    animation: 'sp-run-flash 2s ease-out forwards' }} />
                )}
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <b>{m.symbol}</b>
                  <span style={{ color: 'var(--text-muted,#a89f92)' }}>{m.market}{m.thesis?.direction === 'short' ? ' · short' : ''}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 3 }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5,
                    color: m.status === 'running' ? '#0ca30c' : m.status === 'paused' ? '#7a68d8' : 'inherit' }}>
                    {m.status === 'running' && (
                      <span style={{ width: 6, height: 6, borderRadius: 6, background: '#0ca30c',
                        display: 'inline-block', animation: 'sp-live-pulse 1.6s ease-in-out infinite' }} />
                    )}
                    {statusLabel(m.status, language)}{m.paused_reason ? ` (${m.paused_reason})` : ''}
                  </span>
                  {m.realized_pnl_usd != null && (
                    <span style={{ color: (m.realized_pnl_usd || 0) >= 0 ? '#2e9e6b' : '#f0663f' }}>
                      {(m.realized_pnl_usd || 0) >= 0 ? '+' : ''}{Number(m.realized_pnl_usd).toFixed(2)}
                    </span>
                  )}
                </div>
                {m.run_budget_usd != null && (
                  <div style={{ marginTop: 3, fontSize: 11.5, color: 'var(--text-muted,#a89f92)' }}>
                    {T.memberBudget}: ${Number(m.run_budget_usd).toFixed(0)}
                  </div>
                )}
                {m.thesis?.rationale && (
                  <div style={{ marginTop: 4, fontSize: 11.5, color: 'var(--text-muted,#a89f92)', overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' as any }}>
                    {m.thesis.rationale}
                  </div>
                )}
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {fleet.status === 'active' && <button style={chip(false)} onClick={() => act('pause')} disabled={busy}>{T.pause}</button>}
            {fleet.status === 'paused' && <button style={chip(false)} onClick={() => act('resume')} disabled={busy}>{T.resume}</button>}
            <button onClick={() => act('stop')} disabled={busy}
              style={{ padding: '8px 18px', borderRadius: 8, border: 'none', background: '#c0392b', color: '#fff', fontWeight: 700, fontSize: 13, cursor: 'pointer' }}>
              {T.stopAll}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
