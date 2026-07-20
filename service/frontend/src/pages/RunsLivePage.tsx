import { useCallback, useEffect, useMemo, useState } from 'react'
import { API_BASE, useLanguage } from '../appShared'
import { RunSparkline } from '../components/RunSparkline'
import { SymbolSelect } from '../components/SymbolSelect'
import { useRunStream } from '../hooks/useRunStream'
import { Language, tr } from '../i18n'

// Live trading-run dashboard (Plan 10, Phase 8). Route /runs/live.
//   * multi-run grid of small multiples (equity WebGL2 sparkline + status +
//     last-update AGE BADGE — honest staleness for poll-bound markets)
//   * click-through to run detail (price/equity chart + event log)
//   * create form (settings + reporting) and lifecycle controls
// Streaming is via useRunStream (ticketed /ws/runs); the grid equity series
// come from each run's snapshot + live equity events.

interface Props { token?: string | null }

type Run = {
  id: number; symbol: string; market: string; market_type: string
  status: string; status_reason?: string
  config?: any; realized_pnl_usd?: number
  last_cycle_at?: string; last_event_seq?: number
}

const STATUS_COLOR: Record<string, string> = {
  draft: 'var(--text-muted, #898781)',
  armed: '#eda100',
  running: '#0ca30c',
  paused: '#7a68d8',
  stopping: '#eb6834',
  stopped: '#898781',
}

// A raw status ("stopped") and a raw reason ("stop_event:max_loss") tell the
// user nothing — the reason in particular is the only thing that explains WHY
// a TRADING ended. Both are rendered through these maps in the active locale.
const STATUS_TEXT: Record<string, Record<Language, string>> = {
  draft: { ko: '준비됨', en: 'Ready', ja: '準備完了', th: 'พร้อม', vi: 'Sẵn sàng' },
  armed: { ko: '대기 중', en: 'Waiting', ja: '待機中', th: 'รออยู่', vi: 'Đang chờ' },
  running: { ko: '실행 중', en: 'Running', ja: '実行中', th: 'กำลังทำงาน', vi: 'Đang chạy' },
  paused: { ko: '일시정지', en: 'Paused', ja: '一時停止', th: 'หยุดชั่วคราว', vi: 'Tạm dừng' },
  stopping: { ko: '정지하는 중', en: 'Stopping', ja: '停止処理中', th: 'กำลังหยุด', vi: 'Đang dừng' },
  stopped: { ko: '정지됨', en: 'Stopped', ja: '停止済み', th: 'หยุดแล้ว', vi: 'Đã dừng' },
}

