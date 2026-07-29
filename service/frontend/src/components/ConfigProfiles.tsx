import { useEffect, useState } from 'react'
import { API_BASE, useLanguage } from '../appShared'
import { tr } from '../i18n'

// Named config profiles (Plan 06 C3). A profile is a saved bundle of the
// knobs tuned together — risk limits + trading guidelines — that can be
// switched, exported and imported.
//
// Lives on the Automation page because these are AGENT-scoped (claw_ token);
// Settings holds the user token and cannot reach /api/risk/*.
//
// Saving or importing never changes live risk — only Apply does, and the
// backend re-validates through the same model the risk endpoint uses, so a
// pasted profile can never carry a limit the normal editor would refuse.

interface Props { token?: string | null }

interface Profile {
  id: number
  name: string
  limits: Record<string, number | boolean>
  guidelines?: string
  updated_at?: string
}

export function ConfigProfiles({ token }: Props) {
  const { language } = useLanguage()
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [open, setOpen] = useState(false)

  const auth: any = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }

  const T = {
    title: tr(language, { ko: '설정 프로필', en: 'Config profiles', ja: '設定プロファイル', th: 'โปรไฟล์การตั้งค่า', vi: 'Hồ sơ cấu hình', id: 'Profil konfigurasi' }),
    subtitle: tr(language, { ko: '리스크 한도와 지침을 이름 붙여 저장하고 전환합니다', en: 'Save your risk limits + guidelines under a name and switch between them', ja: 'リスク上限と指針を名前を付けて保存・切替', th: 'บันทึกลิมิตความเสี่ยงและแนวทางเป็นชื่อ', vi: 'Lưu giới hạn rủi ro và chỉ dẫn theo tên', id: 'Simpan batas risiko + panduan Anda dengan sebuah nama dan berpindah di antaranya' }),
    save: tr(language, { ko: '현재 설정 저장', en: 'Save current', ja: '現在の設定を保存', th: 'บันทึกปัจจุบัน', vi: 'Lưu hiện tại', id: 'Simpan yang sekarang' }),
    namePh: tr(language, { ko: '프로필 이름 (예: 보수적)', en: 'Profile name (e.g. Cautious)', ja: 'プロファイル名', th: 'ชื่อโปรไฟล์', vi: 'Tên hồ sơ', id: 'Nama profil (mis. Hati-hati)' }),
    apply: tr(language, { ko: '적용', en: 'Apply', ja: '適用', th: 'ใช้', vi: 'Áp dụng', id: 'Terapkan' }),
    del: tr(language, { ko: '삭제', en: 'Delete', ja: '削除', th: 'ลบ', vi: 'Xóa', id: 'Hapus' }),
    exportBtn: tr(language, { ko: '내보내기', en: 'Export', ja: 'エクスポート', th: 'ส่งออก', vi: 'Xuất', id: 'Ekspor' }),
    importBtn: tr(language, { ko: 'JSON 가져오기', en: 'Import JSON', ja: 'JSONを取込', th: 'นำเข้า JSON', vi: 'Nhập JSON', id: 'Impor JSON' }),
    empty: tr(language, { ko: '저장된 프로필이 없습니다.', en: 'No saved profiles yet.', ja: '保存されたプロファイルはありません。', th: 'ยังไม่มีโปรไฟล์', vi: 'Chưa có hồ sơ nào.', id: 'Belum ada profil tersimpan.' }),
    applied: tr(language, { ko: '프로필이 적용되었습니다', en: 'Profile applied', ja: 'プロファイルを適用しました', th: 'ใช้โปรไฟล์แล้ว', vi: 'Đã áp dụng hồ sơ', id: 'Profil diterapkan' }),
    saved: tr(language, { ko: '저장되었습니다', en: 'Saved', ja: '保存しました', th: 'บันทึกแล้ว', vi: 'Đã lưu', id: 'Tersimpan' }),
    imported: tr(language, { ko: '가져왔습니다 — 적용하려면 [적용]을 누르세요', en: 'Imported — press Apply to use it', ja: '取り込みました — 適用するには[適用]', th: 'นำเข้าแล้ว — กด ใช้ เพื่อใช้งาน', vi: 'Đã nhập — nhấn Áp dụng để dùng', id: 'Terimpor — tekan Terapkan untuk memakainya' }),
    confirmApply: tr(language, { ko: '이 프로필의 리스크 한도와 지침으로 덮어씁니다. 계속할까요?', en: 'This overwrites your live risk limits and guidelines. Continue?', ja: '現在のリスク上限と指針を上書きします。続けますか？', th: 'จะเขียนทับลิมิตและแนวทางปัจจุบัน ดำเนินการต่อ?', vi: 'Sẽ ghi đè giới hạn và chỉ dẫn hiện tại. Tiếp tục?', id: 'Ini akan menimpa batas risiko dan panduan aktif Anda. Lanjutkan?' }),
    importPrompt: tr(language, { ko: '프로필 JSON을 붙여넣으세요', en: 'Paste the profile JSON', ja: 'プロファイルJSONを貼り付け', th: 'วาง JSON ของโปรไฟล์', vi: 'Dán JSON hồ sơ', id: 'Tempel JSON profil' }),
    note: tr(language, { ko: '저장·가져오기는 현재 설정을 바꾸지 않습니다. [적용]을 눌러야 반영되며, 서버가 한도를 다시 검증합니다.', en: 'Saving and importing never change your live setup — only Apply does, and the server re-validates every limit.', ja: '保存・取込は現在の設定を変更しません。適用時のみ反映され、サーバーが上限を再検証します。', th: 'การบันทึก/นำเข้าไม่เปลี่ยนการตั้งค่าปัจจุบัน', vi: 'Lưu và nhập không thay đổi cài đặt hiện tại.', id: 'Menyimpan dan mengimpor tidak pernah mengubah pengaturan aktif Anda — hanya Terapkan yang melakukannya, dan server memvalidasi ulang setiap batas.' }),
  }

  const flash = (m: string) => { setMsg(m); setErr(''); setTimeout(() => setMsg(''), 2600) }

  async function load() {
    if (!token) return
    try {
      const r = await fetch(`${API_BASE}/risk/profiles`, { headers: auth })
      if (!r.ok) return
      const d = await r.json()
      setProfiles(d.profiles || [])
    } catch { /* transient */ }
  }

  useEffect(() => { if (open) load() }, [open, token])

  async function saveCurrent() {
    const n = name.trim()
    if (!n || busy) return
    setBusy(true); setErr('')
    try {
      const r = await fetch(`${API_BASE}/risk/profiles`, {
        method: 'POST', headers: auth, body: JSON.stringify({ name: n }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'save failed')
      setName(''); flash(T.saved); await load()
    } catch (e: any) { setErr(e.message) }
    setBusy(false)
  }

  async function apply(p: Profile) {
    if (!confirm(T.confirmApply)) return
    setBusy(true); setErr('')
    try {
      const r = await fetch(`${API_BASE}/risk/profiles/${p.id}/apply`, { method: 'POST', headers: auth })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'apply failed')
      flash(T.applied)
    } catch (e: any) { setErr(e.message) }
    setBusy(false)
  }

  async function remove(p: Profile) {
    setBusy(true); setErr('')
    try {
      await fetch(`${API_BASE}/risk/profiles/${p.id}`, { method: 'DELETE', headers: auth })
      await load()
    } catch (e: any) { setErr(e.message) }
    setBusy(false)
  }

  function exportOne(p: Profile) {
    const blob = { name: p.name, limits: p.limits, guidelines: p.guidelines || '' }
    navigator.clipboard?.writeText(JSON.stringify(blob, null, 2))
    flash(tr(language, { ko: 'JSON이 클립보드에 복사되었습니다', en: 'JSON copied to clipboard', ja: 'JSONをコピーしました', th: 'คัดลอก JSON แล้ว', vi: 'Đã sao chép JSON', id: 'JSON disalin ke papan klip' }))
  }

  async function importOne() {
    const text = prompt(T.importPrompt)
    if (!text) return
    setBusy(true); setErr('')
    try {
      const parsed = JSON.parse(text)
      const r = await fetch(`${API_BASE}/risk/profiles/import`, {
        method: 'POST', headers: auth, body: JSON.stringify(parsed),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'import failed')
      flash(T.imported); await load()
    } catch (e: any) {
      setErr(e instanceof SyntaxError ? 'Invalid JSON' : e.message)
    }
    setBusy(false)
  }

  if (!token) return null

  return (
    <div className="card" style={{ marginBottom: 18 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}
           onClick={() => setOpen(o => !o)}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 700, fontSize: 14 }}>🗂 {T.title}</div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary,#8a8073)' }}>{T.subtitle}</div>
        </div>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{open ? '▲' : '▼'}</span>
      </div>

      {open && (
        <div style={{ marginTop: 14 }}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
            <input value={name} onChange={e => setName(e.target.value)} placeholder={T.namePh}
              maxLength={60}
              onKeyDown={e => { if (e.key === 'Enter') saveCurrent() }}
              style={{ flex: 1, minWidth: 180, padding: '8px 11px', borderRadius: 8, fontSize: 12.5,
                       border: '1px solid var(--border-color)', background: 'var(--bg-secondary)',
                       color: 'var(--text-primary)' }} />
            <button onClick={saveCurrent} disabled={busy || !name.trim()} className="btn btn-secondary"
              style={{ fontSize: 12.5, padding: '8px 14px', opacity: busy || !name.trim() ? 0.6 : 1 }}>
              {T.save}
            </button>
            <button onClick={importOne} disabled={busy} className="btn btn-secondary"
              style={{ fontSize: 12.5, padding: '8px 14px' }}>{T.importBtn}</button>
          </div>

          {msg && <div style={{ fontSize: 12, color: '#3fb950', marginBottom: 8 }}>✓ {msg}</div>}
          {err && <div style={{ fontSize: 12, color: 'var(--error,#d03b3b)', marginBottom: 8 }}>⚠️ {err}</div>}

          {profiles.length === 0 ? (
            <div style={{ fontSize: 12.5, color: 'var(--text-secondary,#8a8073)' }}>{T.empty}</div>
          ) : profiles.map(p => (
            <div key={p.id} style={{
              display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
              padding: '9px 0', borderTop: '1px solid var(--border-color)',
            }}>
              <div style={{ flex: 1, minWidth: 140 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{p.name}</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  SL {((Number(p.limits?.stop_loss_pct) || 0) * 100).toFixed(1)}% ·
                  {' '}TP {((Number(p.limits?.take_profit_pct) || 0) * 100).toFixed(1)}% ·
                  {' '}max/day ${Number(p.limits?.max_daily_loss_usd) || 0}
                  {p.guidelines ? ' · ✎' : ''}
                </div>
              </div>
              <button onClick={() => apply(p)} disabled={busy} className="btn btn-secondary"
                style={{ fontSize: 11.5, padding: '5px 12px' }}>{T.apply}</button>
              <button onClick={() => exportOne(p)} className="btn btn-secondary"
                style={{ fontSize: 11.5, padding: '5px 12px' }}>{T.exportBtn}</button>
              <button onClick={() => remove(p)} disabled={busy} className="btn btn-secondary"
                style={{ fontSize: 11.5, padding: '5px 10px', color: 'var(--error,#d03b3b)' }}>{T.del}</button>
            </div>
          ))}

          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 12, lineHeight: 1.55 }}>
            {T.note}
          </div>
        </div>
      )}
    </div>
  )
}

export default ConfigProfiles
