import { useState } from 'react'
import { tr, type Language } from '../i18n'
import { fmtUsd } from '../pages/tradeShared'

// ga TradingCalculator, compact: PnL / target-price calculator for the
// futures terminal. Pure math, no API — mirrors the terminal's simulator
// model (linear PnL, isolated liq at entry×(1∓(1/L − MMR))).

const MAINTENANCE_MARGIN_RATE = 0.005
const mono: any = { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontVariantNumeric: 'tabular-nums' }
const UP = 'var(--success,#3fb950)', DOWN = 'var(--error,#f0663f)'

export function TradingCalculator({ language, livePrice, onClose }: {
  language: Language
  livePrice: number | null
  onClose: () => void
}) {
  const [tab, setTab] = useState<'pnl' | 'target'>('pnl')
  const [side, setSide] = useState<'long' | 'short'>('long')
  const [leverage, setLeverage] = useState(10)
  const [entry, setEntry] = useState(livePrice ? String(livePrice) : '')
  const [exit, setExit] = useState('')
  const [qty, setQty] = useState('')
  const [roiTarget, setRoiTarget] = useState('')

  const T = {
    title: tr(language, { ko: '계산기', en: 'Calculator', ja: '計算機', th: 'เครื่องคิดเลข', vi: 'Máy tính', id: 'Kalkulator' }),
    pnlTab: tr(language, { ko: '손익', en: 'PnL', ja: '損益', th: 'กำไรขาดทุน', vi: 'PnL', id: 'PnL' }),
    targetTab: tr(language, { ko: '목표가', en: 'Target price', ja: '目標価格', th: 'ราคาเป้าหมาย', vi: 'Giá mục tiêu', id: 'Harga target' }),
    long: tr(language, { ko: '롱', en: 'Long', ja: 'ロング', th: 'Long', vi: 'Long', id: 'Long' }),
    short: tr(language, { ko: '숏', en: 'Short', ja: 'ショート', th: 'Short', vi: 'Short', id: 'Short' }),
    lev: tr(language, { ko: '레버리지', en: 'Leverage', ja: 'レバレッジ', th: 'เลเวอเรจ', vi: 'Đòn bẩy', id: 'Leverage' }),
    entry: tr(language, { ko: '진입 가격', en: 'Entry price', ja: 'エントリー価格', th: 'ราคาเข้า', vi: 'Giá vào', id: 'Harga masuk' }),
    exit: tr(language, { ko: '청산 가격', en: 'Exit price', ja: '決済価格', th: 'ราคาออก', vi: 'Giá thoát', id: 'Harga keluar' }),
    qty: tr(language, { ko: '수량', en: 'Quantity', ja: '数量', th: 'จำนวน', vi: 'Số lượng', id: 'Kuantitas' }),
    roi: tr(language, { ko: '목표 수익률 (ROI %)', en: 'Target ROI (%)', ja: '目標ROI (%)', th: 'ROI เป้าหมาย (%)', vi: 'ROI mục tiêu (%)', id: 'ROI target (%)' }),
    margin: tr(language, { ko: '증거금', en: 'Margin', ja: '証拠金', th: 'มาร์จิน', vi: 'Ký quỹ', id: 'Margin' }),
    pnl: tr(language, { ko: '손익', en: 'PnL', ja: '損益', th: 'กำไรขาดทุน', vi: 'PnL', id: 'PnL' }),
    roiOut: tr(language, { ko: '수익률 (ROI)', en: 'ROI', ja: 'ROI', th: 'ROI', vi: 'ROI', id: 'ROI' }),
    liq: tr(language, { ko: '청산가 (근사치)', en: 'Liq. price (approx)', ja: '清算価格(概算)', th: 'ราคาล้างพอร์ต (ประมาณ)', vi: 'Giá thanh lý (xấp xỉ)', id: 'Harga likuidasi (perkiraan)' }),
    targetOut: tr(language, { ko: '목표 달성 가격', en: 'Price at target ROI', ja: '目標達成価格', th: 'ราคาที่ถึงเป้า', vi: 'Giá đạt mục tiêu', id: 'Harga saat ROI tercapai' }),
    note: tr(language, { ko: '수수료 제외 · 시뮬레이터의 선형 손익 모델 기준입니다.', en: 'Fees excluded · uses the simulator’s linear PnL model.', ja: '手数料抜き・シミュレーターの線形損益モデル。', th: 'ไม่รวมค่าธรรมเนียม · ใช้โมเดล PnL เชิงเส้นของซิมูเลเตอร์', vi: 'Chưa gồm phí · theo mô hình PnL tuyến tính của trình mô phỏng.', id: 'Belum termasuk biaya · memakai model PnL linear simulator.' }),
    close: tr(language, { ko: '닫기', en: 'Close', ja: '閉じる', th: 'ปิด', vi: 'Đóng', id: 'Tutup' }),
  }

  const entryN = parseFloat(entry), exitN = parseFloat(exit), qtyN = parseFloat(qty)
  const roiN = parseFloat(roiTarget)
  const dir = side === 'long' ? 1 : -1
  const valid = Number.isFinite(entryN) && entryN > 0

  const notional = valid && qtyN > 0 ? entryN * qtyN : null
  const margin = notional !== null ? notional / leverage : null
  const pnl = valid && Number.isFinite(exitN) && exitN > 0 && qtyN > 0
    ? (exitN - entryN) * qtyN * dir : null
  const roi = pnl !== null && margin ? (pnl / margin) * 100 : null
  const liq = valid ? entryN * (1 - dir * (1 / leverage - MAINTENANCE_MARGIN_RATE)) : null
  // target: roi% on margin ⇒ price move of entry × roi/(100·L) in the side's direction
  const targetPrice = valid && Number.isFinite(roiN)
    ? entryN * (1 + dir * (roiN / (100 * leverage))) : null

  const inp: any = { width: '100%', padding: '8px 10px', borderRadius: 8, border: '1px solid var(--border-color,#d3c8b6)', background: 'var(--bg-secondary,#fff)', color: 'var(--text-primary,inherit)', ...mono }
  const panel: any = { background: 'var(--bg-card,#fffdf9)', border: '1px solid var(--border-color,#d3c8b6)', borderRadius: 12 }
  const tabBtn = (active: boolean): any => ({ flex: 1, padding: '8px 0', borderRadius: 8, fontWeight: 700, fontSize: 12.5, cursor: 'pointer', border: active ? 'none' : '1px solid var(--border-color,#d3c8b6)', background: active ? 'var(--accent-primary,#c26a45)' : 'transparent', color: active ? 'var(--accent-contrast,#fff)' : 'var(--text-secondary,#8a8073)' })

  const Row = ({ label, value, color }: { label: string; value: string; color?: string }) => (
    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5, padding: '3px 0' }}>
      <span style={{ color: 'var(--text-secondary,#8a8073)' }}>{label}</span>
      <span style={{ ...mono, fontWeight: 600, color: color || 'inherit' }}>{value}</span>
    </div>
  )

  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 60, padding: 20 }}>
      <div onClick={e => e.stopPropagation()} style={{ ...panel, width: 380, padding: 20 }}>
        <div style={{ fontWeight: 800, marginBottom: 12 }}>{T.title}</div>
        <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
          <button onClick={() => setTab('pnl')} style={tabBtn(tab === 'pnl')}>{T.pnlTab}</button>
          <button onClick={() => setTab('target')} style={tabBtn(tab === 'target')}>{T.targetTab}</button>
        </div>
        <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
          <button onClick={() => setSide('long')} style={{ ...tabBtn(side === 'long'), background: side === 'long' ? UP : 'transparent', border: side === 'long' ? 'none' : '1px solid var(--border-color,#d3c8b6)', color: side === 'long' ? '#fff' : 'var(--text-secondary,#8a8073)' }}>{T.long}</button>
          <button onClick={() => setSide('short')} style={{ ...tabBtn(side === 'short'), background: side === 'short' ? DOWN : 'transparent', border: side === 'short' ? 'none' : '1px solid var(--border-color,#d3c8b6)', color: side === 'short' ? '#fff' : 'var(--text-secondary,#8a8073)' }}>{T.short}</button>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
          <span>{T.lev}</span><b style={mono}>{leverage}×</b>
        </div>
        <input type="range" min={1} max={100} value={leverage} onChange={e => setLeverage(+e.target.value)} style={{ width: '100%', marginBottom: 10 }} />

        <label style={{ fontSize: 12, display: 'block', margin: '6px 0 4px' }}>{T.entry}</label>
        <input style={inp} value={entry} onChange={e => setEntry(e.target.value)} placeholder="0.00" />

        {tab === 'pnl' ? (
          <>
            <label style={{ fontSize: 12, display: 'block', margin: '10px 0 4px' }}>{T.exit}</label>
            <input style={inp} value={exit} onChange={e => setExit(e.target.value)} placeholder="0.00" />
            <label style={{ fontSize: 12, display: 'block', margin: '10px 0 4px' }}>{T.qty}</label>
            <input style={inp} value={qty} onChange={e => setQty(e.target.value)} placeholder="0.00" />
            <div style={{ marginTop: 12, borderTop: '1px solid var(--border-color,#e6ddd0)', paddingTop: 8 }}>
              <Row label={T.margin} value={margin !== null ? `${fmtUsd(margin)} USDT` : '—'} />
              <Row label={T.pnl} value={pnl !== null ? `${pnl >= 0 ? '+' : ''}${fmtUsd(pnl)} USDT` : '—'}
                color={pnl === null ? undefined : pnl >= 0 ? UP : DOWN} />
              <Row label={T.roiOut} value={roi !== null ? `${roi >= 0 ? '+' : ''}${roi.toFixed(2)}%` : '—'}
                color={roi === null ? undefined : roi >= 0 ? UP : DOWN} />
              <Row label={T.liq} value={liq !== null && liq > 0 ? fmtUsd(liq) : '—'} />
            </div>
          </>
        ) : (
          <>
            <label style={{ fontSize: 12, display: 'block', margin: '10px 0 4px' }}>{T.roi}</label>
            <input style={inp} value={roiTarget} onChange={e => setRoiTarget(e.target.value)} placeholder="50" />
            <div style={{ marginTop: 12, borderTop: '1px solid var(--border-color,#e6ddd0)', paddingTop: 8 }}>
              <Row label={T.targetOut} value={targetPrice !== null && targetPrice > 0 ? fmtUsd(targetPrice) : '—'}
                color={targetPrice === null ? undefined : UP} />
              <Row label={T.liq} value={liq !== null && liq > 0 ? fmtUsd(liq) : '—'} />
            </div>
          </>
        )}

        <div style={{ marginTop: 10, fontSize: 11, color: 'var(--text-secondary,#8a8073)' }}>{T.note}</div>
        <button onClick={onClose} style={{ width: '100%', marginTop: 12, padding: '10px 0', borderRadius: 8, border: '1px solid var(--border-color,#d3c8b6)', background: 'transparent', color: 'inherit', cursor: 'pointer' }}>{T.close}</button>
      </div>
    </div>
  )
}

export default TradingCalculator