const REASON_TEXT: Record<string, Record<Language, string>> = {
  // NOT "you pressed Stop" — this reason only means a stop request arrived on
  // the agent token, which is just as often a QA session or a script as it is
  // the owner clicking the button. Say what actually happened, not who did it.
  user_stop: {
    ko: '수동 정지 — 이 TRADING에 정지 요청이 들어왔습니다 (정지 버튼 또는 API)',
    en: 'Stopped by hand — a Stop request arrived for this TRADING (button or API)',
    ja: '手動停止 — この TRADING に停止リクエストが届きました（ボタンまたは API）',
    th: 'หยุดด้วยมือ — มีคำขอหยุดส่งมาที่ TRADING นี้ (ปุ่มหรือ API)',
    vi: 'Dừng thủ công — có yêu cầu Dừng gửi tới TRADING này (nút hoặc API)' },
  user_pause: {
    ko: '수동 일시정지 — 일시정지 요청이 들어왔습니다',
    en: 'Paused by hand — a Pause request arrived',
    ja: '手動一時停止 — 一時停止リクエストが届きました',
    th: 'หยุดชั่วคราวด้วยมือ — มีคำขอหยุดชั่วคราวส่งมา',
    vi: 'Tạm dừng thủ công — có yêu cầu Tạm dừng' },
  'stop_event:profit_target': {
    ko: '목표 수익에 도달했습니다 — 같은 설정으로 새 TRADING이 자동 시작됩니다',
    en: 'Profit target reached — a new TRADING with the same settings starts automatically',
    ja: '目標利益に到達しました — 同じ設定で新しい TRADING が自動開始されます',
    th: 'ถึงเป้ากำไรแล้ว — TRADING ใหม่ด้วยการตั้งค่าเดิมจะเริ่มอัตโนมัติ',
    vi: 'Đã đạt mục tiêu lợi nhuận — một TRADING mới với cùng thiết lập sẽ tự khởi động' },
  'stop_event:max_trades': {
    ko: '설정한 최대 거래 횟수를 채웠습니다 — 같은 설정으로 새 TRADING이 자동 시작됩니다',
    en: 'Trade limit reached — a new TRADING with the same settings starts automatically',
    ja: '最大取引回数に達しました — 同じ設定で新しい TRADING が自動開始されます',
    th: 'ครบจำนวนเทรดสูงสุด — TRADING ใหม่ด้วยการตั้งค่าเดิมจะเริ่มอัตโนมัติ',
    vi: 'Đã đạt giới hạn số lệnh — một TRADING mới với cùng thiết lập sẽ tự khởi động' },
  'stop_event:max_loss': {
    ko: '손실 한도에 도달해 잔고 보호를 위해 멈췄습니다 — 자동 재시작하지 않습니다',
    en: 'Loss limit hit — stopped to protect your balance, and it does NOT auto-restart',
    ja: '損失上限に達したため停止しました — 自動再開はしません',
    th: 'ถึงขีดจำกัดขาดทุน — หยุดเพื่อป้องกันยอดเงิน และจะไม่เริ่มใหม่อัตโนมัติ',
    vi: 'Chạm giới hạn lỗ — dừng để bảo vệ số dư, và KHÔNG tự khởi động lại' },
  'stop_event:at_time': {
    ko: '예약한 종료 시각이 되었습니다', en: 'The scheduled end time arrived',
    ja: '予約した終了時刻になりました', th: 'ถึงเวลาสิ้นสุดที่ตั้งไว้',
    vi: 'Đã đến thời điểm kết thúc đã đặt' },
  'stop_event:price_cross': {
    ko: '설정한 가격선을 통과했습니다', en: 'Price crossed the line you set',
    ja: '設定した価格ラインを超えました', th: 'ราคาข้ามเส้นที่คุณตั้งไว้',
    vi: 'Giá đã vượt mức bạn đặt' },
  synthetic_liquidation: {
    ko: '숏 손실이 담보 전액에 도달해 강제 청산했습니다',
    en: 'Force-closed — the short’s loss reached your full collateral',
    ja: 'ショートの損失が担保全額に達し強制決済しました',
    th: 'ปิดบังคับ — ขาดทุนของ short ถึงหลักประกันทั้งหมด',
    vi: 'Đóng bắt buộc — lỗ của lệnh short đã chạm toàn bộ ký quỹ' },
  stop_eval_failed: {
    ko: '가격이 오래되어 정지 조건을 확인할 수 없어 안전하게 멈췄습니다',
    en: 'Stopped for safety — prices went stale, so stop conditions could not be checked',
    ja: '価格が古く停止条件を確認できないため安全のため停止しました',
    th: 'หยุดเพื่อความปลอดภัย — ราคาเก่าเกินไปจึงตรวจเงื่อนไขหยุดไม่ได้',
    vi: 'Dừng để an toàn — giá quá cũ nên không kiểm tra được điều kiện dừng' },
  stop_eval_recovered: {
    ko: '가격 수신이 회복되어 다시 실행합니다', en: 'The price feed recovered — running again',
    ja: '価格配信が回復し再開しました', th: 'ราคากลับมาปกติ — ทำงานต่อ',
    vi: 'Nguồn giá đã hồi phục — chạy lại' },
  positions_held: {
    ko: '정지했지만 포지션은 손절·익절 감시 아래 그대로 유지됩니다',
    en: 'Stopped, but the position is kept open under the stop-loss / take-profit watcher',
    ja: '停止しましたがポジションは損切り・利確監視下で保持されます',
    th: 'หยุดแล้ว แต่สถานะยังเปิดอยู่ภายใต้ตัวเฝ้า SL/TP',
    vi: 'Đã dừng, nhưng vị thế vẫn mở dưới bộ theo dõi cắt lỗ / chốt lời' },
  stop_complete: {
    ko: '정상적으로 종료했습니다', en: 'Finished normally', ja: '正常に終了しました',
    th: 'จบการทำงานตามปกติ', vi: 'Đã kết thúc bình thường' },
  armed_timeout: {
    ko: '대기 시간 안에 시작 조건이 발생하지 않았습니다',
    en: 'The start condition never fired within the waiting window',
    ja: '待機時間内に開始条件が発生しませんでした',
    th: 'เงื่อนไขเริ่มไม่เกิดขึ้นภายในเวลารอ',
    vi: 'Điều kiện khởi động không xảy ra trong thời gian chờ' },
  start_condition_fired: {
    ko: '시작 조건이 충족되어 실행에 들어갔습니다', en: 'The start condition fired',
    ja: '開始条件が成立しました', th: 'เงื่อนไขเริ่มทำงานแล้ว', vi: 'Điều kiện khởi động đã kích hoạt' },
  stop_conditions_tightened: {
    ko: '정지 조건을 더 엄격하게 변경했습니다', en: 'Stop conditions were tightened',
    ja: '停止条件を厳しくしました', th: 'ปรับเงื่อนไขหยุดให้เข้มขึ้น',
    vi: 'Điều kiện dừng đã được siết chặt' },
  created: {
    ko: '생성되었습니다', en: 'Created', ja: '作成しました', th: 'สร้างแล้ว', vi: 'Đã tạo' },
}

function statusLabel(status: string | undefined, lang: Language): string {
  if (!status) return ''
  return STATUS_TEXT[status] ? tr(lang, STATUS_TEXT[status]) : status
}

// Falls back to the raw reason so a newly-added backend reason still shows
// something actionable instead of silently disappearing.
function reasonLabel(reason: string | undefined, lang: Language): string {
  if (!reason) return ''
  return REASON_TEXT[reason] ? tr(lang, REASON_TEXT[reason]) : reason
}

function ageLabel(ts: string | undefined, lang: Language): string {
  if (!ts) return tr(lang, { ko: '대기', en: 'idle', ja: '待機', th: 'ว่าง', vi: 'chờ' })
  const secs = Math.max(0, (Date.now() - new Date(ts).getTime()) / 1000)
  if (secs < 60) return `${Math.round(secs)}s`
  if (secs < 3600) return `${Math.round(secs / 60)}m`
  return `${Math.round(secs / 3600)}h`
}

