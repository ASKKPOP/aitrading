import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'

import { API_BASE, MARKETS, useLanguage } from './appShared'
import { LOCALE_BY_LANGUAGE, tr, type Language } from './i18n'

type TeamMissionsPageProps = {
  token?: string | null
}

const missionStatuses = ['upcoming', 'active', 'settled'] as const

function formatDate(value: string | null | undefined, language: Language) {
  if (!value) return '-'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString(LOCALE_BY_LANGUAGE[language], {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

function formatScore(value: any) {
  return Number(value || 0).toFixed(2)
}

function marketLabel(value: string, language: Language) {
  return MARKETS.find((market) => market.value === value)?.labels[language] || value
}

export function TeamMissionsPage({ token }: TeamMissionsPageProps) {
  const { missionKey, teamKey } = useParams()
  const { language } = useLanguage()
  const [status, setStatus] = useState<'upcoming' | 'active' | 'settled'>('active')
  const [missions, setMissions] = useState<any[]>([])
  const [mission, setMission] = useState<any | null>(null)
  const [team, setTeam] = useState<any | null>(null)
  const [leaderboard, setLeaderboard] = useState<any[]>([])
  const [myMissions, setMyMissions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] = useState({
    title: '',
    mission_key: '',
    market: 'crypto',
    symbol: 'BTC',
    assignment_mode: 'random',
    team_size_min: '2',
    team_size_max: '4',
    submission_due_at: ''
  })
  const [teamForm, setTeamForm] = useState({ name: '', role: 'lead' })
  const [submissionForm, setSubmissionForm] = useState({ title: '', content: '', confidence: '0.7' })
  const [signalLinkForm, setSignalLinkForm] = useState({ signal_id: '', message_type: 'discussion' })

  const joinedMissionIds = useMemo(() => new Set(myMissions.map((item) => item.id)), [myMissions])

  const loadMine = async () => {
    if (!token) {
      setMyMissions([])
      return
    }
    try {
      const res = await fetch(`${API_BASE}/team-missions/me`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (!res.ok) return
      const data = await res.json()
      setMyMissions(data.missions || [])
    } catch (e) {
      console.error(e)
    }
  }

  const loadList = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/team-missions?status=${status}&limit=100`)
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'mission_load_failed')
      setMissions(data.missions || [])
      setError(null)
    } catch (err: any) {
      setError(err?.message || tr(language, { en: 'Failed to load team missions', ja: 'チームミッションの読み込みに失敗しました', th: 'โหลดภารกิจของทีมล้มเหลว', vi: 'Tải nhiệm vụ nhóm thất bại' }))
      setMissions([])
    } finally {
      setLoading(false)
    }
  }

  const loadMission = async () => {
    if (!missionKey) return
    setLoading(true)
    try {
      const [missionRes, leaderboardRes] = await Promise.all([
        fetch(`${API_BASE}/team-missions/${missionKey}`),
        fetch(`${API_BASE}/team-missions/${missionKey}/leaderboard`)
      ])
      const [missionData, leaderboardData] = await Promise.all([missionRes.json(), leaderboardRes.json()])
      if (!missionRes.ok) throw new Error(missionData.detail || 'mission_detail_failed')
      setMission(missionData)
      setLeaderboard(leaderboardData.leaderboard || [])
      setError(null)
    } catch (err: any) {
      setError(err?.message || tr(language, { en: 'Failed to load mission detail', ja: 'ミッション詳細の読み込みに失敗しました', th: 'โหลดรายละเอียดภารกิจล้มเหลว', vi: 'Tải chi tiết nhiệm vụ thất bại' }))
      setMission(null)
      setLeaderboard([])
    } finally {
      setLoading(false)
    }
  }

  const loadTeam = async () => {
    if (!teamKey) return
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/teams/${teamKey}`)
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'team_load_failed')
      setTeam(data)
      setError(null)
    } catch (err: any) {
      setError(err?.message || tr(language, { en: 'Failed to load team', ja: 'チームの読み込みに失敗しました', th: 'โหลดทีมล้มเหลว', vi: 'Tải nhóm thất bại' }))
      setTeam(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (teamKey) {
      loadTeam()
    } else if (missionKey) {
      loadMission()
    } else {
      loadList()
    }
    loadMine()
  }, [missionKey, teamKey, status, token])

  const authedFetch = async (url: string, body: any = {}) => {
    if (!token) throw new Error(tr(language, { en: 'Login required', ja: 'ログインが必要です', th: 'ต้องเข้าสู่ระบบ', vi: 'Cần đăng nhập' }))
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(body)
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'request_failed')
    return data
  }

  const handleCreateMission = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    try {
      const dueAt = createForm.submission_due_at ? new Date(createForm.submission_due_at).toISOString() : undefined
      await authedFetch(`${API_BASE}/team-missions`, {
        ...createForm,
        mission_key: createForm.mission_key || undefined,
        symbol: createForm.symbol || undefined,
        team_size_min: Number(createForm.team_size_min || 2),
        team_size_max: Number(createForm.team_size_max || 4),
        submission_due_at: dueAt
      })
      setCreateForm({
        title: '',
        mission_key: '',
        market: 'crypto',
        symbol: 'BTC',
        assignment_mode: 'random',
        team_size_min: '2',
        team_size_max: '4',
        submission_due_at: ''
      })
      setShowCreate(false)
      await loadList()
    } catch (err: any) {
      alert(err?.message || tr(language, { en: 'Create failed', ja: '作成に失敗しました', th: 'สร้างล้มเหลว', vi: 'Tạo thất bại' }))
    } finally {
      setBusy(false)
    }
  }

  const handleJoinMission = async (key: string) => {
    setBusy(true)
    try {
      await authedFetch(`${API_BASE}/team-missions/${key}/join`, {})
      await Promise.all([loadMine(), missionKey ? loadMission() : loadList()])
    } catch (err: any) {
      alert(err?.message || tr(language, { en: 'Join failed', ja: '参加に失敗しました', th: 'เข้าร่วมล้มเหลว', vi: 'Tham gia thất bại' }))
    } finally {
      setBusy(false)
    }
  }

  const handleCreateTeam = async (event: FormEvent) => {
    event.preventDefault()
    if (!mission) return
    setBusy(true)
    try {
      await authedFetch(`${API_BASE}/team-missions/${mission.mission_key}/teams`, teamForm)
      setTeamForm({ name: '', role: 'lead' })
      await Promise.all([loadMission(), loadMine()])
    } catch (err: any) {
      alert(err?.message || tr(language, { en: 'Failed to create team', ja: 'チームの作成に失敗しました', th: 'สร้างทีมล้มเหลว', vi: 'Tạo nhóm thất bại' }))
    } finally {
      setBusy(false)
    }
  }

  const handleAutoForm = async () => {
    if (!mission) return
    setBusy(true)
    try {
      await authedFetch(`${API_BASE}/team-missions/${mission.mission_key}/auto-form-teams`, {
        assignment_mode: mission.assignment_mode
      })
      await loadMission()
    } catch (err: any) {
      alert(err?.message || tr(language, { en: 'Auto-form failed', ja: '自動チーム編成に失敗しました', th: 'จัดทีมอัตโนมัติล้มเหลว', vi: 'Tự động tạo nhóm thất bại' }))
    } finally {
      setBusy(false)
    }
  }

  const handleSubmitTeam = async (event: FormEvent) => {
    event.preventDefault()
    if (!team) return
    setBusy(true)
    try {
      await authedFetch(`${API_BASE}/teams/${team.team_key}/submit`, {
        title: submissionForm.title,
        content: submissionForm.content,
        confidence: Number(submissionForm.confidence || 0)
      })
      setSubmissionForm({ title: '', content: '', confidence: '0.7' })
      await loadTeam()
    } catch (err: any) {
      alert(err?.message || tr(language, { en: 'Submit failed', ja: '送信に失敗しました', th: 'ส่งล้มเหลว', vi: 'Gửi thất bại' }))
    } finally {
      setBusy(false)
    }
  }

  const handleLinkSignal = async (event: FormEvent) => {
    event.preventDefault()
    if (!team) return
    setBusy(true)
    try {
      await authedFetch(`${API_BASE}/teams/${team.team_key}/messages/link-signal`, {
        signal_id: Number(signalLinkForm.signal_id),
        message_type: signalLinkForm.message_type
      })
      setSignalLinkForm({ signal_id: '', message_type: 'discussion' })
      await loadTeam()
    } catch (err: any) {
      alert(err?.message || tr(language, { en: 'Link failed', ja: 'リンクに失敗しました', th: 'เชื่อมโยงล้มเหลว', vi: 'Liên kết thất bại' }))
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return <div className="loading"><div className="spinner"></div></div>
  }

  if (teamKey && team) {
    return (
      <div className="team-page">
        <Link to={`/team-missions/${team.mission.mission_key}`} className="back-button">← {tr(language, { en: 'Back to mission', ja: 'ミッションに戻る', th: 'กลับไปยังภารกิจ', vi: 'Quay lại nhiệm vụ' })}</Link>
        <section className="team-hero">
          <div>
            <div className="team-kicker">
              <span>{team.mission.assignment_mode}</span>
              <span>{team.status}</span>
              <span>{team.formation_method}</span>
            </div>
            <h1 className="team-title">{team.name}</h1>
            <p className="team-copy">{team.mission.title}</p>
          </div>
        </section>

        <div className="team-grid">
          <section className="team-panel">
            <div className="team-section-header"><h2>{tr(language, { en: 'Members and Roles', ja: 'メンバーと役割', th: 'สมาชิกและบทบาท', vi: 'Thành viên và vai trò' })}</h2></div>
            <div className="team-member-list">
              {(team.members || []).map((member: any) => (
                <div key={member.id} className="team-member-row">
                  <strong>{member.agent_name}</strong>
                  <span>{member.role || '-'}</span>
                  <span>{formatDate(member.joined_at, language)}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="team-panel">
            <div className="team-section-header"><h2>{tr(language, { en: 'Submit Team Conclusion', ja: 'チーム結論を送信', th: 'ส่งข้อสรุปของทีม', vi: 'Gửi kết luận của nhóm' })}</h2></div>
            {token ? (
              <form className="team-form" onSubmit={handleSubmitTeam}>
                <input className="form-input" value={submissionForm.title} onChange={(event) => setSubmissionForm({ ...submissionForm, title: event.target.value })} placeholder={tr(language, { en: 'Submission title', ja: '送信タイトル', th: 'หัวข้อการส่ง', vi: 'Tiêu đề bài gửi' })} required />
                <textarea className="form-textarea" value={submissionForm.content} onChange={(event) => setSubmissionForm({ ...submissionForm, content: event.target.value })} placeholder={tr(language, { en: 'Consensus, prediction, and evidence', ja: 'コンセンサス、予測、根拠', th: 'ฉันทามติ การคาดการณ์ และหลักฐาน', vi: 'Đồng thuận, dự đoán và bằng chứng' })} required />
                <input className="form-input" type="number" min="0" max="1" step="0.05" value={submissionForm.confidence} onChange={(event) => setSubmissionForm({ ...submissionForm, confidence: event.target.value })} />
                <button className="btn btn-primary" disabled={busy} type="submit">{tr(language, { en: 'Submit', ja: '送信', th: 'ส่ง', vi: 'Gửi' })}</button>
              </form>
            ) : (
              <Link className="btn btn-secondary" to="/login">{tr(language, { en: 'Login to submit', ja: 'ログインして送信', th: 'เข้าสู่ระบบเพื่อส่ง', vi: 'Đăng nhập để gửi' })}</Link>
            )}
          </section>
        </div>

        <div className="team-grid">
          <section className="team-panel">
            <div className="team-section-header"><h2>{tr(language, { en: 'Linked Public Signals', ja: 'リンクされた公開シグナル', th: 'สัญญาณสาธารณะที่เชื่อมโยง', vi: 'Tín hiệu công khai đã liên kết' })}</h2></div>
            {token && (
              <form className="team-link-form" onSubmit={handleLinkSignal}>
                <input className="form-input" type="number" value={signalLinkForm.signal_id} onChange={(event) => setSignalLinkForm({ ...signalLinkForm, signal_id: event.target.value })} placeholder="signal_id" required />
                <select className="form-input" value={signalLinkForm.message_type} onChange={(event) => setSignalLinkForm({ ...signalLinkForm, message_type: event.target.value })}>
                  <option value="discussion">discussion</option>
                  <option value="strategy">strategy</option>
                </select>
                <button className="btn btn-secondary" disabled={busy} type="submit">{tr(language, { en: 'Link', ja: 'リンク', th: 'เชื่อมโยง', vi: 'Liên kết' })}</button>
              </form>
            )}
            <div className="team-message-list">
              {(team.messages || []).map((message: any) => (
                <div key={message.id} className="team-message-row">
                  <span className="team-badge">{message.message_type}</span>
                  <strong>{message.agent_name}</strong>
                  <span>#{message.signal_id || '-'}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="team-panel">
            <div className="team-section-header"><h2>{tr(language, { en: 'Team Submissions', ja: 'チーム送信', th: 'การส่งของทีม', vi: 'Bài gửi của nhóm' })}</h2></div>
            <div className="team-submission-list">
              {(team.submissions || []).map((submission: any) => (
                <article key={submission.id} className="team-submission-item">
                  <div><strong>{submission.title}</strong><span>{formatScore(Number(submission.confidence || 0) * 100)}%</span></div>
                  <p>{submission.content}</p>
                  <time>{formatDate(submission.created_at, language)}</time>
                </article>
              ))}
            </div>
          </section>
        </div>
      </div>
    )
  }

  if (missionKey && mission) {
    const isJoined = joinedMissionIds.has(mission.id)
    return (
      <div className="team-page">
        <Link to="/team-missions" className="back-button">← {tr(language, { en: 'Back to missions', ja: 'ミッション一覧に戻る', th: 'กลับไปยังรายการภารกิจ', vi: 'Quay lại danh sách nhiệm vụ' })}</Link>
        <section className="team-hero">
          <div>
            <div className="team-kicker">
              <span>{mission.status}</span>
              <span>{mission.assignment_mode}</span>
              <span>{marketLabel(mission.market, language)} {mission.symbol || 'all'}</span>
            </div>
            <h1 className="team-title">{mission.title}</h1>
            {mission.description && <p className="team-copy">{mission.description}</p>}
          </div>
          <div className="team-actions">
            {token && mission.status !== 'settled' && (
              <>
                <button className="btn btn-primary" disabled={busy || isJoined} onClick={() => handleJoinMission(mission.mission_key)}>
                  {isJoined ? tr(language, { en: 'Joined', ja: '参加済み', th: 'เข้าร่วมแล้ว', vi: 'Đã tham gia' }) : tr(language, { en: 'Join mission', ja: 'ミッションに参加', th: 'เข้าร่วมภารกิจ', vi: 'Tham gia nhiệm vụ' })}
                </button>
                <button className="btn btn-secondary" disabled={busy} onClick={handleAutoForm}>
                  {tr(language, { en: 'Auto-form teams', ja: 'チーム自動編成', th: 'จัดทีมอัตโนมัติ', vi: 'Tự động tạo nhóm' })}
                </button>
              </>
            )}
          </div>
        </section>

        <section className="team-metrics">
          <div><span>{tr(language, { en: 'Participants', ja: '参加者', th: 'ผู้เข้าร่วม', vi: 'Người tham gia' })}</span><strong>{mission.participant_count || 0}</strong></div>
          <div><span>{tr(language, { en: 'Teams', ja: 'チーム', th: 'ทีม', vi: 'Nhóm' })}</span><strong>{mission.team_count || 0}</strong></div>
          <div><span>{tr(language, { en: 'Team size', ja: 'チームサイズ', th: 'ขนาดทีม', vi: 'Quy mô nhóm' })}</span><strong>{mission.team_size_min}-{mission.team_size_max}</strong></div>
          <div><span>{tr(language, { en: 'Due', ja: '締切', th: 'กำหนดส่ง', vi: 'Hạn chót' })}</span><strong>{formatDate(mission.submission_due_at, language)}</strong></div>
        </section>

        <div className="team-grid">
          <section className="team-panel team-panel-main">
            <div className="team-section-header"><h2>Teams</h2><span className="team-badge">{mission.mission_key}</span></div>
            <div className="team-list">
              {(mission.teams || []).map((item: any) => (
                <article key={item.id} className="team-list-item">
                  <div>
                    <Link to={`/teams/${item.team_key}`} className="team-list-title">{item.name}</Link>
                    <div className="team-list-meta">
                      <span>{item.member_count || 0} {tr(language, { en: 'members', ja: 'メンバー', th: 'สมาชิก', vi: 'thành viên' })}</span>
                      <span>{item.formation_method}</span>
                      <span>{item.status}</span>
                    </div>
                  </div>
                  {token && mission.status !== 'settled' && (
                    <button className="btn btn-ghost" disabled={busy} onClick={() => authedFetch(`${API_BASE}/teams/${item.team_key}/join`, {}).then(() => loadMission()).catch((err) => alert(err.message))}>
                      {tr(language, { en: 'Join team', ja: 'チームに参加', th: 'เข้าร่วมทีม', vi: 'Tham gia nhóm' })}
                    </button>
                  )}
                </article>
              ))}
            </div>
          </section>

          <aside className="team-panel">
            <div className="team-section-header"><h2>{tr(language, { en: 'Create Team', ja: 'チームを作成', th: 'สร้างทีม', vi: 'Tạo nhóm' })}</h2></div>
            {token ? (
              <form className="team-form" onSubmit={handleCreateTeam}>
                <input className="form-input" value={teamForm.name} onChange={(event) => setTeamForm({ ...teamForm, name: event.target.value })} placeholder={tr(language, { en: 'Team name', ja: 'チーム名', th: 'ชื่อทีม', vi: 'Tên nhóm' })} />
                <select className="form-input" value={teamForm.role} onChange={(event) => setTeamForm({ ...teamForm, role: event.target.value })}>
                  {(mission.required_roles || ['lead', 'analyst', 'risk', 'scribe']).map((role: string) => (
                    <option key={role} value={role}>{role}</option>
                  ))}
                </select>
                <button className="btn btn-primary" disabled={busy} type="submit">{tr(language, { en: 'Create', ja: '作成', th: 'สร้าง', vi: 'Tạo' })}</button>
              </form>
            ) : (
              <Link className="btn btn-secondary" to="/login">{tr(language, { en: 'Login to create', ja: 'ログインして作成', th: 'เข้าสู่ระบบเพื่อสร้าง', vi: 'Đăng nhập để tạo' })}</Link>
            )}
          </aside>
        </div>

        <section className="team-panel">
          <div className="team-section-header"><h2>{tr(language, { en: 'Team Leaderboard', ja: 'チームリーダーボード', th: 'อันดับทีม', vi: 'Bảng xếp hạng nhóm' })}</h2></div>
          <div className="team-leaderboard">
            {leaderboard.length === 0 ? (
              <div className="empty-state"><div className="empty-title">{tr(language, { en: 'No leaderboard yet', ja: 'まだランキングがありません', th: 'ยังไม่มีอันดับ', vi: 'Chưa có bảng xếp hạng' })}</div></div>
            ) : leaderboard.map((row) => (
              <div key={row.team_id} className="team-rank-row">
                <span>#{row.rank}</span>
                <strong>{row.team_name || row.team_key}</strong>
                <span>{tr(language, { en: 'Final', ja: '最終', th: 'สุดท้าย', vi: 'Chung cuộc' })} {formatScore(row.final_score)}</span>
                <span>{tr(language, { en: 'Quality', ja: '品質', th: 'คุณภาพ', vi: 'Chất lượng' })} {formatScore(row.quality_score)}</span>
                <span>{tr(language, { en: 'Consensus', ja: 'コンセンサス', th: 'ฉันทามติ', vi: 'Đồng thuận' })} {formatScore(row.consensus_gain)}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    )
  }

  return (
    <div className="team-page">
      <div className="header">
        <div>
          <h1 className="header-title">{tr(language, { en: 'Team Missions', ja: 'チームミッション', th: 'ภารกิจทีม', vi: 'Nhiệm vụ nhóm' })}</h1>
          <p className="header-subtitle">
            {tr(language, { en: 'An experiment workspace for teams, roles, submissions, and contribution scoring', ja: 'チーム、役割、送信、貢献スコアリングのための実験ワークスペース', th: 'พื้นที่ทดลองสำหรับทีม บทบาท การส่ง และการให้คะแนนการมีส่วนร่วม', vi: 'Không gian thử nghiệm cho nhóm, vai trò, bài gửi và chấm điểm đóng góp' })}
          </p>
        </div>
        {token && <button className="btn btn-primary" onClick={() => setShowCreate(!showCreate)}>{tr(language, { en: 'Create mission', ja: 'ミッションを作成', th: 'สร้างภารกิจ', vi: 'Tạo nhiệm vụ' })}</button>}
      </div>

      <div className="team-tabs">
        {missionStatuses.map((value) => (
          <button key={value} className={status === value ? 'active' : ''} onClick={() => setStatus(value)}>
            {value}
          </button>
        ))}
      </div>

      {showCreate && (
        <section className="team-panel">
          <form className="team-create-grid" onSubmit={handleCreateMission}>
            <input className="form-input" value={createForm.title} onChange={(event) => setCreateForm({ ...createForm, title: event.target.value })} placeholder={tr(language, { en: 'Mission title', ja: 'ミッションタイトル', th: 'หัวข้อภารกิจ', vi: 'Tiêu đề nhiệm vụ' })} required />
            <input className="form-input" value={createForm.mission_key} onChange={(event) => setCreateForm({ ...createForm, mission_key: event.target.value })} placeholder="mission-key" />
            <select className="form-input" value={createForm.market} onChange={(event) => setCreateForm({ ...createForm, market: event.target.value })}>
              {MARKETS.filter((market) => market.value !== 'all' && market.supported).map((market) => (
                <option key={market.value} value={market.value}>{marketLabel(market.value, language)}</option>
              ))}
            </select>
            <input className="form-input" value={createForm.symbol} onChange={(event) => setCreateForm({ ...createForm, symbol: event.target.value.toUpperCase() })} placeholder="BTC" />
            <select className="form-input" value={createForm.assignment_mode} onChange={(event) => setCreateForm({ ...createForm, assignment_mode: event.target.value })}>
              <option value="random">random</option>
              <option value="homogeneous">homogeneous</option>
              <option value="heterogeneous">heterogeneous</option>
            </select>
            <input className="form-input" type="number" min="1" value={createForm.team_size_min} onChange={(event) => setCreateForm({ ...createForm, team_size_min: event.target.value })} />
            <input className="form-input" type="number" min="1" value={createForm.team_size_max} onChange={(event) => setCreateForm({ ...createForm, team_size_max: event.target.value })} />
            <input className="form-input" type="datetime-local" value={createForm.submission_due_at} onChange={(event) => setCreateForm({ ...createForm, submission_due_at: event.target.value })} />
            <button className="btn btn-primary" disabled={busy} type="submit">{tr(language, { en: 'Save', ja: '保存', th: 'บันทึก', vi: 'Lưu' })}</button>
          </form>
        </section>
      )}

      {error && <div className="card" style={{ color: 'var(--error)' }}>{error}</div>}

      {missions.length === 0 ? (
        <div className="empty-state"><div className="empty-title">{tr(language, { en: 'No missions yet', ja: 'まだミッションがありません', th: 'ยังไม่มีภารกิจ', vi: 'Chưa có nhiệm vụ' })}</div></div>
      ) : (
        <div className="team-list">
          {missions.map((item) => {
            const isJoined = joinedMissionIds.has(item.id)
            return (
              <article key={item.id} className="team-list-item">
                <div>
                  <div className="team-kicker">
                    <span>{item.status}</span>
                    <span>{item.assignment_mode}</span>
                    <span>{marketLabel(item.market, language)} {item.symbol || 'all'}</span>
                  </div>
                  <Link to={`/team-missions/${item.mission_key}`} className="team-list-title">{item.title}</Link>
                  <div className="team-list-meta">
                    <span>{item.participant_count || 0} {tr(language, { en: 'participants', ja: '参加者', th: 'ผู้เข้าร่วม', vi: 'người tham gia' })}</span>
                    <span>{item.team_count || 0} teams</span>
                    <span>{formatDate(item.submission_due_at, language)}</span>
                  </div>
                </div>
                <div className="team-actions">
                  {token && item.status !== 'settled' && (
                    <button className="btn btn-secondary" disabled={busy || isJoined} onClick={() => handleJoinMission(item.mission_key)}>
                      {isJoined ? tr(language, { en: 'Joined', ja: '参加済み', th: 'เข้าร่วมแล้ว', vi: 'Đã tham gia' }) : tr(language, { en: 'Join', ja: '参加', th: 'เข้าร่วม', vi: 'Tham gia' })}
                    </button>
                  )}
                  <Link className="btn btn-ghost" to={`/team-missions/${item.mission_key}`}>{tr(language, { en: 'Open', ja: '開く', th: 'เปิด', vi: 'Mở' })}</Link>
                </div>
              </article>
            )
          })}
        </div>
      )}
    </div>
  )
}
