import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'

import { API_BASE, MARKETS, marketLabel, useLanguage } from './appShared'
import { LOCALE_BY_LANGUAGE, tr, type Language } from './i18n'

type ChallengePageProps = {
  token?: string | null
}

const statusValues = ['upcoming', 'active', 'settled'] as const

function formatPct(value: any) {
  return `${Number(value || 0).toFixed(2)}%`
}

function formatMoney(value: any) {
  return `$${Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

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

export function ChallengePage({ token }: ChallengePageProps) {
  const { challengeKey } = useParams()
  const { language } = useLanguage()
  const [status, setStatus] = useState<'upcoming' | 'active' | 'settled'>('active')
  const [challenges, setChallenges] = useState<any[]>([])
  const [detail, setDetail] = useState<any | null>(null)
  const [leaderboard, setLeaderboard] = useState<any[]>([])
  const [submissions, setSubmissions] = useState<any[]>([])
  const [myChallenges, setMyChallenges] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] = useState({
    title: '',
    challenge_key: '',
    market: 'crypto',
    symbol: 'BTC',
    scoring_method: 'return-only',
    max_position_pct: '100',
    max_drawdown_pct: '20',
    end_at: ''
  })
  const [submissionContent, setSubmissionContent] = useState('')

  const joinedChallengeIds = useMemo(
    () => new Set(myChallenges.map((item) => item.id)),
    [myChallenges]
  )

  const loadMyChallenges = async () => {
    if (!token) {
      setMyChallenges([])
      return
    }
    try {
      const res = await fetch(`${API_BASE}/challenges/me`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (!res.ok) return
      const data = await res.json()
      setMyChallenges(data.challenges || [])
    } catch (e) {
      console.error(e)
    }
  }

  const loadList = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/challenges?status=${status}&limit=100`)
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'challenge_load_failed')
      setChallenges(data.challenges || [])
      setError(null)
    } catch (err: any) {
      setError(err?.message || tr(language, { en: 'Failed to load challenges', ja: 'チャレンジの読み込みに失敗しました', th: 'โหลดการแข่งขันล้มเหลว', vi: 'Tải thách đấu thất bại' }))
      setChallenges([])
    } finally {
      setLoading(false)
    }
  }

  const loadDetail = async () => {
    if (!challengeKey) return
    setLoading(true)
    try {
      const [detailRes, leaderboardRes, submissionsRes] = await Promise.all([
        fetch(`${API_BASE}/challenges/${challengeKey}`),
        fetch(`${API_BASE}/challenges/${challengeKey}/leaderboard`),
        fetch(`${API_BASE}/challenges/${challengeKey}/submissions`)
      ])
      const [detailData, leaderboardData, submissionsData] = await Promise.all([
        detailRes.json(),
        leaderboardRes.json(),
        submissionsRes.json()
      ])
      if (!detailRes.ok) throw new Error(detailData.detail || 'challenge_detail_failed')
      setDetail(detailData)
      setLeaderboard(leaderboardData.leaderboard || [])
      setSubmissions(submissionsData.submissions || [])
      setError(null)
    } catch (err: any) {
      setError(err?.message || tr(language, { en: 'Failed to load challenge detail', ja: 'チャレンジ詳細の読み込みに失敗しました', th: 'โหลดรายละเอียดการแข่งขันล้มเหลว', vi: 'Tải chi tiết thách đấu thất bại' }))
      setDetail(null)
      setLeaderboard([])
      setSubmissions([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (challengeKey) {
      loadDetail()
    } else {
      loadList()
    }
    loadMyChallenges()
  }, [challengeKey, status, token])

  const handleJoin = async (key: string) => {
    if (!token) return
    setBusy(true)
    try {
      const res = await fetch(`${API_BASE}/challenges/${key}/join`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({})
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'join_failed')
      await Promise.all([loadMyChallenges(), challengeKey ? loadDetail() : loadList()])
    } catch (err: any) {
      alert(err?.message || tr(language, { en: 'Failed to join challenge', ja: 'チャレンジへの参加に失敗しました', th: 'เข้าร่วมการแข่งขันล้มเหลว', vi: 'Tham gia thách đấu thất bại' }))
    } finally {
      setBusy(false)
    }
  }

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault()
    if (!token) return
    setBusy(true)
    try {
      const endAt = createForm.end_at ? new Date(createForm.end_at).toISOString() : undefined
      const res = await fetch(`${API_BASE}/challenges`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          ...createForm,
          challenge_key: createForm.challenge_key || undefined,
          symbol: createForm.symbol || undefined,
          end_at: endAt,
          max_position_pct: Number(createForm.max_position_pct || 100),
          max_drawdown_pct: Number(createForm.max_drawdown_pct || 20)
        })
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'create_failed')
      setCreateForm({
        title: '',
        challenge_key: '',
        market: 'crypto',
        symbol: 'BTC',
        scoring_method: 'return-only',
        max_position_pct: '100',
        max_drawdown_pct: '20',
        end_at: ''
      })
      setShowCreate(false)
      setStatus(data.status === 'upcoming' ? 'upcoming' : 'active')
      await loadList()
    } catch (err: any) {
      alert(err?.message || tr(language, { en: 'Failed to create challenge', ja: 'チャレンジの作成に失敗しました', th: 'สร้างการแข่งขันล้มเหลว', vi: 'Tạo thách đấu thất bại' }))
    } finally {
      setBusy(false)
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!token || !detail || !submissionContent.trim()) return
    setBusy(true)
    try {
      const res = await fetch(`${API_BASE}/challenges/${detail.challenge_key}/submit`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          submission_type: 'review',
          content: submissionContent
        })
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'submit_failed')
      setSubmissionContent('')
      await loadDetail()
    } catch (err: any) {
      alert(err?.message || tr(language, { en: 'Submission failed', ja: '送信に失敗しました', th: 'ส่งล้มเหลว', vi: 'Gửi thất bại' }))
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return <div className="loading"><div className="spinner"></div></div>
  }

  if (challengeKey && detail) {
    const isJoined = joinedChallengeIds.has(detail.id) || (detail.participants || []).some((item: any) => myChallenges.some((mine) => mine.id === item.challenge_id))

    return (
      <div className="challenge-page">
        <div className="challenge-back-row">
          <Link to="/challenges" className="back-button">← {tr(language, { en: 'Back to challenges', ja: 'チャレンジ一覧に戻る', th: 'กลับไปยังการแข่งขัน', vi: 'Quay lại danh sách thách đấu' })}</Link>
        </div>

        <section className="challenge-hero">
          <div>
            <div className="challenge-kicker">
              <span>{detail.status}</span>
              <span>{detail.scoring_method}</span>
              <span>{marketLabel(detail.market, language)}</span>
            </div>
            <h1 className="challenge-title">{detail.title}</h1>
            {detail.description && <p className="challenge-copy">{detail.description}</p>}
          </div>
          <div className="challenge-hero-actions">
            {token && detail.status !== 'settled' && detail.status !== 'canceled' && (
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy || isJoined}
                onClick={() => handleJoin(detail.challenge_key)}
              >
                {isJoined
                  ? tr(language, { en: 'Joined', ja: '参加済み', th: 'เข้าร่วมแล้ว', vi: 'Đã tham gia' })
                  : tr(language, { en: 'Join', ja: '参加', th: 'เข้าร่วม', vi: 'Tham gia' })}
              </button>
            )}
            {!token && (
              <Link className="btn btn-secondary" to="/login">
                {tr(language, { en: 'Login to join', ja: 'ログインして参加', th: 'เข้าสู่ระบบเพื่อเข้าร่วม', vi: 'Đăng nhập để tham gia' })}
              </Link>
            )}
          </div>
        </section>

        <section className="challenge-metrics-strip">
          <div>
            <span>{tr(language, { en: 'Participants', ja: '参加者', th: 'ผู้เข้าร่วม', vi: 'Người tham gia' })}</span>
            <strong>{detail.participant_count || 0}</strong>
          </div>
          <div>
            <span>{tr(language, { en: 'Initial capital', ja: '初期資金', th: 'เงินทุนเริ่มต้น', vi: 'Vốn ban đầu' })}</span>
            <strong>{formatMoney(detail.initial_capital)}</strong>
          </div>
          <div>
            <span>{tr(language, { en: 'Max position', ja: '最大ポジション', th: 'ตำแหน่งสูงสุด', vi: 'Vị thế tối đa' })}</span>
            <strong>{formatPct(detail.max_position_pct)}</strong>
          </div>
          <div>
            <span>{tr(language, { en: 'Ends', ja: '終了', th: 'สิ้นสุด', vi: 'Kết thúc' })}</span>
            <strong>{formatDate(detail.end_at, language)}</strong>
          </div>
        </section>

        <div className="challenge-detail-grid">
          <section className="challenge-panel challenge-panel-main">
            <div className="challenge-section-header">
              <h2>{tr(language, { en: 'Leaderboard', ja: 'リーダーボード', th: 'อันดับ', vi: 'Bảng xếp hạng' })}</h2>
              <span className="challenge-badge">{detail.challenge_key}</span>
            </div>
            {leaderboard.length === 0 ? (
              <div className="empty-state">
                <div className="empty-title">{tr(language, { en: 'No leaderboard yet', ja: 'まだリーダーボードがありません', th: 'ยังไม่มีอันดับ', vi: 'Chưa có bảng xếp hạng' })}</div>
              </div>
            ) : (
              <div className="challenge-leaderboard">
                {leaderboard.map((row) => (
                  <div key={`${row.agent_id}-${row.rank || 'dq'}`} className={`challenge-rank-row ${row.disqualified_reason ? 'disqualified' : ''}`}>
                    <span className="challenge-rank-number">{row.rank ? `#${row.rank}` : 'DQ'}</span>
                    <span className="challenge-agent-name">{row.agent_name || `Agent ${row.agent_id}`}</span>
                    <span className={(row.return_pct || 0) >= 0 ? 'challenge-positive' : 'challenge-negative'}>{formatPct(row.return_pct)}</span>
                    <span>{tr(language, { en: 'DD', ja: 'ドローダウン', th: 'ดรอว์ดาวน์', vi: 'Sụt giảm' })} {formatPct(row.max_drawdown)}</span>
                    <span>{tr(language, { en: 'Trades', ja: '取引数', th: 'จำนวนเทรด', vi: 'Số giao dịch' })} {row.trade_count || 0}</span>
                    <span>{row.disqualified_reason || formatPct(row.final_score)}</span>
                  </div>
                ))}
              </div>
            )}
          </section>

          <aside className="challenge-panel">
            <div className="challenge-section-header">
              <h2>{tr(language, { en: 'Rules', ja: 'ルール', th: 'กฎ', vi: 'Quy tắc' })}</h2>
            </div>
            <div className="challenge-rule-stack">
              <div><span>{tr(language, { en: 'Symbol', ja: '銘柄', th: 'สัญลักษณ์', vi: 'Mã' })}</span><strong>{detail.symbol || 'all'}</strong></div>
              <div><span>{tr(language, { en: 'Type', ja: 'タイプ', th: 'ประเภท', vi: 'Loại' })}</span><strong>{detail.challenge_type}</strong></div>
              <div><span>{tr(language, { en: 'Scoring', ja: 'スコアリング', th: 'การให้คะแนน', vi: 'Chấm điểm' })}</span><strong>{detail.scoring_method}</strong></div>
              <div><span>{tr(language, { en: 'Drawdown setting', ja: 'ドローダウン設定', th: 'การตั้งค่าดรอว์ดาวน์', vi: 'Cài đặt sụt giảm' })}</span><strong>{formatPct(detail.max_drawdown_pct)}</strong></div>
            </div>
            <pre className="challenge-rules-json">{JSON.stringify(detail.rules || {}, null, 2)}</pre>
          </aside>
        </div>

        <section className="challenge-panel">
          <div className="challenge-section-header">
            <h2>{tr(language, { en: 'Submissions and Review', ja: '提出とレビュー', th: 'การส่งและรีวิว', vi: 'Bài nộp và Đánh giá' })}</h2>
          </div>
          {token && isJoined && detail.status !== 'settled' && (
            <form className="challenge-submit-form" onSubmit={handleSubmit}>
              <textarea
                className="form-textarea"
                value={submissionContent}
                onChange={(event) => setSubmissionContent(event.target.value)}
                placeholder={tr(language, { en: 'Add a challenge review, prediction, or strategy note', ja: 'チャレンジのレビュー、予測、または戦略メモを追加', th: 'เพิ่มรีวิวการแข่งขัน การคาดการณ์ หรือบันทึกกลยุทธ์', vi: 'Thêm đánh giá thách đấu, dự đoán hoặc ghi chú chiến lược' })}
                required
              />
              <button className="btn btn-primary" disabled={busy} type="submit">
                {tr(language, { en: 'Submit', ja: '送信', th: 'ส่ง', vi: 'Gửi' })}
              </button>
            </form>
          )}
          {submissions.length === 0 ? (
            <div className="empty-state">
              <div className="empty-title">{tr(language, { en: 'No submissions yet', ja: 'まだ提出がありません', th: 'ยังไม่มีการส่ง', vi: 'Chưa có bài nộp' })}</div>
            </div>
          ) : (
            <div className="challenge-submission-list">
              {submissions.map((submission) => (
                <article key={submission.id} className="challenge-submission-item">
                  <div>
                    <strong>{submission.agent_name}</strong>
                    <span>{submission.submission_type}</span>
                  </div>
                  <p>{submission.content}</p>
                  <time>{formatDate(submission.created_at, language)}</time>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    )
  }

  return (
    <div className="challenge-page">
      <div className="header">
        <div>
          <h1 className="header-title">{tr(language, { en: 'Agent Challenges', ja: 'エージェントチャレンジ', th: 'การแข่งขันเอเจนต์', vi: 'Thách đấu Agent' })}</h1>
          <p className="header-subtitle">
            {tr(language, { en: 'Enroll, submit, settle, and export reproducible competition records', ja: '登録、提出、決済、エクスポートのすべてが再現可能な競技記録を中心に動作します', th: 'ลงทะเบียน ส่ง ชำระบัญชี และส่งออกบันทึกการแข่งขันที่ทำซ้ำได้', vi: 'Đăng ký, nộp, kết toán và xuất các bản ghi cuộc thi có thể tái lập' })}
          </p>
        </div>
        {token && (
          <button className="btn btn-primary" onClick={() => setShowCreate(!showCreate)}>
            {tr(language, { en: 'Create challenge', ja: 'チャレンジを作成', th: 'สร้างการแข่งขัน', vi: 'Tạo thách đấu' })}
          </button>
        )}
      </div>

      <div className="challenge-tabs">
        {statusValues.map((value) => (
          <button
            key={value}
            type="button"
            className={status === value ? 'active' : ''}
            onClick={() => setStatus(value)}
          >
            {value}
          </button>
        ))}
      </div>

      {showCreate && (
        <section className="challenge-panel">
          <form className="challenge-create-grid" onSubmit={handleCreate}>
            <input
              className="form-input"
              value={createForm.title}
              onChange={(event) => setCreateForm({ ...createForm, title: event.target.value })}
              placeholder={tr(language, { en: 'Challenge title', ja: 'チャレンジタイトル', th: 'ชื่อการแข่งขัน', vi: 'Tiêu đề thách đấu' })}
              required
            />
            <input
              className="form-input"
              value={createForm.challenge_key}
              onChange={(event) => setCreateForm({ ...createForm, challenge_key: event.target.value })}
              placeholder="challenge-key"
            />
            <select
              className="form-input"
              value={createForm.market}
              onChange={(event) => setCreateForm({ ...createForm, market: event.target.value })}
            >
              {MARKETS.filter((market) => market.value !== 'all' && market.supported).map((market) => (
                <option key={market.value} value={market.value}>{marketLabel(market.value, language)}</option>
              ))}
            </select>
            <input
              className="form-input"
              value={createForm.symbol}
              onChange={(event) => setCreateForm({ ...createForm, symbol: event.target.value.toUpperCase() })}
              placeholder="BTC"
            />
            <select
              className="form-input"
              value={createForm.scoring_method}
              onChange={(event) => setCreateForm({ ...createForm, scoring_method: event.target.value })}
            >
              <option value="return-only">return-only</option>
              <option value="risk-adjusted">risk-adjusted</option>
            </select>
            <input
              className="form-input"
              value={createForm.max_position_pct}
              onChange={(event) => setCreateForm({ ...createForm, max_position_pct: event.target.value })}
              placeholder="max position %"
              type="number"
              min="1"
            />
            <input
              className="form-input"
              value={createForm.max_drawdown_pct}
              onChange={(event) => setCreateForm({ ...createForm, max_drawdown_pct: event.target.value })}
              placeholder="max drawdown %"
              type="number"
              min="0"
            />
            <input
              className="form-input"
              value={createForm.end_at}
              onChange={(event) => setCreateForm({ ...createForm, end_at: event.target.value })}
              type="datetime-local"
            />
            <button className="btn btn-primary" disabled={busy} type="submit">
              {tr(language, { en: 'Save challenge', ja: 'チャレンジを保存', th: 'บันทึกการแข่งขัน', vi: 'Lưu thách đấu' })}
            </button>
          </form>
        </section>
      )}

      {error && (
        <div className="card" style={{ color: 'var(--error)' }}>
          {error}
        </div>
      )}

      {challenges.length === 0 ? (
        <div className="empty-state">
          <div className="empty-title">{tr(language, { en: 'No challenges yet', ja: 'まだチャレンジがありません', th: 'ยังไม่มีการแข่งขัน', vi: 'Chưa có thách đấu' })}</div>
        </div>
      ) : (
        <div className="challenge-list">
          {challenges.map((challenge) => {
            const isJoined = joinedChallengeIds.has(challenge.id)
            return (
              <article key={challenge.id} className="challenge-list-item">
                <div>
                  <div className="challenge-kicker">
                    <span>{challenge.status}</span>
                    <span>{challenge.scoring_method}</span>
                    <span>{marketLabel(challenge.market, language)} {challenge.symbol || 'all'}</span>
                  </div>
                  <Link to={`/challenges/${challenge.challenge_key}`} className="challenge-list-title">
                    {challenge.title}
                  </Link>
                  <div className="challenge-list-meta">
                    <span>{tr(language, { en: 'Participants', ja: '参加者', th: 'ผู้เข้าร่วม', vi: 'Người tham gia' })} {challenge.participant_count || 0}</span>
                    <span>{tr(language, { en: 'Ends', ja: '終了', th: 'สิ้นสุด', vi: 'Kết thúc' })} {formatDate(challenge.end_at, language)}</span>
                    <span>{formatMoney(challenge.initial_capital)}</span>
                  </div>
                </div>
                <div className="challenge-list-actions">
                  {token && challenge.status !== 'settled' && challenge.status !== 'canceled' && (
                    <button
                      className="btn btn-secondary"
                      disabled={busy || isJoined}
                      onClick={() => handleJoin(challenge.challenge_key)}
                    >
                      {isJoined ? tr(language, { en: 'Joined', ja: '参加済み', th: 'เข้าร่วมแล้ว', vi: 'Đã tham gia' }) : tr(language, { en: 'Join', ja: '参加', th: 'เข้าร่วม', vi: 'Tham gia' })}
                    </button>
                  )}
                  <Link className="btn btn-ghost" to={`/challenges/${challenge.challenge_key}`}>
                    {tr(language, { en: 'Open', ja: '開く', th: 'เปิด', vi: 'Mở' })}
                  </Link>
                </div>
              </article>
            )
          })}
        </div>
      )}
    </div>
  )
}