// The whole live-runs experience (grid + create + detail drawer), embeddable:
// /automation renders it as its primary section (embedded), while the old
// /runs/live route now redirects there. `reloadKey` lets a parent force a
// reload after it creates a run out-of-band.
export function RunsLiveSection({ token, embedded = false, reloadKey = 0 }: {
  token?: string | null; embedded?: boolean; reloadKey?: number
}) {
  const { language } = useLanguage()
  const [runs, setRuns] = useState<Run[]>([])
  const [equityByRun, setEquityByRun] = useState<Record<number, number[]>>({})
  const [selected, setSelected] = useState<number | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [err, setErr] = useState('')
  // Structured start conflict (409 with resolvable position/rules) — rendered
  // as a modal offering one-click "close position + disable rules, then start".
  const [conflict, setConflict] = useState<{
    runId: number; message: string
    conflicts: { position: any; rule_ids: number[] }
  } | null>(null)

  const auth = useMemo(() => ({ 'Content-Type': 'application/json',
    Authorization: `Bearer ${token}` }), [token])

  const load = useCallback(async () => {
    if (!token) return
    try {
      const r = await fetch(`${API_BASE}/runs`, { headers: auth })
      if (r.ok) setRuns((await r.json()).runs || [])
    } catch { /* transient */ }
  }, [token, auth])

  useEffect(() => { load() }, [load, reloadKey])
  useEffect(() => {
    const id = setInterval(load, 20000)  // low-frequency reconcile; WS carries live
    return () => clearInterval(id)
  }, [load])

  const activeRunIds = useMemo(
    () => runs.filter((r) => ['armed', 'running', 'paused', 'stopping'].includes(r.status))
      .map((r) => r.id),
    [runs])
  const { connected, eventsByRun, tickByRun } = useRunStream(token || null, activeRunIds)

  // seed equity series from snapshots for the grid
  useEffect(() => {
    for (const run of runs) {
      if (equityByRun[run.id]) continue
      fetch(`${API_BASE}/runs/${run.id}/events?limit=500`, { headers: auth })
        .then((r) => (r.ok ? r.json() : { events: [] }))
        .then((d) => {
          const series = (d.events || [])
            .filter((e: any) => e.event_type === 'equity')
            .map((e: any) => Number(e.payload?.total ?? 0))
          setEquityByRun((prev) => ({ ...prev, [run.id]: series.length ? series : [0] }))
        })
        .catch(() => { /* transient */ })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runs])

  // append live equity events into the grid series
  useEffect(() => {
    setEquityByRun((prev) => {
      const next = { ...prev }
      for (const [ridStr, events] of Object.entries(eventsByRun)) {
        const rid = Number(ridStr)
        const eqs = events.filter((e) => e.event_type === 'equity')
        if (!eqs.length) continue
        const base = prev[rid] || [0]
        const merged = base.concat(eqs.map((e) => Number(e.payload?.total ?? 0)))
        next[rid] = merged.length > 4096 ? merged.slice(merged.length - 4096) : merged
      }
      return next
    })
  }, [eventsByRun])

  async function act(id: number, action: string, body?: any) {
    setErr('')
    try {
      const r = await fetch(`${API_BASE}/runs/${id}/${action}`, {
        method: 'POST', headers: auth,
        body: body ? JSON.stringify(body) : undefined,
      })
      if (!r.ok) {
        const detail = (await r.json()).detail
        if (r.status === 409 && detail && typeof detail === 'object' && detail.conflicts
            && (detail.conflicts.position || detail.conflicts.rule_ids?.length)) {
          setConflict({ runId: id, message: detail.message, conflicts: detail.conflicts })
        } else {
          const msg = typeof detail === 'object' ? detail?.message : detail
          setErr(msg || T.actionFailed)
        }
      }
      await load()
    } catch { setErr(T.networkError) }
  }

  async function del(id: number) {
    await fetch(`${API_BASE}/runs/${id}`, { method: 'DELETE', headers: auth })
    if (selected === id) setSelected(null)
    await load()
  }

  // "AI Automation Master" (the section) and "TRADING" (one box) are product
  // names — they stay verbatim in every locale; the sentences around them do not.
  const T = {
    title: 'AI Automation Master',
    subtitle: tr(language, {
      ko: '각 TRADING은 서버에서 계속 실행됩니다. 목표(익절·최대 거래 횟수)를 채우고 멈추면 같은 설정의 TRADING이 자동으로 이어서 시작됩니다. 가격 갱신 주기 때문에 데이터 나이(⧗)도 함께 확인하세요.',
      en: 'Each TRADING keeps running on the server. When one stops because it reached its goal (profit target or trade limit), a new TRADING with the same settings takes over automatically. Watch the data-age badge (⧗) — polled markets update on an interval.',
      ja: '各 TRADING はサーバーで実行され続けます。目標（利確・最大取引回数）に達して停止すると、同じ設定の TRADING が自動的に引き継ぎます。ポーリング市場のためデータ経過時間（⧗）にも注意。',
      th: 'แต่ละ TRADING ทำงานต่อเนื่องบนเซิร์ฟเวอร์ เมื่อหยุดเพราะถึงเป้าหมาย (เป้ากำไรหรือจำนวนเทรด) TRADING ใหม่ที่ตั้งค่าเหมือนกันจะทำงานต่อทันที ดูอายุข้อมูล (⧗) ด้วย',
      vi: 'Mỗi TRADING chạy liên tục trên máy chủ. Khi dừng vì đạt mục tiêu (chốt lời hoặc giới hạn lệnh), một TRADING mới cùng thiết lập sẽ tiếp quản tự động. Hãy xem nhãn tuổi dữ liệu (⧗).' }),
    newRun: tr(language, { ko: '새 TRADING', en: 'New TRADING', ja: '新しい TRADING',
      th: 'TRADING ใหม่', vi: 'TRADING mới' }),
    empty: tr(language, { ko: '아직 TRADING이 없습니다.', en: 'No TRADING yet.',
      ja: 'TRADING はまだありません。', th: 'ยังไม่มี TRADING', vi: 'Chưa có TRADING nào.' }),
    live: tr(language, { ko: '실시간', en: 'live', ja: 'ライブ', th: 'สด', vi: 'trực tiếp' }),
    offline: tr(language, { ko: '오프라인', en: 'offline', ja: 'オフライン', th: 'ออฟไลน์', vi: 'ngoại tuyến' }),
    actionFailed: tr(language, { ko: '요청을 처리하지 못했습니다.', en: 'That action did not go through.',
      ja: '操作を実行できませんでした。', th: 'ดำเนินการไม่สำเร็จ', vi: 'Thao tác không thành công.' }),
    networkError: tr(language, { ko: '네트워크 오류 — 연결을 확인한 뒤 다시 시도하세요.',
      en: 'Network error — check your connection and try again.',
      ja: 'ネットワークエラー — 接続を確認して再試行してください。',
      th: 'เครือข่ายผิดพลาด — ตรวจการเชื่อมต่อแล้วลองใหม่',
      vi: 'Lỗi mạng — kiểm tra kết nối rồi thử lại.' }),
  }

  if (!token) {
    return <div className="page"><p className="muted">
      {tr(language, { ko: '에이전트 로그인이 필요합니다.', en: 'Agent login required.',
        ja: 'エージェントログインが必要です。', th: 'ต้องเข้าสู่ระบบ', vi: 'Cần đăng nhập' })}
    </p></div>
  }

  return (
    <div className={embedded ? undefined : 'page'}
      style={embedded ? undefined : { padding: '20px 24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        gap: 12, flexWrap: 'wrap' }}>
        <div>
          {embedded
            ? <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)' }}>📈 {T.title}</div>
            : <h1 style={{ margin: 0, fontSize: 22 }}>{T.title}</h1>}
          <p className="muted" style={{ margin: '4px 0 0', maxWidth: 680, fontSize: 13 }}>
            {T.subtitle}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: connected ? '#0ca30c' : '#898781',
            display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 8, height: 8, borderRadius: 8,
              background: connected ? '#0ca30c' : '#898781', display: 'inline-block' }} />
            {connected ? T.live : T.offline}
          </span>
          <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
            + {T.newRun}
          </button>
        </div>
      </div>

      {err && <div style={{ color: '#d03b3b', marginTop: 10, fontSize: 13 }}>{err}</div>}

      {showCreate && (
        <CreateRunForm token={token}
          onDone={(startError, conflictInfo) => {
            setShowCreate(false)
            if (conflictInfo) setConflict(conflictInfo)
            else if (startError) setErr(startError)
            load()
          }}
          onCancel={() => setShowCreate(false)} language={language} />
      )}

      {runs.length === 0 && !showCreate && (
        <p className="muted" style={{ marginTop: 24 }}>{T.empty}</p>
      )}

      <div style={{ display: 'grid', gap: 12, marginTop: 18,
        gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))' }}>
        {runs.map((run) => {
          const tick = tickByRun[run.id]
          const pnl = Number(run.realized_pnl_usd || 0)
          const pnlColor = pnl > 0 ? '#0ca30c' : pnl < 0 ? '#d03b3b' : 'var(--text-muted,#898781)'
          const ageTs = run.status === 'running' ? (tick?.ts || run.last_cycle_at) : run.last_cycle_at
          return (
            <div key={run.id}
              onClick={() => setSelected(run.id)}
              style={{ background: 'var(--bg-card,#fff)', border: '1px solid var(--border-color,rgba(0,0,0,0.1))',
                borderRadius: 12, padding: 14, cursor: 'pointer' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <strong style={{ fontSize: 15 }}>{run.symbol}
                  <span className="muted" style={{ fontSize: 11, marginLeft: 6 }}>
                    {run.market}{run.market_type === 'futures' ? ' · fut' : ''}</span>
                </strong>
                <span style={{ fontSize: 11, fontWeight: 600,
                  color: STATUS_COLOR[run.status] || '#898781' }}>
                  {statusLabel(run.status, language)}</span>
              </div>
              {/* the reason is the whole answer to "why did this stop?" —
                  never leave a stopped/paused box without it */}
              {['stopped', 'stopping', 'paused'].includes(run.status) && run.status_reason && (
                <div className="muted" style={{ fontSize: 11, marginTop: 4, lineHeight: 1.45 }}>
                  {reasonLabel(run.status_reason, language)}
                </div>
              )}
              <div style={{ marginTop: 8 }}>
                <RunSparkline values={equityByRun[run.id] || [0]}
                  color={pnl < 0 ? 'rgb(208,59,59)' : 'rgb(12,163,12)'} height={44} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between',
                alignItems: 'center', marginTop: 8, fontSize: 12 }}>
                <span style={{ color: pnlColor, fontWeight: 600 }}>
                  {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}</span>
                <span className="muted" title="last data update"
                  style={{ fontSize: 11 }}>⧗ {ageLabel(ageTs, language)}</span>
              </div>
            </div>
          )
        })}
      </div>

      {selected !== null && (
        <RunDetail runId={selected} token={token}
          events={eventsByRun[selected] || []}
          tick={tickByRun[selected]}
          onClose={() => setSelected(null)}
          onAct={act} onDelete={del} language={language} />
      )}

      {conflict && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 60 }}>
          <div style={{ width: 'min(440px, calc(100% - 32px))', background: 'var(--bg-card,#fff)',
            border: '1px solid var(--border-color,rgba(0,0,0,0.15))', borderRadius: 12,
            padding: 20 }}>
            <strong style={{ fontSize: 15 }}>
              {tr(language, { ko: '시작 차단 — 해결 가능한 충돌', en: 'Start blocked — resolvable conflicts',
                ja: '開始ブロック — 解決可能な競合', th: 'เริ่มไม่ได้ — ความขัดแย้งที่แก้ได้',
                vi: 'Bị chặn — xung đột có thể xử lý' })}
            </strong>
            <ul style={{ margin: '12px 0', paddingLeft: 18, fontSize: 13, lineHeight: 1.6 }}>
              {conflict.conflicts.position && (
                <li>{tr(language, {
                  ko: `이 심볼에 열린 포지션이 있습니다 (${conflict.conflicts.position.side} ${conflict.conflicts.position.quantity})`,
                  en: `An open position exists on this symbol (${conflict.conflicts.position.side} ${conflict.conflicts.position.quantity})`,
                  ja: `このシンボルに未決済ポジションがあります (${conflict.conflicts.position.side} ${conflict.conflicts.position.quantity})`,
                  th: `มีสถานะเปิดอยู่ (${conflict.conflicts.position.side} ${conflict.conflicts.position.quantity})`,
                  vi: `Đang có vị thế mở (${conflict.conflicts.position.side} ${conflict.conflicts.position.quantity})` })}</li>
              )}
              {conflict.conflicts.rule_ids?.length > 0 && (
                <li>{tr(language, {
                  ko: `자동실행 automation 규칙 ${conflict.conflicts.rule_ids.length}개가 같은 심볼에 켜져 있습니다`,
                  en: `${conflict.conflicts.rule_ids.length} auto-executing automation rule(s) enabled on this symbol`,
                  ja: `同一シンボルで自動実行ルールが${conflict.conflicts.rule_ids.length}件有効です`,
                  th: `กฎอัตโนมัติ ${conflict.conflicts.rule_ids.length} ข้อเปิดอยู่บนสัญลักษณ์นี้`,
                  vi: `${conflict.conflicts.rule_ids.length} quy tắc tự động đang bật trên mã này` })}</li>
              )}
            </ul>
            <p className="muted" style={{ fontSize: 12, margin: '0 0 14px' }}>
              {tr(language, {
                ko: '런의 손익 귀속을 정확히 유지하려면 런은 항상 빈 포지션에서 시작해야 합니다. 아래 버튼 하나로 포지션을 현재가에 청산하고 규칙을 끈 뒤 바로 시작합니다.',
                en: 'Runs must start flat so run P&L attribution stays honest. One click closes the position at the current mark, disables the rules, and starts the run.',
                ja: 'ランの損益帰属を正確に保つため、ランはフラットな状態から開始する必要があります。ワンクリックで現在値でクローズし、ルールを無効化して開始します。',
                th: 'รันต้องเริ่มจากสถานะว่างเพื่อให้ P&L ถูกต้อง คลิกเดียวเพื่อปิดสถานะ ปิดกฎ แล้วเริ่มรัน',
                vi: 'Phiên phải bắt đầu không vị thế để P&L chính xác. Một cú nhấp sẽ đóng vị thế theo giá hiện tại, tắt quy tắc và bắt đầu.' })}
            </p>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn" onClick={() => setConflict(null)}>
                {tr(language, { ko: '취소', en: 'Cancel', ja: 'キャンセル', th: 'ยกเลิก', vi: 'Hủy' })}
              </button>
              <button className="btn btn-primary" onClick={() => {
                const id = conflict.runId
                setConflict(null)
                act(id, 'start', { resolve_conflicts: true })
              }}>
                {tr(language, {
                  ko: '청산·규칙 해제 후 시작', en: 'Close & disable, then start',
                  ja: 'クローズ＆無効化して開始', th: 'ปิดสถานะและกฎ แล้วเริ่ม',
                  vi: 'Đóng & tắt, rồi bắt đầu' })}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export function RunsLivePage({ token }: Props) {
  return (
    <div className="page" style={{ padding: '20px 24px' }}>
      <RunsLiveSection token={token} />
    </div>
  )
}

function RunDetail({ runId, token, events, tick, onClose, onAct, onDelete, language }: {
  runId: number; token: string; events: any[]; tick: any
  onClose: () => void
  onAct: (id: number, action: string, body?: any) => void
  onDelete: (id: number) => void
  language: Language
}) {
  const [snap, setSnap] = useState<any>(null)
  const auth = { Authorization: `Bearer ${token}` }

  useEffect(() => {
    fetch(`${API_BASE}/runs/${runId}/snapshot`, { headers: auth })
      .then((r) => (r.ok ? r.json() : null)).then(setSnap).catch(() => setSnap(null))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, events.length])

  const equity = useMemo(() => {
    const base = (snap?.pnl ? [Number(snap.pnl.total || 0)] : [0])
    const live = events.filter((e) => e.event_type === 'equity')
      .map((e) => Number(e.payload?.total ?? 0))
    return base.concat(live)
  }, [snap, events])

  const run = snap?.run
  const status = run?.status
  const canStop = ['armed', 'running', 'paused'].includes(status)
  const log = events.slice().reverse().slice(0, 60)

  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0,
      background: 'rgba(0,0,0,0.45)', display: 'flex', justifyContent: 'flex-end', zIndex: 50 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: 'min(560px, 100%)',
        height: '100%', overflowY: 'auto', background: 'var(--bg-primary,#fff)',
        borderLeft: '1px solid var(--border-color,rgba(0,0,0,0.1))', padding: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ margin: 0, fontSize: 18 }}>
            {run ? `${run.symbol} · ${run.market}` : `TRADING #${runId}`}</h2>
          <button className="btn" onClick={onClose}>✕</button>
        </div>
        {run && (
          <>
            <div style={{ marginTop: 4, fontSize: 12, color: STATUS_COLOR[status] || '#898781',
              fontWeight: 600 }}>
              {statusLabel(status, language)}
            </div>
            {run.status_reason && (
              <div className="muted" style={{ fontSize: 12, marginTop: 3, lineHeight: 1.5 }}>
                {reasonLabel(run.status_reason, language)}
              </div>
            )}
          </>
        )}

        {snap?.pnl && (
          <div style={{ display: 'flex', gap: 18, marginTop: 12, fontSize: 13 }}>
            <div><span className="muted">P&amp;L </span>
              <strong style={{ color: snap.pnl.total >= 0 ? '#0ca30c' : '#d03b3b' }}>
                {snap.pnl.total >= 0 ? '+' : ''}${Number(snap.pnl.total).toFixed(2)}</strong></div>
            <div><span className="muted">
              {tr(language, { ko: '실현', en: 'realized', ja: '実現', th: 'รับรู้', vi: 'đã chốt' })} </span>
              ${Number(snap.pnl.realized).toFixed(2)}</div>
            <div><span className="muted">
              {tr(language, { ko: '거래', en: 'trades', ja: '取引', th: 'ดีล', vi: 'lệnh' })} </span>
              {snap.pnl.trades}</div>
            {tick && <div><span className="muted">
              {tr(language, { ko: '현재가', en: 'mark', ja: '価格', th: 'ราคา', vi: 'giá' })} </span>
              ${Number(tick.price).toFixed(2)}</div>}
          </div>
        )}

        <div style={{ marginTop: 14, background: 'var(--bg-card,#fafafa)',
          border: '1px solid var(--border-color,rgba(0,0,0,0.08))', borderRadius: 10, padding: 8 }}>
          <RunSparkline values={equity}
            color={(snap?.pnl?.total ?? 0) < 0 ? 'rgb(208,59,59)' : 'rgb(12,163,12)'}
            height={120} />
        </div>

        {canStop && (
          <div style={{ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
            {status === 'running' &&
              <button className="btn" onClick={() => onAct(runId, 'pause')}>
                {tr(language, { ko: '일시정지', en: 'Pause', ja: '一時停止', th: 'พัก', vi: 'Tạm dừng' })}</button>}
            {status === 'paused' &&
              <button className="btn" onClick={() => onAct(runId, 'resume')}>
                {tr(language, { ko: '재개', en: 'Resume', ja: '再開', th: 'ต่อ', vi: 'Tiếp tục' })}</button>}
            <button className="btn" style={{ color: '#eb6834' }}
              onClick={() => onAct(runId, 'stop', { flatten: true })}>
              {tr(language, { ko: '정지+청산', en: 'Stop & flatten', ja: '停止+清算',
                th: 'หยุด+ปิด', vi: 'Dừng + đóng' })}</button>
            <button className="btn"
              onClick={() => onAct(runId, 'stop', { flatten: false })}>
              {tr(language, { ko: '정지+보유', en: 'Stop & hold', ja: '停止+保有',
                th: 'หยุด+ถือ', vi: 'Dừng + giữ' })}</button>
          </div>
        )}
        {['draft', 'stopped'].includes(status) &&
          <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
            {status === 'draft' &&
              <button className="btn btn-primary" onClick={() => onAct(runId, 'start')}>
                {tr(language, { ko: '시작', en: 'Start', ja: '開始', th: 'เริ่ม', vi: 'Bắt đầu' })}</button>}
            <button className="btn" style={{ color: '#d03b3b' }} onClick={() => onDelete(runId)}>
              {tr(language, { ko: '삭제', en: 'Delete', ja: '削除', th: 'ลบ', vi: 'Xóa' })}</button>
          </div>}

        <h3 style={{ fontSize: 13, marginTop: 20, marginBottom: 6 }}>
          {tr(language, { ko: '이벤트 로그', en: 'Event log', ja: 'イベントログ',
            th: 'บันทึกเหตุการณ์', vi: 'Nhật ký sự kiện' })}</h3>
        <div style={{ fontFamily: 'ui-monospace, monospace', fontSize: 11.5, lineHeight: 1.7 }}>
          {log.length === 0 && <span className="muted">—</span>}
          {log.map((e, i) => (
            <div key={i} style={{ display: 'flex', gap: 8 }}>
              <span className="muted" style={{ minWidth: 62 }}>{e.ts?.slice(11, 19)}</span>
              <span style={{ minWidth: 74, color: e.event_type === 'trade' ? '#0ca30c'
                : e.event_type === 'run_status' ? '#2a78d6' : '#898781' }}>{e.event_type}</span>
              <span style={{ opacity: 0.85 }}>{summarize(e, language)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function summarize(e: any, lang: Language): string {
  const p = e.payload || {}
  if (e.event_type === 'run_status') {
    const from = statusLabel(p.from, lang) || '—'
    const why = reasonLabel(p.reason, lang)
    return `${from} → ${statusLabel(p.to, lang)}${why ? ` (${why})` : ''}`
  }
  if (e.event_type === 'alert' && p.auto_restart_run_id) {
    return tr(lang, {
      ko: `같은 설정으로 새 TRADING #${p.auto_restart_run_id}을(를) 시작했습니다`,
      en: `Restarted as TRADING #${p.auto_restart_run_id} with the same settings`,
      ja: `同じ設定で TRADING #${p.auto_restart_run_id} を開始しました`,
      th: `เริ่ม TRADING #${p.auto_restart_run_id} ใหม่ด้วยการตั้งค่าเดิม`,
      vi: `Đã khởi động lại thành TRADING #${p.auto_restart_run_id} với cùng thiết lập` })
  }
  if (e.event_type === 'alert' && p.stop_reason) return reasonLabel(p.stop_reason, lang)
  if (e.event_type === 'trade') return `${p.side} ${Number(p.quantity).toFixed(4)} @ $${Number(p.price).toFixed(2)}`
  if (e.event_type === 'decision') return `${p.action ?? '—'} conf ${p.confidence ?? '—'}`
  if (e.event_type === 'equity') return `total $${Number(p.total).toFixed(2)}`
  if (e.event_type === 'gate_skip') return `${p.stage}: ${p.reason}`
  if (e.event_type === 'alert') return p.stop_reason ?? JSON.stringify(p)
  return JSON.stringify(p).slice(0, 80)
}

function CreateRunForm({ token, onDone, onCancel, language }: {
  token: string
  onDone: (startError?: string, conflictInfo?: {
    runId: number; message: string
    conflicts: { position: any; rule_ids: number[] }
  }) => void
  onCancel: () => void; language: Language
}) {
  const [f, setF] = useState({
    symbol: 'BTC', market: 'crypto', market_type: 'spot',
    max_bet_usd: 500, interval_minutes: 60, min_confidence: 0.65,
    stop_loss_usd: '', profit_target_usd: '',
    report_frequency: 'off', notify_on_trade: false,
  })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const auth = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
  const E = {
    createFailed: tr(language, { ko: 'TRADING을 만들지 못했습니다.', en: 'Could not create the TRADING.',
      ja: 'TRADING を作成できませんでした。', th: 'สร้าง TRADING ไม่สำเร็จ', vi: 'Không tạo được TRADING.' }),
    startFailed: tr(language, { ko: 'TRADING을 시작하지 못했습니다.', en: 'Could not start the TRADING.',
      ja: 'TRADING を開始できませんでした。', th: 'เริ่ม TRADING ไม่สำเร็จ', vi: 'Không khởi động được TRADING.' }),
    network: tr(language, { ko: '네트워크 오류 — 연결을 확인한 뒤 다시 시도하세요.',
      en: 'Network error — check your connection and try again.',
      ja: 'ネットワークエラー — 接続を確認して再試行してください。',
      th: 'เครือข่ายผิดพลาด — ตรวจการเชื่อมต่อแล้วลองใหม่',
      vi: 'Lỗi mạng — kiểm tra kết nối rồi thử lại.' }),
  }

  async function submit() {
    setErr(''); setBusy(true)
    const stop: any = {}
    if (f.stop_loss_usd) stop.max_loss_usd = Number(f.stop_loss_usd)
    if (f.profit_target_usd) stop.profit_target_usd = Number(f.profit_target_usd)
    try {
      const r = await fetch(`${API_BASE}/runs`, {
        method: 'POST', headers: auth,
        body: JSON.stringify({
          symbol: f.symbol, market: f.market, market_type: f.market_type,
          max_bet_usd: Number(f.max_bet_usd),
          interval_minutes: Number(f.interval_minutes),
          min_confidence: Number(f.min_confidence),
          stop_conditions: stop,
        }),
      })
      const d = await r.json()
      if (!r.ok) {
        const msg = typeof d.detail === 'object' ? d.detail?.message : d.detail
        setErr(msg || E.createFailed); setBusy(false); return
      }
      const runId = d.id
      if (f.report_frequency !== 'off' || f.notify_on_trade) {
        await fetch(`${API_BASE}/runs/${runId}/reporting`, {
          method: 'PUT', headers: auth,
          body: JSON.stringify({ report_frequency: f.report_frequency,
            notify_on_trade: f.notify_on_trade }),
        })
      }
      // One step: start immediately. A structured 409 (open position and/or a
      // conflicting auto-execute rule) bubbles up so the section can offer
      // one-click resolution; any other refusal leaves the draft in the grid
      // with the reason surfaced at section level.
      let startError: string | undefined
      let conflictInfo
      try {
        const s = await fetch(`${API_BASE}/runs/${runId}/start`, { method: 'POST', headers: auth })
        if (!s.ok) {
          const detail = (await s.json().catch(() => null))?.detail
          if (s.status === 409 && detail && typeof detail === 'object' && detail.conflicts
              && (detail.conflicts.position || detail.conflicts.rule_ids?.length)) {
            conflictInfo = { runId, message: detail.message, conflicts: detail.conflicts }
          } else if (typeof detail === 'string') {
            startError = detail
          } else {
            startError = detail?.message || E.startFailed
          }
        }
      } catch { startError = E.network }
      onDone(startError, conflictInfo)
    } catch { setErr(E.network); setBusy(false) }
  }

  const lbl = (o: any) => tr(language, o)
  const field: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }
  const input: React.CSSProperties = { padding: '6px 8px', borderRadius: 6,
    border: '1px solid var(--border-color,rgba(0,0,0,0.15))', background: 'var(--bg-card,#fff)',
    color: 'var(--text-primary,#111)' }

  return (
    <div style={{ marginTop: 16, background: 'var(--bg-card,#fff)',
      border: '1px solid var(--border-color,rgba(0,0,0,0.1))', borderRadius: 12, padding: 16 }}>
      <div style={{ display: 'grid', gap: 12,
        gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
        <label style={field}>{lbl({ ko: '심볼', en: 'Symbol', ja: 'シンボル', th: 'สัญลักษณ์', vi: 'Mã' })}
          <SymbolSelect style={input} market={f.market} value={f.symbol}
            onChange={(symbol) => setF({ ...f, symbol })}
            placeholder={lbl({ ko: '종목 선택', en: 'Select symbol', ja: '銘柄を選択',
              th: 'เลือกสัญลักษณ์', vi: 'Chọn mã' })} /></label>
        <label style={field}>{lbl({ ko: '시장', en: 'Market', ja: '市場', th: 'ตลาด', vi: 'Thị trường' })}
          <select style={input} value={f.market}
            onChange={(e) => setF({ ...f, market: e.target.value, symbol: '',
              market_type: e.target.value === 'crypto' ? f.market_type : 'spot' })}>
            <option value="crypto">crypto</option><option value="us-stock">us-stock</option>
            <option value="forex">forex</option>
          </select></label>
        <label style={field}>{lbl({ ko: '유형', en: 'Type', ja: 'タイプ', th: 'ชนิด', vi: 'Loại' })}
          <select style={input} value={f.market_type}
            onChange={(e) => setF({ ...f, market_type: e.target.value })}>
            <option value="spot">spot</option>
            <option value="futures" disabled={f.market !== 'crypto'}>futures</option>
          </select></label>
        <label style={field}>{lbl({ ko: '최대 베팅($)', en: 'Max bet ($)', ja: '最大($)', th: 'เดิมพันสูงสุด', vi: 'Cược tối đa' })}
          <input style={input} type="number" value={f.max_bet_usd}
            onChange={(e) => setF({ ...f, max_bet_usd: Number(e.target.value) })} /></label>
        <label style={field}>{lbl({ ko: '주기(분)', en: 'Interval (min)', ja: '間隔(分)', th: 'ช่วง(นาที)', vi: 'Chu kỳ (phút)' })}
          <input style={input} type="number" min={5} value={f.interval_minutes}
            onChange={(e) => setF({ ...f, interval_minutes: Number(e.target.value) })} /></label>
        <label style={field}>{lbl({ ko: '최소 신뢰도', en: 'Min confidence', ja: '最小信頼度', th: 'ความมั่นใจ', vi: 'Độ tin tối thiểu' })}
          <input style={input} type="number" step={0.05} min={0} max={1} value={f.min_confidence}
            onChange={(e) => setF({ ...f, min_confidence: Number(e.target.value) })} /></label>
        <label style={field}>{lbl({ ko: '손절($)', en: 'Stop loss ($)', ja: '損切り($)', th: 'ตัดขาดทุน', vi: 'Cắt lỗ ($)' })}
          <input style={input} type="number" value={f.stop_loss_usd}
            onChange={(e) => setF({ ...f, stop_loss_usd: e.target.value })} /></label>
        <label style={field}>{lbl({ ko: '익절($)', en: 'Profit target ($)', ja: '利確($)', th: 'เป้ากำไร', vi: 'Chốt lời ($)' })}
          <input style={input} type="number" value={f.profit_target_usd}
            onChange={(e) => setF({ ...f, profit_target_usd: e.target.value })} /></label>
        <label style={field}>{lbl({ ko: '리포트', en: 'Reports', ja: 'レポート', th: 'รายงาน', vi: 'Báo cáo' })}
          <select style={input} value={f.report_frequency}
            onChange={(e) => setF({ ...f, report_frequency: e.target.value })}>
            <option value="off">off</option><option value="hourly">hourly</option>
            <option value="daily">daily</option><option value="weekly">weekly</option>
          </select></label>
        <label style={{ ...field, flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 18 }}>
          <input type="checkbox" checked={f.notify_on_trade}
            onChange={(e) => setF({ ...f, notify_on_trade: e.target.checked })} />
          {lbl({ ko: '체결 알림', en: 'Alert on trade', ja: '取引通知', th: 'แจ้งเมื่อเทรด', vi: 'Báo khi giao dịch' })}
        </label>
      </div>
      {err && <div style={{ color: '#d03b3b', marginTop: 10, fontSize: 12 }}>{err}</div>}
      <p className="muted" style={{ fontSize: 11, marginTop: 10 }}>
        {tr(language, {
          ko: '런은 서버에서 백그라운드로 실행되며 페이퍼(시뮬레이터) 계정으로 체결됩니다. 미국 주식은 가격 갱신 주기 특성상 정지 조건이 수 분 지연될 수 있습니다.',
          en: 'Runs execute server-side on the paper (simulator) account. US-stock stops evaluate on minutes-old marks due to the price-poll interval.',
          ja: 'ランはサーバー側でペーパー口座で執行。米国株は価格ポーリングのため停止条件が数分遅延することがあります。',
          th: 'รันทำงานฝั่งเซิร์ฟเวอร์บนบัญชีจำลอง หุ้นสหรัฐฯ เงื่อนไขหยุดอาจช้าไม่กี่นาที',
          vi: 'Phiên chạy phía máy chủ trên tài khoản mô phỏng. Cổ phiếu Mỹ có thể trễ vài phút do chu kỳ polling giá.' })}
      </p>
      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <button className="btn btn-primary" disabled={busy} onClick={submit}>
          {tr(language, { ko: '▶ TRADING 만들고 시작', en: '▶ Create & start TRADING',
            ja: '▶ TRADING を作成して開始', th: '▶ สร้างและเริ่ม TRADING',
            vi: '▶ Tạo & bắt đầu TRADING' })}</button>
        <button className="btn" onClick={onCancel}>
          {tr(language, { ko: '취소', en: 'Cancel', ja: 'キャンセル', th: 'ยกเลิก', vi: 'Hủy' })}</button>
      </div>
    </div>
  )
}

export default RunsLivePage
