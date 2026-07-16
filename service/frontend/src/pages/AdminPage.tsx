import { useEffect, useState } from 'react'
import { API_BASE, useLanguage } from '../appShared'
import { tr } from '../i18n'

// Manager console — /admin. Gated by ADMIN_TOKEN (backend .env); the token is
// entered once and kept in localStorage. Tabs: overview / accounts / money /
// AI automation. Read-mostly; the only writes are agent/user deletion.
const ADMIN_TOKEN_KEY = 'sooppiy_admin_token'

type Tab = 'overview' | 'accounts' | 'money' | 'ai'

export function AdminPage() {
  const { language } = useLanguage()
  const [token, setToken] = useState<string>(() => localStorage.getItem(ADMIN_TOKEN_KEY) || '')
  const [draft, setDraft] = useState('')
  const [tab, setTab] = useState<Tab>('overview')
  const [overview, setOverview] = useState<any | null>(null)
  const [agents, setAgents] = useState<any | null>(null)
  const [users, setUsers] = useState<any | null>(null)
  const [tx, setTx] = useState<any | null>(null)
  const [ai, setAi] = useState<any | null>(null)
  const [q, setQ] = useState('')
  const [error, setError] = useState('')

  const T = {
    title: tr(language, { ko: '관리자 콘솔', en: 'Manager Console', ja: '管理コンソール', th: 'คอนโซลผู้ดูแล', vi: 'Bảng quản trị' }),
    enterToken: tr(language, { ko: 'ADMIN_TOKEN을 입력하세요 (서버 .env에 설정된 값)', en: 'Enter the ADMIN_TOKEN (set in the server .env)', ja: 'ADMIN_TOKENを入力（サーバー.envの値）', th: 'กรอก ADMIN_TOKEN (ตั้งค่าใน .env ของเซิร์ฟเวอร์)', vi: 'Nhập ADMIN_TOKEN (đặt trong .env máy chủ)' }),
    connect: tr(language, { ko: '연결', en: 'Connect', ja: '接続', th: 'เชื่อมต่อ', vi: 'Kết nối' }),
    logout: tr(language, { ko: '토큰 지우기', en: 'Clear token', ja: 'トークン削除', th: 'ล้างโทเค็น', vi: 'Xóa token' }),
    tabOverview: tr(language, { ko: '개요', en: 'Overview', ja: '概要', th: 'ภาพรวม', vi: 'Tổng quan' }),
    tabAccounts: tr(language, { ko: '사용자 · 에이전트', en: 'Users · Agents', ja: 'ユーザー · エージェント', th: 'ผู้ใช้ · เอเจนต์', vi: 'Người dùng · Agent' }),
    tabMoney: tr(language, { ko: '거래 · 자금', en: 'Money · Transactions', ja: '取引 · 資金', th: 'เงิน · ธุรกรรม', vi: 'Tiền · Giao dịch' }),
    tabAi: tr(language, { ko: 'AI 자동화', en: 'AI Automation', ja: 'AI自動化', th: 'AI อัตโนมัติ', vi: 'AI tự động' }),
    del: tr(language, { ko: '삭제', en: 'Delete', ja: '削除', th: 'ลบ', vi: 'Xóa' }),
    delConfirm: tr(language, { ko: '정말 삭제할까요? 이 계정의 모든 데이터(시그널·포지션·규칙)가 함께 삭제됩니다.', en: 'Really delete? All of this account\'s data (signals, positions, rules) is deleted with it.', ja: '本当に削除しますか？この口座の全データも削除されます。', th: 'ลบจริงหรือไม่? ข้อมูลทั้งหมดของบัญชีนี้จะถูกลบด้วย', vi: 'Xóa thật không? Mọi dữ liệu của tài khoản này sẽ bị xóa theo.' }),
    search: tr(language, { ko: '이름/이메일 검색', en: 'Search name/email', ja: '名前/メール検索', th: 'ค้นหาชื่อ/อีเมล', vi: 'Tìm tên/email' }),
    unauthorized: tr(language, { ko: '토큰이 올바르지 않습니다', en: 'Invalid admin token', ja: 'トークンが正しくありません', th: 'โทเค็นไม่ถูกต้อง', vi: 'Token không hợp lệ' }),
    disabled: tr(language, { ko: '관리자 API가 비활성화되어 있습니다 — 서버 .env에 ADMIN_TOKEN을 설정하세요', en: 'Admin API disabled — set ADMIN_TOKEN in the server .env', ja: '管理APIが無効 — サーバー.envにADMIN_TOKENを設定', th: 'API ผู้ดูแลถูกปิด — ตั้ง ADMIN_TOKEN ใน .env', vi: 'API quản trị bị tắt — đặt ADMIN_TOKEN trong .env' }),
    noData: tr(language, { ko: '데이터 없음', en: 'No data', ja: 'データなし', th: 'ไม่มีข้อมูล', vi: 'Không có dữ liệu' }),
  }

  const hdr = { 'Authorization': `Bearer ${token}` }

  async function call(path: string) {
    const r = await fetch(`${API_BASE}/admin/${path}`, { headers: hdr })
    if (r.status === 401) { setError(T.unauthorized); throw new Error('401') }
    if (r.status === 503) { setError(T.disabled); throw new Error('503') }
    if (!r.ok) throw new Error(String(r.status))
    return r.json()
  }

  async function refresh(which: Tab = tab) {
    if (!token) return
    setError('')
    try {
      if (which === 'overview') setOverview(await call('overview'))
      if (which === 'accounts') {
        setAgents(await call(`agents?q=${encodeURIComponent(q)}&limit=100`))
        setUsers(await call('users?limit=100'))
      }
      if (which === 'money') setTx(await call('transactions?limit=100'))
      if (which === 'ai') setAi(await call('automation?limit=100'))
    } catch { /* error state already set */ }
  }

  useEffect(() => { refresh(tab) }, [tab, token])

  async function removeAgent(id: number) {
    if (!window.confirm(T.delConfirm)) return
    await fetch(`${API_BASE}/admin/agents/${id}`, { method: 'DELETE', headers: hdr })
    refresh('accounts'); refresh('overview')
  }
  async function removeUser(id: number) {
    if (!window.confirm(T.delConfirm)) return
    await fetch(`${API_BASE}/admin/users/${id}`, { method: 'DELETE', headers: hdr })
    refresh('accounts'); refresh('overview')
  }

  const card: any = { background: 'var(--bg-secondary,#161615)', border: '1px solid var(--border-color,#2a2a28)', borderRadius: 12, padding: '16px 18px' }
  const th: any = { textAlign: 'left', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-muted,#8a8073)', padding: '8px 10px', borderBottom: '1px solid var(--border-color,#2a2a28)' }
  const td: any = { padding: '8px 10px', fontSize: 13, borderBottom: '1px solid var(--border-color,#2a2a28)' }
  const chip = (active: boolean): any => ({ padding: '8px 16px', borderRadius: 999, cursor: 'pointer', fontSize: 13, fontWeight: active ? 700 : 500, border: active ? '1.5px solid var(--accent-primary,#c26a45)' : '1px solid var(--border-color,#2a2a28)', background: active ? 'rgba(194,106,69,0.12)' : 'transparent', color: active ? 'var(--accent-primary,#c26a45)' : 'inherit' })
  const delBtn: any = { padding: '4px 10px', borderRadius: 6, border: '1px solid #7f1d1d', background: 'transparent', color: '#ef4444', cursor: 'pointer', fontSize: 12 }

  if (!token) {
    return (
      <div style={{ maxWidth: 480, margin: '80px auto', padding: 24 }}>
        <h1 style={{ fontSize: 22, marginBottom: 8 }}>🔐 {T.title}</h1>
        <p style={{ fontSize: 13, color: 'var(--text-secondary,#8a8073)', marginBottom: 16 }}>{T.enterToken}</p>
        <input type="password" value={draft} onChange={e => setDraft(e.target.value)}
          style={{ width: '100%', padding: '10px 12px', borderRadius: 8, border: '1px solid var(--border-color,#2a2a28)', background: 'var(--bg-secondary,#161615)', color: 'var(--text-primary,#fff)', marginBottom: 12 }} />
        <button onClick={() => { localStorage.setItem(ADMIN_TOKEN_KEY, draft.trim()); setToken(draft.trim()) }}
          style={{ padding: '10px 20px', borderRadius: 8, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 600, cursor: 'pointer' }}>{T.connect}</button>
      </div>
    )
  }

  const ov = overview?.overview

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '24px 16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
        <h1 style={{ fontSize: 22, margin: 0 }}>🔐 {T.title}</h1>
        <button onClick={() => { localStorage.removeItem(ADMIN_TOKEN_KEY); setToken('') }}
          style={{ marginLeft: 'auto', padding: '6px 12px', borderRadius: 7, border: '1px solid var(--border-color,#2a2a28)', background: 'transparent', color: 'inherit', cursor: 'pointer', fontSize: 12 }}>{T.logout}</button>
      </div>
      <div style={{ display: 'flex', gap: 8, margin: '14px 0', flexWrap: 'wrap' }}>
        <button style={chip(tab === 'overview')} onClick={() => setTab('overview')}>{T.tabOverview}</button>
        <button style={chip(tab === 'accounts')} onClick={() => setTab('accounts')}>{T.tabAccounts}</button>
        <button style={chip(tab === 'money')} onClick={() => setTab('money')}>{T.tabMoney}</button>
        <button style={chip(tab === 'ai')} onClick={() => setTab('ai')}>{T.tabAi}</button>
      </div>
      {error && <div style={{ color: '#ef4444', fontSize: 13, marginBottom: 12 }}>⚠️ {error}</div>}

      {tab === 'overview' && ov && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))', gap: 12 }}>
          {[
            [tr(language, { ko: '에이전트', en: 'Agents', ja: 'エージェント', th: 'เอเจนต์', vi: 'Agent' }), ov.agents],
            [tr(language, { ko: '사용자', en: 'Users', ja: 'ユーザー', th: 'ผู้ใช้', vi: 'Người dùng' }), ov.users],
            [tr(language, { ko: '거래', en: 'Trades', ja: '取引', th: 'เทรด', vi: 'Giao dịch' }), ov.trades],
            [tr(language, { ko: '전략 / 토론', en: 'Strategies / Discussions', ja: '戦略 / 議論', th: 'กลยุทธ์ / สนทนา', vi: 'Chiến lược / Thảo luận' }), `${ov.strategies} / ${ov.discussions}`],
            [tr(language, { ko: '미결제 포지션', en: 'Open positions', ja: '未決済ポジション', th: 'สถานะเปิด', vi: 'Vị thế mở' }), ov.open_positions],
            [tr(language, { ko: '자동화 규칙 (활성)', en: 'Automation rules (on)', ja: '自動化ルール（有効）', th: 'กฎอัตโนมัติ (เปิด)', vi: 'Quy tắc tự động (bật)' }), `${ov.automation_rules} (${ov.automation_rules_enabled})`],
            [tr(language, { ko: '24시간 자동화 실행', en: 'Automation runs 24h', ja: '24h自動実行', th: 'รัน 24 ชม.', vi: 'Lần chạy 24h' }), ov.automation_runs_24h],
            [tr(language, { ko: '모의 자금 합계', en: 'Total sim cash', ja: '模擬資金合計', th: 'เงินจำลองรวม', vi: 'Tổng tiền mô phỏng' }), `$${Number(ov.total_sim_cash).toLocaleString()}`],
            [tr(language, { ko: '포인트 합계', en: 'Total points', ja: 'ポイント合計', th: 'คะแนนรวม', vi: 'Tổng điểm' }), ov.total_points],
          ].map(([label, value]) => (
            <div key={String(label)} style={card}>
              <div style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
              <div style={{ fontSize: 24, fontWeight: 700, marginTop: 6 }}>{String(value)}</div>
            </div>
          ))}
        </div>
      )}

      {tab === 'accounts' && (
        <>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <input placeholder={T.search} value={q} onChange={e => setQ(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && refresh('accounts')}
              style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid var(--border-color,#2a2a28)', background: 'var(--bg-secondary,#161615)', color: 'var(--text-primary,#fff)', width: 260 }} />
          </div>
          <div style={{ ...card, padding: 0, marginBottom: 16, overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 720 }}>
              <thead><tr><th style={th}>ID</th><th style={th}>{tr(language, { ko: '에이전트', en: 'Agent', ja: 'エージェント', th: 'เอเจนต์', vi: 'Agent' })}</th><th style={th}>Email</th><th style={th}>{tr(language, { ko: '현금', en: 'Cash', ja: '現金', th: 'เงินสด', vi: 'Tiền' })}</th><th style={th}>{tr(language, { ko: '포인트', en: 'Points', ja: 'ポイント', th: 'คะแนน', vi: 'Điểm' })}</th><th style={th}>{tr(language, { ko: '거래', en: 'Trades', ja: '取引', th: 'เทรด', vi: 'GD' })}</th><th style={th}></th></tr></thead>
              <tbody>
                {(agents?.agents || []).map((a: any) => (
                  <tr key={a.id}>
                    <td style={td}>{a.id}</td><td style={{ ...td, fontWeight: 600 }}>{a.name}</td>
                    <td style={td}>{a.email || '—'}</td>
                    <td style={td}>${Number(a.cash || 0).toLocaleString()}</td>
                    <td style={td}>{a.points}</td><td style={td}>{a.trade_count}</td>
                    <td style={td}><button style={delBtn} onClick={() => removeAgent(a.id)}>{T.del}</button></td>
                  </tr>
                ))}
                {!(agents?.agents || []).length && <tr><td style={td} colSpan={7}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
          <div style={{ ...card, padding: 0, overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 620 }}>
              <thead><tr><th style={th}>ID</th><th style={th}>{tr(language, { ko: '사용자 이메일', en: 'User email', ja: 'ユーザーメール', th: 'อีเมลผู้ใช้', vi: 'Email người dùng' })}</th><th style={th}>MFA</th><th style={th}>{tr(language, { ko: '연결된 에이전트', en: 'Linked agent', ja: '連携エージェント', th: 'เอเจนต์ที่เชื่อม', vi: 'Agent liên kết' })}</th><th style={th}>{tr(language, { ko: '가입일', en: 'Created', ja: '作成日', th: 'สร้างเมื่อ', vi: 'Tạo lúc' })}</th><th style={th}></th></tr></thead>
              <tbody>
                {(users?.users || []).map((u: any) => (
                  <tr key={u.id}>
                    <td style={td}>{u.id}</td><td style={{ ...td, fontWeight: 600 }}>{u.email}</td>
                    <td style={td}>{u.mfa_enabled ? '✓' : '—'}</td>
                    <td style={td}>{u.agent_name || '—'}</td>
                    <td style={td}>{String(u.created_at || '').slice(0, 10)}</td>
                    <td style={td}><button style={delBtn} onClick={() => removeUser(u.id)}>{T.del}</button></td>
                  </tr>
                ))}
                {!(users?.users || []).length && <tr><td style={td} colSpan={6}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}

      {tab === 'money' && (
        <>
          <div style={{ ...card, padding: 0, marginBottom: 16, overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 720 }}>
              <thead><tr><th style={th}>{tr(language, { ko: '거래 (최근)', en: 'Trades (recent)', ja: '取引（直近）', th: 'เทรด (ล่าสุด)', vi: 'Giao dịch (gần đây)' })}</th><th style={th}>{tr(language, { ko: '에이전트', en: 'Agent', ja: 'エージェント', th: 'เอเจนต์', vi: 'Agent' })}</th><th style={th}>{tr(language, { ko: '방향', en: 'Side', ja: '方向', th: 'ฝั่ง', vi: 'Hướng' })}</th><th style={th}>{tr(language, { ko: '가격', en: 'Price', ja: '価格', th: 'ราคา', vi: 'Giá' })}</th><th style={th}>{tr(language, { ko: '수량', en: 'Qty', ja: '数量', th: 'จำนวน', vi: 'SL' })}</th><th style={th}>{tr(language, { ko: '시각', en: 'Time', ja: '時刻', th: 'เวลา', vi: 'Lúc' })}</th></tr></thead>
              <tbody>
                {(tx?.trades || []).map((t: any) => (
                  <tr key={t.signal_id}>
                    <td style={{ ...td, fontWeight: 600 }}>{t.symbol} <span style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)' }}>{t.market}</span></td>
                    <td style={td}>{t.agent_name || t.agent_id}</td>
                    <td style={{ ...td, color: ['buy', 'cover'].includes(t.side) ? '#22c55e' : '#ef4444' }}>{t.side}</td>
                    <td style={td}>{t.entry_price}</td><td style={td}>{t.quantity}</td>
                    <td style={td}>{String(t.created_at || '').replace('T', ' ').slice(0, 16)}</td>
                  </tr>
                ))}
                {!(tx?.trades || []).length && <tr><td style={td} colSpan={6}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
          <div style={{ ...card, padding: 0, overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 620 }}>
              <thead><tr><th style={th}>{tr(language, { ko: '포인트 원장', en: 'Points ledger', ja: 'ポイント台帳', th: 'บัญชีคะแนน', vi: 'Sổ điểm' })}</th><th style={th}>{tr(language, { ko: '변동', en: 'Amount', ja: '変動', th: 'จำนวน', vi: 'Số' })}</th><th style={th}>{tr(language, { ko: '사유', en: 'Reason', ja: '理由', th: 'เหตุผล', vi: 'Lý do' })}</th><th style={th}>{tr(language, { ko: '시각', en: 'Time', ja: '時刻', th: 'เวลา', vi: 'Lúc' })}</th></tr></thead>
              <tbody>
                {(tx?.reward_ledger || []).map((l: any) => (
                  <tr key={l.id}>
                    <td style={{ ...td, fontWeight: 600 }}>{l.agent_name || l.agent_id}</td>
                    <td style={{ ...td, color: (l.amount || 0) >= 0 ? '#22c55e' : '#ef4444' }}>{(l.amount || 0) >= 0 ? '+' : ''}{l.amount}</td>
                    <td style={td}>{l.reason}</td>
                    <td style={td}>{String(l.created_at || '').replace('T', ' ').slice(0, 16)}</td>
                  </tr>
                ))}
                {!(tx?.reward_ledger || []).length && <tr><td style={td} colSpan={4}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}

      {tab === 'ai' && (
        <>
          <div style={{ ...card, padding: 0, marginBottom: 16, overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 760 }}>
              <thead><tr><th style={th}>{tr(language, { ko: '규칙', en: 'Rule', ja: 'ルール', th: 'กฎ', vi: 'Quy tắc' })}</th><th style={th}>{tr(language, { ko: '에이전트', en: 'Agent', ja: 'エージェント', th: 'เอเจนต์', vi: 'Agent' })}</th><th style={th}>{tr(language, { ko: '주기', en: 'Interval', ja: '間隔', th: 'ช่วง', vi: 'Chu kỳ' })}</th><th style={th}>{tr(language, { ko: '신뢰도', en: 'Conf.', ja: '信頼度', th: 'มั่นใจ', vi: 'Tin cậy' })}</th><th style={th}>$</th><th style={th}>{tr(language, { ko: '상태', en: 'Status', ja: '状態', th: 'สถานะ', vi: 'Trạng thái' })}</th><th style={th}>{tr(language, { ko: '마지막 실행', en: 'Last run', ja: '最終実行', th: 'รันล่าสุด', vi: 'Chạy cuối' })}</th></tr></thead>
              <tbody>
                {(ai?.rules || []).map((r: any) => (
                  <tr key={r.id}>
                    <td style={{ ...td, fontWeight: 600 }}>{r.symbol} <span style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)' }}>{r.market} · {r.provider || 'default'}</span></td>
                    <td style={td}>{r.agent_name || r.agent_id}</td>
                    <td style={td}>{r.interval_minutes}m</td>
                    <td style={td}>≥{Math.round((r.min_confidence || 0) * 100)}%</td>
                    <td style={td}>${r.size_usd}</td>
                    <td style={td}>{r.enabled ? (r.auto_execute ? '🟢 auto' : '🟡 analysis') : '⚪ off'} · {r.account_type}</td>
                    <td style={td}>{String(r.last_run_at || '—').replace('T', ' ').slice(0, 16)}</td>
                  </tr>
                ))}
                {!(ai?.rules || []).length && <tr><td style={td} colSpan={7}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
          <div style={{ ...card, padding: 0, overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 720 }}>
              <thead><tr><th style={th}>{tr(language, { ko: '실행 기록', en: 'Run', ja: '実行', th: 'รัน', vi: 'Lần chạy' })}</th><th style={th}>{tr(language, { ko: '에이전트', en: 'Agent', ja: 'エージェント', th: 'เอเจนต์', vi: 'Agent' })}</th><th style={th}>{tr(language, { ko: '결정', en: 'Action', ja: '決定', th: 'การตัดสิน', vi: 'Quyết định' })}</th><th style={th}>{tr(language, { ko: '신뢰도', en: 'Conf.', ja: '信頼度', th: 'มั่นใจ', vi: 'Tin cậy' })}</th><th style={th}>{tr(language, { ko: '결과', en: 'Result', ja: '結果', th: 'ผล', vi: 'Kết quả' })}</th></tr></thead>
              <tbody>
                {(ai?.runs || []).map((r: any) => (
                  <tr key={r.id}>
                    <td style={td}>{String(r.ran_at || '').replace('T', ' ').slice(0, 16)}</td>
                    <td style={td}>{r.agent_name || r.agent_id}</td>
                    <td style={{ ...td, fontWeight: 700, textTransform: 'uppercase', color: r.action === 'buy' ? '#22c55e' : r.action === 'sell' ? '#ef4444' : '#eab308' }}>{r.action || '—'}</td>
                    <td style={td}>{Math.round((r.confidence || 0) * 100)}%</td>
                    <td style={td}>{r.executed ? '✓ executed' : (r.skip_reason || '—')}</td>
                  </tr>
                ))}
                {!(ai?.runs || []).length && <tr><td style={td} colSpan={5}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

export default AdminPage
