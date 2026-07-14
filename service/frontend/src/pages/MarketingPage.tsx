import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useLanguage } from '../appShared'
import { tr } from '../i18n'

const LANGS: Record<string, string> = { en: 'EN', ja: 'JA', th: 'TH', vi: 'VI' }

// Public landing page — mirrors jeton.com's real page skeleton 1:1
// (verified against the live site's DOM):
//   hero (coin spiral · headline bottom-left · sub+CTAs right · floating
//   bottom dock · scroll pill · support pill)
//   → "Unify your …" intro with tabbed walkthrough
//   → full-width ORANGE value-props band
//   → light app-hero ("All your …, in one …")
//   → "Sure. / Check. / Also check." feature callout
//   → converter calculator
//   → "Hear it from …" testimonials
//   → extra-bold closer ("… , plus you.")
//   → multi-column dark footer

const ORANGE = '#f73b20'
const CORAL = '#e2551f'
const INK = '#191512'
const MUT = 'rgba(25,21,18,0.6)'
const FAINT = 'rgba(25,21,18,0.42)'
const BG = '#faf7f2'
const CARD = '#ffffff'
const LINE = 'rgba(25,21,18,0.10)'

const mono: any = { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontVariantNumeric: 'tabular-nums' }

export function MarketingPage() {
  const { language, setLanguage } = useLanguage()
  const [btc, setBtc] = useState<{ price: number; pct: number } | null>(null)
  const [usd, setUsd] = useState('1000')
  // Use a real 3D render if service/frontend/public/robot-hero.png exists;
  // otherwise fall back to the built-in SVG robot.
  const [robotImg, setRobotImg] = useState(true)

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const r = await fetch('/api/markets/crypto/ticker?symbol=BTCUSDT')
        if (!r.ok) return
        const d = await r.json()
        if (alive) setBtc({ price: Number(d.last_price), pct: Number(d.price_24h_pct) })
      } catch { /* transient */ }
    }
    load()
    const iv = setInterval(load, 8000)
    return () => { alive = false; clearInterval(iv) }
  }, [])

  // Jeton-style scroll parallax for the "Unify" floating cards.
  useEffect(() => {
    const stage = document.getElementById('uni-stage')
    if (!stage) return
    let raf = 0
    const apply = () => {
      const rect = stage.getBoundingClientRect()
      const offset = (rect.top + rect.height / 2) - window.innerHeight / 2
      stage.querySelectorAll<HTMLElement>('[data-speed]').forEach((el) => {
        const sp = parseFloat(el.dataset.speed || '0')
        el.style.setProperty('--py', `${(-offset * sp).toFixed(1)}px`)
      })
      raf = 0
    }
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(apply) }
    apply()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => { window.removeEventListener('scroll', onScroll); window.removeEventListener('resize', onScroll); if (raf) cancelAnimationFrame(raf) }
  }, [])

  const T = {
    login: tr(language, { en: 'Log in', ja: 'ログイン', th: 'เข้าสู่ระบบ', vi: 'Đăng nhập' }),
    signup: tr(language, { en: 'Sign up', ja: '登録', th: 'สมัคร', vi: 'Đăng ký' }),
    heroH1: tr(language, { en: 'One desk', ja: 'ひとつのデスクで', th: 'โต๊ะเดียว', vi: 'Một bàn giao dịch' }),
    heroH2: tr(language, { en: 'for all trades', ja: 'すべてのトレードを', th: 'สำหรับทุกเทรด', vi: 'cho mọi giao dịch' }),
    heroS: tr(language, { en: 'Single simulated account for all your AI trading.', ja: 'AIトレードのためのひとつの模擬口座。', th: 'บัญชีจำลองเดียวสำหรับการเทรด AI ทั้งหมดของคุณ', vi: 'Một tài khoản mô phỏng cho mọi giao dịch AI.' }),
    thThe: tr(language, { en: 'THE', ja: '最も', th: 'วิธีที่', vi: 'CÁCH' }),
    thEasiest: tr(language, { en: 'EASIEST', ja: 'かんたんな', th: 'ง่ายที่สุด', vi: 'DỄ NHẤT' }),
    thWay: tr(language, { en: 'WAY TO RUN AN', ja: '方法で動かす', th: 'ในการรันบอท', vi: 'ĐỂ CHẠY BOT' }),
    thAi: tr(language, { en: 'AI', ja: 'AI', th: 'AI', vi: 'AI' }),
    thTrading: tr(language, { en: 'TRADING', ja: 'トレーディング', th: 'เทรดดิ้ง', vi: 'GIAO DỊCH' }),
    thBot: tr(language, { en: 'BOT', ja: 'ボット', th: 'บอท', vi: 'BOT' }),
    stBuild: tr(language, { en: 'BUILD', ja: '構築', th: 'สร้าง', vi: 'XÂY' }),
    stAi: tr(language, { en: 'AI', ja: 'AI', th: 'AI', vi: 'AI' }),
    stProfit: tr(language, { en: 'PROFIT', ja: '利益', th: 'กำไร', vi: 'LỢI NHUẬN' }),
    stNote: tr(language, { en: 'paper only', ja: '模擬のみ', th: 'จำลองเท่านั้น', vi: 'chỉ mô phỏng' }),
    ctaSim: tr(language, { en: 'Open simulator', ja: 'シミュレーターを開く', th: 'เปิดตัวจำลอง', vi: 'Mở trình mô phỏng' }),
    ctaBoard: tr(language, { en: 'See leaderboard', ja: 'リーダーボード', th: 'ดูลีดเดอร์บอร์ด', vi: 'Xem bảng xếp hạng' }),
    scroll: tr(language, { en: 'Scroll', ja: 'スクロール', th: 'เลื่อน', vi: 'Cuộn' }),
    support: tr(language, { en: 'Support', ja: 'サポート', th: 'ซัพพอร์ต', vi: 'Hỗ trợ' }),
    dockProduct: tr(language, { en: 'Product', ja: '製品', th: 'ผลิตภัณฑ์', vi: 'Sản phẩm' }),
    dockMarkets: tr(language, { en: 'Markets', ja: 'マーケット', th: 'ตลาด', vi: 'Thị trường' }),
    dockCompany: tr(language, { en: 'Company', ja: '会社', th: 'บริษัท', vi: 'Công ty' }),

    unifyH: tr(language, { en: 'Unify your trading', ja: 'トレードをひとつに', th: 'รวมการเทรดของคุณ', vi: 'Hợp nhất giao dịch' }),
    tabs: [
      tr(language, { en: 'Analyze', ja: '分析', th: 'วิเคราะห์', vi: 'Phân tích' }),
      tr(language, { en: 'Automate', ja: '自動化', th: 'อัตโนมัติ', vi: 'Tự động' }),
      tr(language, { en: 'Spot', ja: '現物', th: 'สปอต', vi: 'Spot' }),
      tr(language, { en: 'Futures', ja: '先物', th: 'ฟิวเจอร์ส', vi: 'Futures' }),
      tr(language, { en: 'Assets', ja: '資産', th: 'ทรัพย์สิน', vi: 'Tài sản' }),
    ],
    tabDesc: [
      tr(language, { en: 'Four AI analysts read news, sentiment, macro and charts — a trader and risk manager debate the call.', ja: '4人のAIアナリストが読み、トレーダーとリスク管理者が議論します。', th: 'นักวิเคราะห์ AI สี่คนอ่านข้อมูล — เทรดเดอร์และผู้จัดการความเสี่ยงถกเถียงกัน', vi: 'Bốn nhà phân tích AI đọc dữ liệu — trader và quản trị rủi ro tranh luận.' }),
      tr(language, { en: 'Set symbol, model, schedule and confidence. It trades only when your rules are met.', ja: '銘柄・モデル・スケジュール・信頼度を設定。条件を満たした時だけ取引。', th: 'ตั้งเหรียญ โมเดล ตาราง และความมั่นใจ มันเทรดเมื่อเข้าเงื่อนไขเท่านั้น', vi: 'Đặt mã, mô hình, lịch và độ tin cậy. Chỉ giao dịch khi đủ điều kiện.' }),
      tr(language, { en: 'A real OKX order book, live prices, instant simulated fills.', ja: '本物のOKX板・ライブ価格・即時の模擬約定。', th: 'สมุดคำสั่ง OKX จริง ราคาสด เติมจำลองทันที', vi: 'Sổ lệnh OKX thật, giá trực tiếp, khớp mô phỏng tức thì.' }),
      tr(language, { en: 'Long or short with 1–100× sizing and a liquidation preview.', ja: '1〜100倍のロング/ショートと清算プレビュー。', th: 'Long/Short ขนาด 1–100× พร้อมพรีวิวล้างพอร์ต', vi: 'Long hoặc short 1–100× kèm xem trước thanh lý.' }),
      tr(language, { en: 'Cash, holdings and PnL in one view — every number reconciles.', ja: '現金・保有・損益をひと目で。', th: 'เงินสด ถือครอง กำไรขาดทุนในหน้าเดียว', vi: 'Tiền, nắm giữ và PnL trong một màn hình.' }),
    ],

    orangeLead: tr(language, { en: 'All markets. One desk.', ja: 'すべての市場を、ひとつのデスクで。', th: 'ทุกตลาด โต๊ะเดียว', vi: 'Mọi thị trường. Một bàn.' }),
    props: [
      { t: tr(language, { en: 'AI that argues before it acts', ja: '行動の前に議論するAI', th: 'AI ที่ถกเถียงก่อนลงมือ', vi: 'AI tranh luận trước khi hành động' }), d: tr(language, { en: 'Every decision ships with a confidence score and written reasoning.', ja: 'すべての判断に信頼度と理由が付属。', th: 'ทุกการตัดสินใจมาพร้อมคะแนนความมั่นใจและเหตุผล', vi: 'Mỗi quyết định kèm điểm tin cậy và lý do.' }) },
      { t: tr(language, { en: 'Trade crypto, US stocks and events', ja: '暗号資産・米国株・イベント市場', th: 'เทรดคริปโต หุ้นสหรัฐ และตลาดเหตุการณ์', vi: 'Crypto, cổ phiếu Mỹ và sự kiện' }), d: tr(language, { en: 'Live prices from OKX, Hyperliquid, Alpha Vantage and Polymarket.', ja: 'OKX・Hyperliquid・Alpha Vantage・Polymarketのライブ価格。', th: 'ราคาสดจาก OKX, Hyperliquid, Alpha Vantage และ Polymarket', vi: 'Giá trực tiếp từ OKX, Hyperliquid, Alpha Vantage, Polymarket.' }) },
      { t: tr(language, { en: '8 AI providers, or your own', ja: '8つのAIプロバイダー', th: 'ผู้ให้บริการ AI 8 ราย หรือของคุณเอง', vi: '8 nhà cung cấp AI, hoặc của bạn' }), d: tr(language, { en: 'OpenAI, Gemini, Grok, Qwen, GLM, Claude, OpenRouter — or a local model.', ja: 'OpenAI・Gemini・Grok・Qwen・GLM・Claude・ローカル。', th: 'OpenAI, Gemini, Grok, Qwen, GLM, Claude — หรือโมเดลโลคอล', vi: 'OpenAI, Gemini, Grok, Qwen, GLM, Claude — hoặc mô hình cục bộ.' }) },
      { t: tr(language, { en: 'Fast and safe transactions', ja: '速くて安全な取引', th: 'ธุรกรรมเร็วและปลอดภัย', vi: 'Giao dịch nhanh và an toàn' }), d: tr(language, { en: 'Because every one of them is simulated. Learn free; risk nothing.', ja: 'すべて模擬取引だから。無料で学び、リスクはゼロ。', th: 'เพราะทั้งหมดเป็นแบบจำลอง เรียนรู้ฟรี ไม่เสี่ยงอะไรเลย', vi: 'Vì tất cả đều mô phỏng. Học miễn phí; không rủi ro.' }) },
    ],

    appHeroH1: tr(language, { en: 'All your trading,', ja: 'すべてのトレードを、', th: 'ทุกการเทรดของคุณ', vi: 'Mọi giao dịch,' }),
    appHeroH2: tr(language, { en: 'in one app.', ja: 'ひとつのアプリに。', th: 'ในแอปเดียว', vi: 'trong một ứng dụng.' }),
    appHeroS: tr(language, { en: 'Join the desk today — it takes a minute.', ja: '今日から参加。1分で始められます。', th: 'เข้าร่วมวันนี้ — ใช้เวลาแค่นาทีเดียว', vi: 'Tham gia hôm nay — chỉ mất một phút.' }),
    getStarted: tr(language, { en: 'Get Started', ja: 'はじめる', th: 'เริ่มต้น', vi: 'Bắt đầu' }),
    phoneTitle: tr(language, { en: 'AI Analyst', ja: 'AIアナリスト', th: 'นักวิเคราะห์ AI', vi: 'Nhà phân tích AI' }),
    phoneBody: tr(language, { en: 'Run your AI analyst desk and paper-trade crypto, US stocks and events — with live prices and zero real money at risk.', ja: 'AIアナリストデスクを動かし、ライブ価格で暗号資産・米国株・イベントを模擬取引。実際の資金はリスクゼロ。', th: 'รันทีมนักวิเคราะห์ AI และเทรดจำลองคริปโต หุ้นสหรัฐ และเหตุการณ์ — ด้วยราคาสด ไม่มีเงินจริงเสี่ยง', vi: 'Chạy bàn phân tích AI và giao dịch mô phỏng crypto, cổ phiếu Mỹ và sự kiện — giá trực tiếp, không rủi ro tiền thật.' }),
    uniOrder: tr(language, { en: 'Order', ja: '注文', th: 'คำสั่ง', vi: 'Lệnh' }),
    uniBalance: tr(language, { en: 'Balance', ja: '残高', th: 'ยอดคงเหลือ', vi: 'Số dư' }),
    uniDecision: tr(language, { en: 'AI decision', ja: 'AIの判断', th: 'การตัดสินใจ AI', vi: 'Quyết định AI' }),
    uniExecuted: tr(language, { en: 'Executed', ja: '執行済み', th: 'ดำเนินการแล้ว', vi: 'Đã thực hiện' }),
    uniAnalyst: tr(language, { en: 'News Analyst', ja: 'ニュースアナリスト', th: 'นักวิเคราะห์ข่าว', vi: 'Phân tích tin' }),
    uniReasoning: tr(language, { en: 'AI reasoning', ja: 'AIの推論', th: 'เหตุผลของ AI', vi: 'Lý luận AI' }),
    uniRun: tr(language, { en: 'Run', ja: '実行', th: 'รัน', vi: 'Chạy' }),
    uniLiveBtc: tr(language, { en: 'Live BTC', ja: 'ライブBTC', th: 'BTC สด', vi: 'BTC trực tiếp' }),
    uniReconciled: tr(language, { en: 'Every number reconciled', ja: '数字はすべて一致', th: 'ตัวเลขตรงทุกตัว', vi: 'Mọi con số đều khớp' }),

    calloutLines: [
      tr(language, { en: 'Leverage? Sure.', ja: 'レバレッジ？もちろん。', th: 'เลเวอเรจ? ได้เลย', vi: 'Đòn bẩy? Có.' }),
      tr(language, { en: 'Live order book? Check.', ja: 'ライブ板？あり。', th: 'สมุดคำสั่งสด? มี', vi: 'Sổ lệnh trực tiếp? Có.' }),
      tr(language, { en: 'Liquidation preview? Also check.', ja: '清算プレビュー？それもあり。', th: 'พรีวิวล้างพอร์ต? ก็มีเช่นกัน', vi: 'Xem trước thanh lý? Cũng có.' }),
    ],
    calloutD: tr(language, { en: 'The futures terminal gives you the full desk — sized 1× to 100×, with the risk math in front of you before you click.', ja: '先物ターミナルは1〜100倍のサイズ設定と、クリック前のリスク計算を提供します。', th: 'เทอร์มินัลฟิวเจอร์สให้ครบทั้งโต๊ะ — ขนาด 1× ถึง 100× พร้อมคณิตความเสี่ยงตรงหน้าก่อนคุณคลิก', vi: 'Terminal futures cho bạn cả bàn làm việc — cỡ 1× đến 100×, phép toán rủi ro ngay trước mắt.' }),
    learnMore: tr(language, { en: 'Learn more', ja: '詳しく', th: 'เรียนรู้เพิ่ม', vi: 'Tìm hiểu thêm' }),

    convH1: tr(language, { en: 'Convert USDT', ja: 'USDTを', th: 'แปลง USDT', vi: 'Chuyển USDT' }),
    convH2: tr(language, { en: 'to BTC easily.', ja: 'BTCへ簡単に。', th: 'เป็น BTC ง่ายๆ', vi: 'sang BTC dễ dàng.' }),
    convD: tr(language, { en: 'Live rate — the same feed your simulated trades fill against.', ja: 'ライブレート。模擬取引が約定するのと同じフィード。', th: 'เรตสด — ฟีดเดียวกับที่เทรดจำลองของคุณใช้', vi: 'Tỷ giá trực tiếp — cùng nguồn giá lệnh mô phỏng của bạn.' }),

    voicesH: tr(language, { en: 'Hear it from the desk', ja: 'デスクからの声', th: 'ฟังจากโต๊ะเทรด', vi: 'Nghe từ bàn làm việc' }),
    voices: [
      { title: tr(language, { en: 'Recommended', ja: 'おすすめ', th: 'แนะนำ', vi: 'Khuyên dùng' }), who: 'News analyst · AI', quote: tr(language, { en: 'Quiet tape. No adverse headlines in 48 hours. Constructive.', ja: '静かな相場。48時間、悪材料なし。', th: 'ตลาดเงียบ ไม่มีข่าวร้ายใน 48 ชม.', vi: 'Thị trường yên. Không tin xấu 48 giờ.' }) },
      { title: tr(language, { en: 'Not euphoric yet', ja: 'まだ過熱ではない', th: 'ยังไม่คลั่ง', vi: 'Chưa hưng phấn' }), who: 'Sentiment analyst · AI', quote: tr(language, { en: 'StockTwits runs 12–4 bullish. A tailwind, not a top.', ja: 'StockTwitsは12対4で強気。追い風だ。', th: 'StockTwits กระทิง 12–4 เป็นลมส่ง ไม่ใช่ยอดดอย', vi: 'StockTwits 12–4 tăng. Gió thuận, chưa phải đỉnh.' }) },
      { title: tr(language, { en: 'No heroics', ja: '無理はしない', th: 'ไม่เล่นใหญ่', vi: 'Không liều' }), who: 'Risk manager · AI', quote: tr(language, { en: 'Small long justified. Stop under 60,000 — that is the deal.', ja: '小さめのロングは妥当。損切りは60,000割れ。', th: 'Long เล็กสมเหตุผล ตัดขาดทุนใต้ 60,000', vi: 'Long nhỏ hợp lý. Cắt lỗ dưới 60.000.' }) },
      { title: tr(language, { en: 'Every number reconciled', ja: '数字はすべて一致', th: 'ตัวเลขตรงทุกตัว', vi: 'Mọi con số đều khớp' }), who: 'demo-bot · resident test agent', quote: tr(language, { en: 'Four trades in. Cash, fees, PnL — all correct. I am a bot; I checked.', ja: '4回取引して現金・手数料・損益すべて正確。ボットの私が確認。', th: 'เทรดไป 4 ครั้ง เงินสด ค่าธรรมเนียม กำไรขาดทุน — ถูกทุกตัว', vi: 'Bốn lệnh. Tiền, phí, PnL — đều đúng. Tôi là bot; tôi đã kiểm.' }) },
    ],

    boldH: tr(language, { en: '$100,000 of pretend money, plus you.', ja: '10万ドルの模擬資金と、あなた。', th: 'เงินปลอม $100,000 บวกกับคุณ', vi: '$100.000 tiền giả, cộng với bạn.' }),
    boldS: tr(language, { en: 'It only takes a few seconds to get started.', ja: '開始まで数秒。', th: 'ใช้เวลาแค่ไม่กี่วินาทีในการเริ่ม', vi: 'Chỉ mất vài giây để bắt đầu.' }),

    footGet: tr(language, { en: 'Get Started', ja: 'はじめる', th: 'เริ่มต้น', vi: 'Bắt đầu' }),
    footDiscover: tr(language, { en: 'Discover', ja: '見る', th: 'สำรวจ', vi: 'Khám phá' }),
    footMarkets: tr(language, { en: 'Markets', ja: 'マーケット', th: 'ตลาด', vi: 'Thị trường' }),
    footHelp: tr(language, { en: 'Help', ja: 'ヘルプ', th: 'ช่วยเหลือ', vi: 'Trợ giúp' }),
    legal: tr(language, {
      en: 'Sooppiy is research and education software. All trading on this platform is simulated: no real funds are held, moved, or at risk. Market data is provided for information only. Nothing on this site is investment advice.',
      ja: 'Sooppiyは研究・教育用ソフトウェアです。すべての取引は模擬であり、実際の資金は保有・移動・リスクにさらされません。投資助言ではありません。',
      th: 'Sooppiy คือซอฟต์แวร์วิจัยและการศึกษา การเทรดทั้งหมดเป็นแบบจำลอง ไม่มีเงินจริง ไม่ใช่คำแนะนำการลงทุน',
      vi: 'Sooppiy là phần mềm nghiên cứu và giáo dục. Mọi giao dịch đều mô phỏng. Không phải lời khuyên đầu tư.',
    }),
  }

  // hand-built product mock panels for the walkthrough
  const mockPanels = [
    <div key={0} style={{ padding: 18 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <b style={{ ...mono, color: '#16a34a', fontSize: 20 }}>BUY</b>
        <span style={mono}>BTC/USDT</span>
        <span style={{ ...mono, marginLeft: 'auto', fontSize: 12, color: MUT }}>confidence 72%</span>
      </div>
      {[['News', 'quiet tape'], ['Sentiment', '12–4 bullish'], ['Macro', 'neutral'], ['Technical', 'above support']].map(([a, b], i) => (
        <div key={i} style={{ display: 'flex', fontSize: 12.5, padding: '5px 0', borderTop: `1px solid ${LINE}`, marginTop: i === 0 ? 10 : 0 }}>
          <span style={{ color: CORAL, minWidth: 84, fontWeight: 600 }}>{a}</span><span style={{ color: MUT }}>{b}</span>
        </div>
      ))}
    </div>,
    <div key={1} style={{ padding: 18, fontSize: 13 }}>
      <div style={{ fontWeight: 700, marginBottom: 10 }}>BTC · crypto</div>
      {[['Run every', '60 min'], ['Min confidence', '65%'], ['Size', '$250'], ['Status', '● active']].map(([a, b], i) => (
        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderTop: `1px solid ${LINE}` }}>
          <span style={{ color: MUT }}>{a}</span><span style={{ ...mono, color: b === '● active' ? '#16a34a' : INK }}>{b}</span>
        </div>
      ))}
    </div>,
    <div key={2} style={{ padding: 18 }}>
      {[[62181.2, 0.33], [62181.0, 12.0]].map(([p, q], i) => (
        <div key={i} style={{ ...mono, display: 'flex', justifyContent: 'space-between', fontSize: 12.5, color: '#dc2626', padding: '3px 0' }}>
          <span>{p.toLocaleString()}</span><span>{q}</span>
        </div>
      ))}
      <div style={{ ...mono, fontWeight: 800, fontSize: 18, color: '#16a34a', padding: '6px 0', borderTop: `1px solid ${LINE}`, borderBottom: `1px solid ${LINE}` }}>
        {btc ? btc.price.toLocaleString(undefined, { maximumFractionDigits: 1 }) : '62,180.0'}
      </div>
      {[[62179.9, 515.7], [62179.6, 0.63]].map(([p, q], i) => (
        <div key={i} style={{ ...mono, display: 'flex', justifyContent: 'space-between', fontSize: 12.5, color: '#16a34a', padding: '3px 0' }}>
          <span>{p.toLocaleString()}</span><span>{q}</span>
        </div>
      ))}
    </div>,
    <div key={3} style={{ padding: 18, fontSize: 13 }}>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <span style={{ flex: 1, textAlign: 'center', background: '#16a34a', color: '#fff', borderRadius: 8, padding: '7px 0', fontWeight: 700 }}>Long</span>
        <span style={{ flex: 1, textAlign: 'center', background: '#dc2626', color: '#fff', borderRadius: 8, padding: '7px 0', fontWeight: 700 }}>Short</span>
      </div>
      {[['Leverage', '10×'], ['Margin', '$500'], ['Liq. (approx)', 'L 56,200 · S 68,400']].map(([a, b], i) => (
        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderTop: `1px solid ${LINE}` }}>
          <span style={{ color: MUT }}>{a}</span><span style={mono}>{b}</span>
        </div>
      ))}
    </div>,
    <div key={4} style={{ padding: 18, fontSize: 13 }}>
      <div style={{ fontSize: 11, color: MUT, letterSpacing: '.08em' }}>TOTAL</div>
      <div style={{ ...mono, fontSize: 24, fontWeight: 800, margin: '2px 0 12px' }}>99,758.43 <span style={{ fontSize: 12, color: MUT }}>USDT</span></div>
      {[['Available funds', '65,019.53'], ['Spot holdings', '29,738.99'], ['Futures', '4,999.92']].map(([a, b], i) => (
        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderTop: `1px solid ${LINE}` }}>
          <span style={{ color: MUT }}>{a}</span><span style={mono}>{b}</span>
        </div>
      ))}
    </div>,
  ]

  const wrap: any = { maxWidth: 1120, margin: '0 auto', padding: '0 24px' }
  const pill: any = { borderRadius: 999, textDecoration: 'none', fontWeight: 700, fontSize: 14.5, display: 'inline-block' }
  const h2: any = { fontSize: 'clamp(30px,4.6vw,52px)', fontWeight: 800, letterSpacing: '-.02em', color: INK, margin: '0 0 14px', lineHeight: 1.08, fontFamily: 'var(--font-ui, Inter, sans-serif)' }
  const cardS: any = { background: CARD, border: `1px solid ${LINE}`, borderRadius: 16, boxShadow: '0 2px 12px rgba(25,21,18,0.05)' }
  const usdN = parseFloat(usd) || 0

  return (
    <div style={{ minHeight: '100vh', background: BG, color: INK, fontFamily: 'var(--font-ui, Inter, sans-serif)' }}>
      <style>{`
        .jt a{transition:opacity .15s,transform .15s} .jt a:hover{opacity:.9}
        .jt-tab{transition:all .15s;cursor:pointer;border:none;background:none}
        @keyframes jtIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
        .jt-hero>*{animation:jtIn .55s ease both}
        .jt-hero>*:nth-child(2){animation-delay:.1s}
        .jt-grid{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
        /* ── AI-trading-bot thumbnail hero ── */
        @keyframes jtDash{from{stroke-dashoffset:2600}to{stroke-dashoffset:0}}
        @keyframes jtGrow{0%,100%{transform:scaleY(1);opacity:.9}50%{transform:scaleY(1.12);opacity:1}}
        @keyframes jtGlow{0%,100%{filter:drop-shadow(0 0 10px rgba(163,230,53,.5))}50%{filter:drop-shadow(0 0 26px rgba(163,230,53,.9))}}
        @keyframes jtBob{0%,100%{transform:translateY(0)}50%{transform:translateY(-14px)}}
        @keyframes jtWave{0%,100%{transform:rotate(-14deg)}50%{transform:rotate(10deg)}}
        @keyframes jtBlink{0%,90%,100%{transform:scaleY(1)}94%{transform:scaleY(.12)}}
        @keyframes jtStep{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}
        @keyframes jtTip{0%,100%{opacity:.6;transform:scale(1)}50%{opacity:1;transform:scale(1.18)}}
        @keyframes jtShadow{0%,100%{transform:scaleX(1);opacity:.9}50%{transform:scaleX(.9);opacity:.68}}
        .jt-candlebar{transform-box:fill-box;transform-origin:bottom;animation:jtGrow var(--d,3.4s) ease-in-out infinite;animation-delay:var(--dl,0s)}
        .jt-bot{animation:jtBob 5.5s ease-in-out infinite}
        .jt-bot-arm{transform-box:fill-box;transform-origin:center bottom;animation:jtWave 3.4s ease-in-out infinite}
        .jt-bot-eye{transform-box:fill-box;transform-origin:center;animation:jtBlink 4.6s ease-in-out infinite}
        .jt-tip{transform-box:fill-box;transform-origin:center;animation:jtTip 1.8s ease-in-out infinite}
        .jt-shadow{transform-box:fill-box;transform-origin:center;animation:jtShadow 5.5s ease-in-out infinite}
        .jt-step{animation:jtStep 3s ease-in-out infinite;animation-delay:var(--dl,0s)}
        .jt-line{stroke-dasharray:2600;animation:jtDash 12s ease-in-out infinite}

        /* Jeton "Unify" floating cards + parallax */
        @keyframes uniFloat{0%,100%{transform:translateY(0) rotate(var(--rot,0deg))}50%{transform:translateY(-16px) rotate(var(--rot,0deg))}}
        .uni-card{position:absolute;transform:translateY(var(--py,0px));transition:transform .12s linear;will-change:transform}
        .uni-float{animation:uniFloat var(--d,6s) ease-in-out infinite;animation-delay:var(--dl,0s);will-change:transform}
        /* Jeton "one app" rotating coil rings + phone */
        @keyframes uniSpin{to{transform:rotate(360deg)}}
        @keyframes uniSpinR{to{transform:rotate(-360deg)}}
        .uni-ring{transform-box:fill-box;transform-origin:center;animation:uniSpin var(--d,80s) linear infinite}
        .uni-ring-r{transform-box:fill-box;transform-origin:center;animation:uniSpinR var(--d,60s) linear infinite}
        @keyframes uniPhone{0%,100%{transform:translateY(0) rotate(-7deg)}50%{transform:translateY(-20px) rotate(-7deg)}}
        .uni-phone{animation:uniPhone 6.5s ease-in-out infinite}
        @media(max-width:900px){
          .uni-stage{min-height:auto!important;gap:16px}
          .uni-card{position:static!important;transform:none!important;margin:8px auto}
          .uni-float{animation:none}
        }
      `}</style>
      <div className="jt">

        {/* ══ HERO — Claude light theme + 3D AI robot ══ */}
        <section style={{ position: 'relative', minHeight: '100vh', overflow: 'hidden', background: 'radial-gradient(115% 95% at 80% 8%, #fdfbf6 0%, #f5efe4 52%, #ece3d3 100%)' }}>

          {/* faint warm grid */}
          <div aria-hidden style={{ position: 'absolute', inset: 0, opacity: 0.5, backgroundImage: 'linear-gradient(rgba(201,100,66,.06) 1px, transparent 1px), linear-gradient(90deg, rgba(201,100,66,.06) 1px, transparent 1px)', backgroundSize: '76px 76px' }} />

          {/* rising candlestick chart, right side (green on cream) */}
          <svg viewBox="0 0 700 500" style={{ position: 'absolute', right: 0, top: '5%', width: 'min(56vw, 740px)', height: '82%', opacity: 0.95 }} aria-hidden>
            {[
              { x: 40, y: 340, h: 70, up: true }, { x: 105, y: 360, h: 55, up: false }, { x: 170, y: 300, h: 85, up: true },
              { x: 235, y: 260, h: 70, up: true }, { x: 300, y: 285, h: 50, up: false }, { x: 365, y: 210, h: 95, up: true },
              { x: 430, y: 170, h: 75, up: true }, { x: 495, y: 195, h: 48, up: false }, { x: 560, y: 110, h: 100, up: true },
              { x: 625, y: 60, h: 85, up: true },
            ].map((c, i) => (
              <g key={i} className="jt-candlebar" style={{ ['--d' as any]: `${3 + (i % 4) * 0.5}s`, ['--dl' as any]: `${-i * 0.4}s` }}>
                <line x1={c.x + 14} y1={c.y - 26} x2={c.x + 14} y2={c.y + c.h + 26} stroke={c.up ? '#16a34a' : '#b6c0c9'} strokeWidth="3" />
                <rect x={c.x} y={c.y} width="28" height={c.h} rx="5" fill={c.up ? '#22c55e' : '#cdd5de'} stroke={c.up ? '#16a34a' : '#aab4bf'} strokeWidth="1.5" />
              </g>
            ))}
            <path className="jt-line" d="M20,400 L110,380 L180,330 L250,300 L320,315 L390,240 L460,205 L530,225 L600,140 L670,80"
              fill="none" stroke="#16a34a" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="2600" />
          </svg>

          {/* ── AI robot mascot: real render if present, else built-in 3D SVG ── */}
          {robotImg ? (
            <img className="jt-bot" src="/robot-hero.png" alt="AI trading robot" onError={() => setRobotImg(false)}
              style={{ position: 'absolute', right: 'max(3vw, calc(50vw - 650px))', bottom: '6vh', width: 'min(36vw, 360px)', height: 'auto', zIndex: 2, filter: 'drop-shadow(0 28px 48px rgba(40,30,24,0.28))' }} />
          ) : (
          <svg className="jt-bot" aria-hidden viewBox="0 0 300 400"
            style={{ position: 'absolute', right: 'max(3vw, calc(50vw - 640px))', bottom: '6vh', width: 'min(34vw, 330px)', height: 'auto', zIndex: 2 }}>
            <defs>
              <radialGradient id="rHead" cx="38%" cy="24%" r="84%">
                <stop offset="0%" stopColor="#ffffff" /><stop offset="52%" stopColor="#eef3f9" /><stop offset="100%" stopColor="#c7d2df" />
              </radialGradient>
              <radialGradient id="rBody" cx="40%" cy="18%" r="92%">
                <stop offset="0%" stopColor="#ffffff" /><stop offset="58%" stopColor="#eaf0f7" /><stop offset="100%" stopColor="#bcc8d6" />
              </radialGradient>
              <linearGradient id="rMetal" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#f4f7fa" /><stop offset="100%" stopColor="#aeb9c6" />
              </linearGradient>
              <linearGradient id="rBlue" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#5b8def" /><stop offset="100%" stopColor="#2f6bdc" />
              </linearGradient>
              <radialGradient id="rVisor" cx="50%" cy="32%" r="82%">
                <stop offset="0%" stopColor="#22304e" /><stop offset="62%" stopColor="#0f1a2e" /><stop offset="100%" stopColor="#070c16" />
              </radialGradient>
              <radialGradient id="rEye" cx="42%" cy="38%" r="66%">
                <stop offset="0%" stopColor="#d4fbff" /><stop offset="38%" stopColor="#5ee6f5" /><stop offset="72%" stopColor="#22c3e6" /><stop offset="100%" stopColor="#0e86b0" />
              </radialGradient>
              <radialGradient id="rTip" cx="50%" cy="40%" r="60%">
                <stop offset="0%" stopColor="#a5f3fc" /><stop offset="60%" stopColor="#22d3ee" /><stop offset="100%" stopColor="#0891b2" />
              </radialGradient>
              <filter id="soft" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="7" /></filter>
              <filter id="eyeGlow" x="-70%" y="-70%" width="240%" height="240%"><feGaussianBlur stdDeviation="3" /></filter>
            </defs>

            {/* ground shadow */}
            <ellipse className="jt-shadow" cx="150" cy="384" rx="96" ry="15" fill="rgba(40,30,24,0.22)" filter="url(#soft)" />

            {/* feet */}
            <ellipse cx="116" cy="360" rx="30" ry="18" fill="url(#rBody)" stroke="#b3bdc8" strokeWidth="1.5" />
            <ellipse cx="184" cy="360" rx="30" ry="18" fill="url(#rBody)" stroke="#b3bdc8" strokeWidth="1.5" />
            <ellipse cx="116" cy="366" rx="24" ry="9" fill="url(#rBlue)" opacity="0.9" />
            <ellipse cx="184" cy="366" rx="24" ry="9" fill="url(#rBlue)" opacity="0.9" />

            {/* right resting arm */}
            <g>
              <rect x="198" y="214" width="24" height="70" rx="12" fill="url(#rMetal)" stroke="#b3bdc8" strokeWidth="1.5" />
              <circle cx="210" cy="288" r="16" fill="url(#rBody)" stroke="#b3bdc8" strokeWidth="1.5" />
              <circle cx="210" cy="288" r="7" fill="url(#rBlue)" opacity="0.85" />
            </g>

            {/* body */}
            <g>
              <rect x="82" y="196" width="136" height="132" rx="52" fill="url(#rBody)" stroke="#bcc8d6" strokeWidth="2" />
              <path d="M98,206 Q150,190 202,206" fill="none" stroke="rgba(255,255,255,0.9)" strokeWidth="4" strokeLinecap="round" opacity="0.8" />
              <ellipse cx="150" cy="208" rx="36" ry="10" fill="rgba(20,25,40,0.06)" />
              {/* chest gauge button */}
              <circle cx="150" cy="262" r="34" fill="url(#rVisor)" stroke="#0b1220" strokeWidth="2" />
              <circle cx="150" cy="262" r="34" fill="none" stroke="#2f6bdc" strokeWidth="2.5" opacity="0.8" />
              <g className="jt-tip" fill="#5ee6f5" style={{ filter: 'drop-shadow(0 0 5px rgba(94,230,245,0.8))' }}>
                <rect x="138" y="258" width="6" height="12" rx="2" /><rect x="147" y="250" width="6" height="20" rx="2" /><rect x="156" y="254" width="6" height="16" rx="2" />
              </g>
            </g>

            {/* left waving arm */}
            <g className="jt-bot-arm">
              <rect x="74" y="150" width="22" height="80" rx="11" fill="url(#rMetal)" stroke="#b3bdc8" strokeWidth="1.5" />
              <circle cx="85" cy="150" r="17" fill="url(#rBody)" stroke="#b3bdc8" strokeWidth="1.5" />
              <circle cx="85" cy="150" r="7" fill="url(#rBlue)" opacity="0.85" />
            </g>

            {/* neck */}
            <rect x="132" y="182" width="36" height="22" rx="9" fill="#cdd6e1" />

            {/* head */}
            <g>
              {/* twin antennae */}
              <rect x="108" y="40" width="5" height="30" rx="2.5" fill="#bcc8d6" transform="rotate(-12 110 55)" />
              <circle className="jt-tip" cx="102" cy="36" r="8" fill="url(#rTip)" style={{ filter: 'drop-shadow(0 0 8px rgba(34,211,238,0.85))' }} />
              <rect x="187" y="40" width="5" height="30" rx="2.5" fill="#bcc8d6" transform="rotate(12 190 55)" />
              <circle className="jt-tip" cx="198" cy="36" r="8" fill="url(#rTip)" style={{ filter: 'drop-shadow(0 0 8px rgba(34,211,238,0.85))' }} />
              {/* ears */}
              <rect x="54" y="110" width="18" height="48" rx="9" fill="url(#rMetal)" stroke="#b3bdc8" strokeWidth="1.5" />
              <circle cx="63" cy="134" r="6" fill="url(#rBlue)" opacity="0.85" />
              <rect x="228" y="110" width="18" height="48" rx="9" fill="url(#rMetal)" stroke="#b3bdc8" strokeWidth="1.5" />
              <circle cx="237" cy="134" r="6" fill="url(#rBlue)" opacity="0.85" />
              {/* head shell */}
              <rect x="66" y="66" width="168" height="128" rx="60" fill="url(#rHead)" stroke="#bcc8d6" strokeWidth="2" />
              {/* top gloss */}
              <ellipse cx="136" cy="98" rx="70" ry="28" fill="#ffffff" opacity="0.5" filter="url(#soft)" />
              {/* visor */}
              <rect x="84" y="92" width="132" height="82" rx="40" fill="url(#rVisor)" stroke="#0b1220" strokeWidth="2" />
              <ellipse cx="150" cy="112" rx="56" ry="14" fill="rgba(120,180,255,0.16)" />
              {/* big round glowing eyes */}
              <g className="jt-bot-eye">
                <circle cx="123" cy="134" r="22" fill="url(#rEye)" filter="url(#eyeGlow)" />
                <circle cx="177" cy="134" r="22" fill="url(#rEye)" filter="url(#eyeGlow)" />
                <circle cx="123" cy="134" r="22" fill="none" stroke="rgba(255,255,255,0.35)" strokeWidth="1.5" />
                <circle cx="177" cy="134" r="22" fill="none" stroke="rgba(255,255,255,0.35)" strokeWidth="1.5" />
                <circle cx="116" cy="127" r="6" fill="#ffffff" opacity="0.9" />
                <circle cx="170" cy="127" r="6" fill="#ffffff" opacity="0.9" />
              </g>
            </g>
          </svg>
          )}

          {/* top bar (light) */}
          <header style={{ position: 'relative', zIndex: 3 }}>
            <div style={{ ...wrap, display: 'flex', alignItems: 'center', gap: 12, height: 78 }}>
              <span style={{ fontWeight: 800, fontSize: 24, color: INK }}>Sooppiy</span>
              <span style={{ marginLeft: 'auto', display: 'flex', gap: 2, background: 'rgba(25,21,18,0.06)', borderRadius: 999, padding: '4px 8px' }}>
                <span aria-hidden style={{ color: FAINT, fontSize: 13, padding: '3px 2px 0 4px' }}>🌐</span>
                {Object.entries(LANGS).map(([code, label]) => (
                  <button key={code} onClick={() => setLanguage(code as any)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 12.5, padding: '4px 6px', color: language === code ? INK : FAINT, fontWeight: language === code ? 700 : 400 }}>{label}</button>
                ))}
              </span>
              <Link to="/login" style={{ ...pill, color: INK, padding: '11px 20px', background: 'rgba(25,21,18,0.06)' }}>{T.login}</Link>
              <Link to="/register" style={{ ...pill, color: '#fff', padding: '11px 22px', background: INK }}>{T.signup}</Link>
            </div>
          </header>

          {/* stacked thumbnail headline, left */}
          <div className="jt-hero" style={{ position: 'absolute', zIndex: 3, left: 'max(24px, calc(50vw - 560px))', top: '15vh', maxWidth: 640, fontFamily: 'var(--font-ui, Inter, sans-serif)' }}>
            <div style={{ fontSize: 'clamp(30px,3.6vw,44px)', fontWeight: 900, color: INK, letterSpacing: '-.01em', lineHeight: 1.05 }}>{T.thThe}</div>
            <div style={{ display: 'inline-block', background: '#a3e635', color: '#0a1a04', fontSize: 'clamp(40px,5.6vw,68px)', fontWeight: 900, letterSpacing: '-.02em', lineHeight: 1, padding: '6px 16px', borderRadius: 10, margin: '8px 0', boxShadow: '0 8px 22px rgba(163,230,53,0.4)' }}>{T.thEasiest}</div>
            <div style={{ fontSize: 'clamp(26px,3.2vw,40px)', fontWeight: 900, color: INK, letterSpacing: '-.01em', lineHeight: 1.1 }}>{T.thWay}</div>
            <div style={{ fontSize: 'clamp(44px,6vw,74px)', fontWeight: 900, lineHeight: 1.04, letterSpacing: '-.02em', margin: '6px 0 0' }}>
              <span style={{ color: '#0891b2' }}>{T.thAi}</span>{' '}
              <span style={{ color: INK }}>{T.thTrading}</span>{' '}
              <span style={{ color: '#15803d' }}>{T.thBot}</span>
            </div>

            {/* BUILD → AI → PROFIT strip */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 34, flexWrap: 'wrap' }}>
              {[
                { icon: '</>', label: T.stBuild, color: '#0891b2' },
                { icon: '🧠', label: T.stAi, color: '#15803d' },
                { icon: '📈', label: T.stProfit, color: '#15803d', note: T.stNote },
              ].map((s, i) => (
                <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                  <span className="jt-step" style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'center', gap: 6, ['--dl' as any]: `${-i}s` }}>
                    <span style={{ width: 62, height: 50, borderRadius: 12, border: `2px solid ${s.color}`, background: '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: s.icon === '</>' ? 17 : 22, fontWeight: 800, color: s.color, fontFamily: 'ui-monospace,monospace', boxShadow: '0 4px 14px rgba(25,21,18,0.08)' }}>{s.icon}</span>
                    <span style={{ fontSize: 12.5, fontWeight: 800, color: INK, letterSpacing: '.08em' }}>{s.label}{s.note && <span style={{ fontWeight: 500, color: FAINT, textTransform: 'lowercase' }}> · {s.note}</span>}</span>
                  </span>
                  {i < 2 && <span style={{ color: '#15803d', fontWeight: 900, fontSize: 20, marginBottom: 20 }}>›</span>}
                </span>
              ))}
            </div>

            {/* sub + CTAs */}
            <p style={{ fontSize: 16, fontWeight: 600, color: MUT, margin: '30px 0 14px', lineHeight: 1.5, maxWidth: 440 }}>{T.heroS}</p>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <Link to="/register" style={{ ...pill, background: '#a3e635', color: '#0a1a04', padding: '13px 24px', fontSize: 15 }}>◐ {T.ctaSim}</Link>
              <Link to="/login" style={{ ...pill, background: '#fff', color: INK, padding: '13px 24px', fontSize: 15, border: `1.5px solid ${INK}` }}>◆ {T.ctaBoard}</Link>
            </div>
          </div>

          {/* scroll pill bottom-left */}
          <span style={{ position: 'absolute', zIndex: 3, left: 22, bottom: 20, fontSize: 12, color: MUT, background: 'rgba(25,21,18,0.06)', padding: '7px 14px', borderRadius: 999 }}>⌄ {T.scroll}</span>
          {/* support pill bottom-right */}
          <a href="mailto:support@sooppiy.app" style={{ position: 'absolute', zIndex: 3, right: 22, bottom: 20, fontSize: 13, fontWeight: 600, color: '#fff', background: INK, padding: '10px 18px', borderRadius: 999, textDecoration: 'none' }}>💬 {T.support}</a>
        </section>

        {/* ══ floating bottom dock (Jeton's signature nav) — persists on scroll ══ */}
        <nav style={{ position: 'fixed', zIndex: 60, left: '50%', transform: 'translateX(-50%)', bottom: 18, display: 'flex', alignItems: 'center', gap: 4, background: ORANGE, borderRadius: 999, padding: '7px 10px', boxShadow: '0 14px 40px rgba(180,40,20,0.35)' }}>
          <a href="#top" onClick={e => { e.preventDefault(); window.scrollTo({ top: 0, behavior: 'smooth' }) }}
            style={{ width: 34, height: 34, borderRadius: '50%', background: '#fff', color: ORANGE, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 15, textDecoration: 'none' }}>⌂</a>
          <a href="#product" style={{ color: '#fff', textDecoration: 'none', fontSize: 13.5, fontWeight: 700, padding: '8px 14px' }}>{T.dockProduct} ⌄</a>
          <Link to="/login" style={{ color: '#fff', textDecoration: 'none', fontSize: 13.5, fontWeight: 700, padding: '8px 14px' }}>{T.dockMarkets} ↗</Link>
          <a href="#voices" style={{ color: '#fff', textDecoration: 'none', fontSize: 13.5, fontWeight: 700, padding: '8px 14px' }}>{T.dockCompany} ⌄</a>
        </nav>

        {/* ══ 1 · "Unify" — big centred headline with floating cards (Jeton) ══ */}
        <section id="product" style={{ padding: '11vh 0' }}>
          <div id="uni-stage" className="uni-stage" style={{ position: 'relative', maxWidth: 1180, margin: '0 auto', padding: '0 24px', minHeight: 760, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <h2 style={{ fontSize: 'clamp(56px,9.2vw,132px)', fontWeight: 800, letterSpacing: '-.035em', lineHeight: 0.92, color: ORANGE, textAlign: 'center', margin: 0, maxWidth: 640, fontFamily: 'var(--font-ui, Inter, sans-serif)', position: 'relative', zIndex: 1 }}>
              {T.unifyH}
            </h2>

            {/* order card (blue) — top right */}
            <div className="uni-card" data-speed="0.05" style={{ top: 8, right: -6 }}>
              <div className="uni-float" style={{ ['--d' as any]: '6.5s', ['--rot' as any]: '3deg', background: '#fff', border: '2px solid #3b82f6', borderRadius: 26, padding: 20, width: 258, boxShadow: '0 34px 70px -24px rgba(30,60,120,0.4)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontWeight: 700, fontSize: 15 }}>🟢 BTC/USDT <span style={{ marginLeft: 'auto', color: '#3b82f6', fontSize: 12 }}>▾</span></div>
                <div style={{ ...mono, fontSize: 40, fontWeight: 800, margin: '12px 0 2px', letterSpacing: '-.02em' }}>$250</div>
                <div style={{ fontSize: 13, color: MUT }}>{T.uniBalance}: $65,019.53</div>
                <div style={{ marginTop: 16, textAlign: 'center', background: '#eef4ff', color: '#2563eb', borderRadius: 14, padding: '11px 0', fontWeight: 700, fontSize: 14.5 }}>{T.ctaSim.split(' ')[0]} · {T.uniOrder}</div>
              </div>
            </div>

            {/* AI decision card (green) — left */}
            <div className="uni-card" data-speed="0.09" style={{ top: 176, left: -8 }}>
              <div className="uni-float" style={{ ['--d' as any]: '7.5s', ['--dl' as any]: '-1.5s', ['--rot' as any]: '-4deg', background: 'linear-gradient(160deg,#28cd66,#18b957)', color: '#fff', borderRadius: 26, padding: 22, width: 260, boxShadow: '0 34px 66px -22px rgba(24,185,87,0.55)' }}>
                <div style={{ fontSize: 13.5, fontWeight: 700, opacity: 0.92 }}>⇄ {T.uniDecision}</div>
                <div style={{ ...mono, fontSize: 32, fontWeight: 800, marginTop: 10, letterSpacing: '-.01em' }}>BUY · 72%</div>
                <div style={{ ...mono, fontSize: 16, fontWeight: 700, opacity: 0.95, marginTop: 2 }}>BTC/USDT</div>
                <div style={{ marginTop: 16, display: 'inline-block', background: 'rgba(255,255,255,0.28)', borderRadius: 999, padding: '5px 14px', fontSize: 13, fontWeight: 700 }}>✓ {T.uniExecuted}</div>
              </div>
            </div>

            {/* analyst card (pink) — bottom centre */}
            <div className="uni-card" data-speed="0.07" style={{ bottom: 6, left: '41%' }}>
              <div className="uni-float" style={{ ['--d' as any]: '6.8s', ['--dl' as any]: '-3s', ['--rot' as any]: '2deg', background: '#fbe3f1', borderRadius: 26, padding: 20, width: 236, boxShadow: '0 34px 66px -24px rgba(160,40,120,0.32)' }}>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
                  <span style={{ width: 48, height: 48, borderRadius: '50%', background: 'linear-gradient(135deg,#ec4899,#a855f7)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 16 }}>NA</span>
                  <span style={{ fontWeight: 700, color: '#a21caf', fontSize: 15 }}>{T.uniAnalyst}</span>
                </div>
                <div style={{ textAlign: 'center', fontSize: 12.5, color: '#9d5b86', margin: '12px 0' }}>🔒 {T.uniReasoning}</div>
                <div style={{ textAlign: 'center', background: '#fff', borderRadius: 14, padding: '10px 0', fontWeight: 700, fontSize: 14.5, color: '#a21caf' }}>{T.uniRun}</div>
              </div>
            </div>

            {/* live BTC mini-chart tile — top left */}
            <div className="uni-card" data-speed="0.12" style={{ top: 24, left: '9%' }}>
              <div className="uni-float" style={{ ['--d' as any]: '8s', ['--dl' as any]: '-2s', ['--rot' as any]: '-6deg', background: '#fff', borderRadius: 22, padding: 16, width: 174, boxShadow: '0 30px 60px -24px rgba(20,80,50,0.32)' }}>
                <div style={{ fontSize: 12.5, fontWeight: 700, color: MUT, marginBottom: 8 }}>{T.uniLiveBtc}</div>
                <svg viewBox="0 0 140 48" style={{ width: '100%', height: 48 }} aria-hidden>
                  <polyline points="4,42 26,32 44,36 68,20 88,28 110,12 136,5" fill="none" stroke="#16a34a" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <div style={{ ...mono, fontSize: 17, fontWeight: 800, marginTop: 8 }}>{btc ? `$${btc.price.toLocaleString()}` : '$62,180'}</div>
              </div>
            </div>

            {/* leaderboard tile — bottom right */}
            <div className="uni-card" data-speed="0.10" style={{ bottom: 56, right: '3%' }}>
              <div className="uni-float" style={{ ['--d' as any]: '7s', ['--dl' as any]: '-4s', ['--rot' as any]: '5deg', background: '#fff', borderRadius: 22, padding: 16, width: 224, boxShadow: '0 30px 60px -24px rgba(30,25,20,0.28)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, fontSize: 15 }}>🏆 demo-bot <span style={{ marginLeft: 'auto', color: '#16a34a' }}>#1</span></div>
                <div style={{ marginTop: 12, background: BG, borderRadius: 14, padding: '10px 14px', fontSize: 12.5, color: MUT }}>“{T.uniReconciled}”</div>
              </div>
            </div>
          </div>
        </section>

        {/* ══ 2 · ORANGE value-props band (Jeton walkthrough band) ══ */}
        <section style={{ background: ORANGE, color: '#fff', padding: '9vh 0' }}>
          <div style={wrap}>
            <div style={{ fontSize: 14, fontWeight: 700, letterSpacing: '.06em', opacity: 0.85, marginBottom: 8 }}>{T.orangeLead}</div>
            <div className="jt-grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(230px,1fr))' }}>
              {T.props.map((p, i) => (
                <div key={i} style={{ borderTop: '2px solid rgba(255,255,255,0.35)', paddingTop: 16 }}>
                  <div style={{ fontWeight: 800, fontSize: 18, lineHeight: 1.25, marginBottom: 8 }}>{p.t}</div>
                  <div style={{ fontSize: 14, lineHeight: 1.6, opacity: 0.85 }}>{p.d}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ══ 3 · "All your trading, in one app." — full-bleed coil + phone (Jeton) ══ */}
        <section style={{ position: 'relative', overflow: 'hidden', minHeight: '94vh', display: 'flex', alignItems: 'center', background: 'linear-gradient(118deg,#0f6f66 0%,#2b8078 26%,#a94f47 66%,#cf897f 100%)' }}>
          {/* 3D-style coiled torus (bead rings) */}
          <svg viewBox="0 0 900 900" preserveAspectRatio="xMidYMid slice" aria-hidden
            style={{ position: 'absolute', right: '-10%', top: '50%', transform: 'translateY(-50%)', width: 'min(128vh, 1200px)', height: 'min(128vh, 1200px)' }}>
            <defs>
              <linearGradient id="gCoilA" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#e7a498" /><stop offset="48%" stopColor="#b5544a" /><stop offset="100%" stopColor="#7d352f" /></linearGradient>
              <linearGradient id="gCoilB" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#6fc7bb" /><stop offset="50%" stopColor="#2b8b81" /><stop offset="100%" stopColor="#155249" /></linearGradient>
              <radialGradient id="gCore" cx="42%" cy="38%" r="70%"><stop offset="0%" stopColor="#e9b4a8" /><stop offset="100%" stopColor="#c07c72" /></radialGradient>
              <radialGradient id="gVig" cx="62%" cy="50%" r="60%"><stop offset="60%" stopColor="rgba(0,0,0,0)" /><stop offset="100%" stopColor="rgba(20,40,40,0.35)" /></radialGradient>
              <filter id="coilShadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="10" stdDeviation="10" floodColor="#3a1a16" floodOpacity="0.35" /></filter>
            </defs>
            <circle cx="450" cy="450" r="200" fill="url(#gCore)" />
            {/* outer clay coil */}
            <g className="uni-ring" style={{ ['--d' as any]: '150s' }} filter="url(#coilShadow)">
              {Array.from({ length: 72 }).map((_, i) => {
                const a = (i / 72) * Math.PI * 2, R = 372, cx = 450 + R * Math.cos(a), cy = 450 + R * Math.sin(a)
                return <rect key={i} x={cx - 40} y={cy - 11} width={80} height={22} rx={11} fill="url(#gCoilA)" transform={`rotate(${a * 180 / Math.PI} ${cx} ${cy})`} />
              })}
            </g>
            {/* inner teal coil */}
            <g className="uni-ring-r" style={{ ['--d' as any]: '110s' }} filter="url(#coilShadow)">
              {Array.from({ length: 60 }).map((_, i) => {
                const a = (i / 60) * Math.PI * 2, R = 288, cx = 450 + R * Math.cos(a), cy = 450 + R * Math.sin(a)
                return <rect key={i} x={cx - 42} y={cy - 12} width={84} height={24} rx={12} fill="url(#gCoilB)" transform={`rotate(${a * 180 / Math.PI} ${cx} ${cy})`} />
              })}
            </g>
            <circle cx="450" cy="450" r="450" fill="url(#gVig)" />
          </svg>

          <div style={{ ...wrap, position: 'relative', zIndex: 2, display: 'flex', alignItems: 'center', gap: 30, flexWrap: 'wrap', width: '100%' }}>
            {/* left copy */}
            <div style={{ flex: '1 1 400px' }}>
              <h2 style={{ fontSize: 'clamp(46px,6.6vw,86px)', fontWeight: 800, letterSpacing: '-.025em', lineHeight: 0.98, color: '#fff', margin: 0, fontFamily: 'var(--font-ui, Inter, sans-serif)', textShadow: '0 2px 30px rgba(20,40,40,0.3)' }}>
                {T.appHeroH1}<br />{T.appHeroH2}
              </h2>
              <p style={{ fontSize: 18, color: 'rgba(255,255,255,0.92)', margin: '24px 0 32px' }}>{T.appHeroS}</p>
              <Link to="/register" style={{ ...pill, background: '#fff', color: ORANGE, padding: '16px 34px', fontSize: 16.5 }}>{T.getStarted}</Link>
            </div>

            {/* phone mockup */}
            <div style={{ flex: '0 1 340px', display: 'flex', justifyContent: 'center', position: 'relative' }}>
              <div aria-hidden style={{ position: 'absolute', inset: '-8% -4%', borderRadius: '50%', background: 'radial-gradient(closest-side, rgba(255,255,255,0.22), transparent)' }} />
              <div className="uni-phone" style={{ width: 300, background: 'linear-gradient(160deg,#20242e,#05070c)', borderRadius: 52, padding: 12, boxShadow: '0 50px 110px rgba(0,0,0,0.5), 0 0 0 2px rgba(255,255,255,0.12), inset 0 0 0 6px #0a0d16', position: 'relative', zIndex: 1 }}>
                <div style={{ position: 'relative', borderRadius: 42, overflow: 'hidden', background: 'linear-gradient(168deg,#f9536f 0%,#f77a5f 52%,#f6a468 100%)', height: 588, padding: '20px 20px 0' }}>
                  {/* dynamic island */}
                  <div style={{ position: 'absolute', top: 12, left: '50%', transform: 'translateX(-50%)', width: 108, height: 30, background: '#05070c', borderRadius: 999, display: 'flex', alignItems: 'center', justifyContent: 'flex-end', paddingRight: 12 }}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#1d2b3a' }} />
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', color: '#fff', fontSize: 12, fontWeight: 700 }}><span>20:22</span><span style={{ letterSpacing: 1 }}>▂▃▅ ᯤ ▮</span></div>
                  <div style={{ color: '#fff', marginTop: 44 }}>
                    <div style={{ fontSize: 30, fontWeight: 800, letterSpacing: '-.015em' }}>{T.phoneTitle}</div>
                    <p style={{ fontSize: 13, lineHeight: 1.6, color: 'rgba(255,255,255,0.94)', marginTop: 12 }}>{T.phoneBody}</p>
                  </div>
                  {/* tilted decision cards */}
                  <div style={{ position: 'absolute', left: 30, bottom: 40, width: 172, height: 108, borderRadius: 20, background: 'linear-gradient(140deg,#ffe0cc,#f8875f)', transform: 'rotate(-12deg)', boxShadow: '0 22px 46px rgba(120,30,20,0.4)', padding: 14 }}>
                    <div style={{ ...mono, color: '#7a2e18', fontWeight: 800, fontSize: 17 }}>BUY 72%</div>
                    <div style={{ ...mono, color: 'rgba(122,46,24,0.8)', fontSize: 12, marginTop: 5 }}>BTC · executed</div>
                  </div>
                  <div style={{ position: 'absolute', right: 26, bottom: 84, width: 134, height: 84, borderRadius: 16, background: 'rgba(255,255,255,0.94)', transform: 'rotate(9deg)', boxShadow: '0 16px 38px rgba(120,30,20,0.3)', padding: 12 }}>
                    <div style={{ ...mono, color: '#16a34a', fontWeight: 800, fontSize: 15 }}>+ paper</div>
                    <div style={{ ...mono, color: '#6b7280', fontSize: 11, marginTop: 4 }}>live price</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ══ 4 · feature callout — Jeton's "Sure. / Check. / Also check." ══ */}
        <section style={{ ...wrap, padding: '8vh 24px', display: 'flex', gap: 40, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ flex: '1 1 340px' }}>
            <h2 style={{ ...h2, fontSize: 'clamp(26px,3.8vw,42px)' }}>
              {T.calloutLines.map((l, i) => <span key={i} style={{ display: 'block' }}>{l}</span>)}
            </h2>
            <p style={{ fontSize: 16.5, lineHeight: 1.7, color: MUT, marginBottom: 20 }}>{T.calloutD}</p>
            <Link to="/register" style={{ ...pill, background: ORANGE, color: '#fff', padding: '12px 24px', fontSize: 15 }}>{T.learnMore}</Link>
          </div>
          <div style={{ ...cardS, flex: '0 1 340px', margin: '0 auto', overflow: 'hidden' }}>
            <div style={{ height: 10, background: `linear-gradient(90deg, ${ORANGE}, #f9a06b)` }} />
            {mockPanels[3]}
          </div>
        </section>

        {/* ══ 5 · converter calculator ("Convert fiat cash easily.") ══ */}
        <section style={{ ...wrap, padding: '9vh 24px', textAlign: 'center' }}>
          <h2 style={{ ...h2, fontSize: 'clamp(34px,5vw,58px)' }}>{T.convH1}<br />{T.convH2}</h2>
          <p style={{ color: MUT, marginBottom: 28 }}>{T.convD}</p>
          <div style={{ ...cardS, display: 'inline-flex', alignItems: 'center', gap: 16, padding: '20px 28px', flexWrap: 'wrap', justifyContent: 'center', borderRadius: 24 }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ width: 30, height: 30, borderRadius: '50%', background: '#16a34a', color: '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 13 }}>$</span>
              <input value={usd} onChange={e => setUsd(e.target.value.replace(/[^0-9.]/g, ''))}
                style={{ ...mono, width: 110, fontSize: 17, fontWeight: 700, border: `1px solid ${LINE}`, borderRadius: 10, padding: '8px 10px', background: BG, color: INK }} />
              <b>USDT</b>
            </span>
            <span style={{ color: ORANGE, fontWeight: 800, fontSize: 20 }}>⇄</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ width: 30, height: 30, borderRadius: '50%', background: '#f7931a', color: '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 13 }}>₿</span>
              <b style={{ ...mono, fontSize: 17 }}>{btc ? (usdN / btc.price).toFixed(6) : '…'}</b>
              <b>BTC</b>
            </span>
            <span style={{ ...mono, fontSize: 12.5, color: btc && btc.pct >= 0 ? '#16a34a' : '#dc2626', width: '100%', textAlign: 'center' }}>
              {btc ? `1 BTC = ${btc.price.toLocaleString()} USDT · ${btc.pct >= 0 ? '+' : ''}${btc.pct.toFixed(2)}% 24h · live` : 'loading live price…'}
            </span>
          </div>
        </section>

        {/* ══ 6 · testimonials ("Hear it from our clients") ══ */}
        <section id="voices" style={{ ...wrap, padding: '8vh 24px' }}>
          <h2 style={{ ...h2, textAlign: 'center', marginBottom: 32 }}>{T.voicesH}</h2>
          <div className="jt-grid">
            {T.voices.map((v, i) => (
              <div key={i} style={{ ...cardS, padding: '22px 20px', borderRadius: 20 }}>
                <div style={{ color: ORANGE, fontSize: 13, letterSpacing: 2 }}>★★★★★</div>
                <div style={{ fontWeight: 800, fontSize: 16.5, margin: '10px 0 6px' }}>{v.title}</div>
                <p style={{ fontSize: 14, lineHeight: 1.6, color: MUT, margin: '0 0 14px' }}>{v.quote}</p>
                <div style={{ fontSize: 12.5, fontWeight: 700, color: FAINT }}>{v.who}</div>
              </div>
            ))}
          </div>
        </section>

        {/* ══ 7 · extra-bold closer ("1 million users, plus you.") ══ */}
        <section style={{ background: 'linear-gradient(135deg,#f2607a,#f9a06b)', padding: '13vh 24px', textAlign: 'center' }}>
          <h2 style={{ ...h2, color: '#fff', fontSize: 'clamp(38px,6.4vw,74px)', maxWidth: 900, margin: '0 auto 14px' }}>{T.boldH}</h2>
          <p style={{ color: 'rgba(255,255,255,0.85)', fontSize: 17.5, margin: '0 0 32px' }}>{T.boldS}</p>
          <Link to="/register" style={{ ...pill, background: '#fff', color: CORAL, padding: '15px 32px', fontSize: 16.5 }}>{T.signup}</Link>
        </section>

        {/* ══ 8 · footer (multi-column) ══ */}
        <footer style={{ background: INK, color: 'rgba(250,247,242,0.7)', padding: '8vh 24px 12vh' }}>
          <div style={{ ...wrap, display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))', gap: 28 }}>
            <div>
              <div style={{ fontWeight: 800, fontSize: 19, color: ORANGE, marginBottom: 10 }}>Sooppiy</div>
              <div style={{ fontSize: 13, lineHeight: 1.6 }}>AI · analyze · automate<br />EN · 日本語 · ไทย · Tiếng Việt</div>
            </div>
            {[
              [T.footGet, [[T.signup, '/register'], [T.login, '/login']]],
              [T.footDiscover, [['AI Analyst', '/login'], ['Automation', '/login'], ['Spot', '/login'], ['Futures', '/login']]],
              [T.footMarkets, [['Leaderboard', '/login'], ['Financial events', '/login'], ['Copy trading', '/login']]],
              [T.footHelp, [['For developers', '/login'], ['Support', 'mailto:support@sooppiy.app']]],
            ].map(([title, links]: any, i) => (
              <div key={i}>
                <div style={{ fontWeight: 700, color: '#faf7f2', marginBottom: 12, fontSize: 14 }}>{title}</div>
                {links.map(([label, href]: any) => (
                  href.startsWith('/')
                    ? <Link key={label} to={href} style={{ display: 'block', color: 'inherit', textDecoration: 'none', fontSize: 13.5, padding: '4px 0' }}>{label}</Link>
                    : <a key={label} href={href} style={{ display: 'block', color: 'inherit', textDecoration: 'none', fontSize: 13.5, padding: '4px 0' }}>{label}</a>
                ))}
              </div>
            ))}
          </div>
          <div style={{ ...wrap, borderTop: '1px solid rgba(250,247,242,0.14)', marginTop: 36, paddingTop: 22, fontSize: 12, lineHeight: 1.65, color: 'rgba(250,247,242,0.45)' }}>
            {T.legal}
            <div style={{ marginTop: 8 }}>© 2026 Sooppiy.</div>
          </div>
        </footer>
      </div>
    </div>
  )
}

export default MarketingPage
