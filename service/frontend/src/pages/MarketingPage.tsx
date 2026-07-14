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

/* Paper Ledger palette (design/theme: paper · ink · terracotta) */
const ORANGE = '#c2553b'                 /* terracotta accent */
const CORAL = '#a13a26'                  /* deep rust */
const INK = '#24211b'
const MUT = '#55503f'
const FAINT = 'rgba(36,33,27,0.45)'
const BG = '#faf8f3'                     /* paper */
const CARD = '#ffffff'
const LINE = '#e7e1d3'
const UP = '#47764f'                     /* ledger green */

const mono: any = { fontFamily: '"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,monospace', fontVariantNumeric: 'tabular-nums' }
const serif: any = { fontFamily: '"Source Serif 4","Noto Serif JP",Georgia,serif' }

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

  // Jeton "Unify" scroll convergence: as the section moves toward viewport centre
  // the floating cards fly in from a wide spread and scale up to rest, reversing on
  // scroll-up. Driven by a rAF loop gated to when the section is near the viewport
  // (IntersectionObserver) so it reacts to any scroll and stays idle-cheap off-screen.
  useEffect(() => {
    const stage = document.getElementById('uni-stage')
    if (!stage) return
    const cards = Array.from(stage.querySelectorAll<HTMLElement>('.uni-card'))
    const apply = () => {
      const vh = window.innerHeight
      const rect = stage.getBoundingClientRect()
      const offset = (rect.top + rect.height / 2) - vh / 2
      const p = Math.max(0, Math.min(1, 1 - offset / (vh * 0.6))) // 0 spread → 1 converged
      const e = p * p * (3 - 2 * p) // smoothstep
      const spread = 1 - e
      for (const el of cards) {
        const dx = parseFloat(el.dataset.dx || '0')
        const dy = parseFloat(el.dataset.dy || '0')
        el.style.setProperty('--tx', `${(dx * spread).toFixed(1)}px`)
        el.style.setProperty('--ty', `${(dy * spread).toFixed(1)}px`)
        el.style.setProperty('--sc', (0.7 + 0.3 * e).toFixed(3))
        el.style.setProperty('--op', (0.5 + 0.5 * e).toFixed(3))
      }
    }
    let raf = 0, active = false
    const loop = () => { apply(); if (active) raf = requestAnimationFrame(loop) }
    const io = new IntersectionObserver((ents) => {
      const vis = ents.some((en) => en.isIntersecting)
      if (vis && !active) { active = true; loop() }
      else if (!vis && active) { active = false; if (raf) cancelAnimationFrame(raf); raf = 0 }
    }, { rootMargin: '200px 0px 200px 0px' })
    io.observe(stage)
    apply()
    return () => { active = false; if (raf) cancelAnimationFrame(raf); io.disconnect() }
  }, [])

  const T = {
    login: tr(language, { en: 'Log in', ja: 'ログイン', th: 'เข้าสู่ระบบ', vi: 'Đăng nhập' }),
    signup: tr(language, { en: 'Sign up', ja: '登録', th: 'สมัคร', vi: 'Đăng ký' }),
    heroH1: tr(language, { en: 'One desk', ja: 'ひとつのデスクで', th: 'โต๊ะเดียว', vi: 'Một bàn giao dịch' }),
    heroH2: tr(language, { en: 'for all trades', ja: 'すべてのトレードを', th: 'สำหรับทุกเทรด', vi: 'cho mọi giao dịch' }),
    heroS: tr(language, { en: 'Your AI reads the news, economic data, trending markets and price charts — then trades automatically on the rules you set. Tracked on live prices. Paper only, no real orders.', ja: 'あなたのAIがニュース・経済指標・トレンド市場・価格チャートを読み取り、あなたが設定したルールで自動売買。すべてライブ価格で追跡、模擬のみで実注文なし。', th: 'AI ของคุณอ่านข่าว ข้อมูลเศรษฐกิจ ตลาดที่กำลังมาแรง และกราฟราคา — แล้วเทรดอัตโนมัติตามกฎที่คุณตั้ง ติดตามด้วยราคาสด จำลองเท่านั้น ไม่มีคำสั่งจริง', vi: 'AI của bạn đọc tin tức, dữ liệu kinh tế, thị trường xu hướng và biểu đồ giá — rồi giao dịch tự động theo quy tắc bạn đặt. Theo giá trực tiếp. Chỉ mô phỏng, không lệnh thật.' }),
    thThe: tr(language, { en: 'TRADING ON', ja: '自動売買を', th: 'เทรดแบบ', vi: 'GIAO DỊCH' }),
    thEasiest: tr(language, { en: 'AUTOPILOT', ja: 'オートパイロット', th: 'ออโต้ไพลอต', vi: 'TỰ ĐỘNG' }),
    thWay: tr(language, { en: 'POWERED BY', ja: 'で動かす', th: 'ขับเคลื่อนโดย', vi: 'DẪN DẮT BỞI' }),
    thAi: tr(language, { en: 'AI', ja: 'AI', th: 'AI', vi: 'AI' }),
    thBot: tr(language, { en: 'ANALYSIS', ja: '分析', th: 'การวิเคราะห์', vi: 'PHÂN TÍCH' }),
    stBuild: tr(language, { en: 'CONFIGURE', ja: '設定', th: 'ตั้งค่า', vi: 'CẤU HÌNH' }),
    stAi: tr(language, { en: 'ANALYZE', ja: '分析', th: 'วิเคราะห์', vi: 'PHÂN TÍCH' }),
    stProfit: tr(language, { en: 'AUTO-TRADE', ja: '自動売買', th: 'เทรดอัตโนมัติ', vi: 'TỰ ĐỘNG' }),
    stNote: tr(language, { en: 'paper only', ja: '模擬のみ', th: 'จำลองเท่านั้น', vi: 'chỉ mô phỏng' }),
    ctaSim: tr(language, { en: 'Start trading', ja: 'トレードを始める', th: 'เริ่มเทรด', vi: 'Bắt đầu' }),
    ctaBoard: tr(language, { en: 'See leaderboard', ja: 'リーダーボード', th: 'ดูลีดเดอร์บอร์ด', vi: 'Xem bảng xếp hạng' }),
    scroll: tr(language, { en: 'Scroll', ja: 'スクロール', th: 'เลื่อน', vi: 'Cuộn' }),
    support: tr(language, { en: 'Support', ja: 'サポート', th: 'ซัพพอร์ต', vi: 'Hỗ trợ' }),
    dockProduct: tr(language, { en: 'Product', ja: '製品', th: 'ผลิตภัณฑ์', vi: 'Sản phẩm' }),
    dockMarkets: tr(language, { en: 'Markets', ja: 'マーケット', th: 'ตลาด', vi: 'Thị trường' }),
    dockCompany: tr(language, { en: 'Company', ja: '会社', th: 'บริษัท', vi: 'Công ty' }),

    unifyH: tr(language, { en: 'One AI reads it all', ja: 'ひとつのAIが全てを読む', th: 'AI เดียว อ่านทุกอย่าง', vi: 'Một AI đọc tất cả' }),
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
      tr(language, { en: 'A live order book, real-time prices, instant simulated fills.', ja: 'ライブ板・リアルタイム価格・即時の模擬約定。', th: 'สมุดคำสั่งสด ราคาเรียลไทม์ เติมจำลองทันที', vi: 'Sổ lệnh trực tiếp, giá thời gian thực, khớp mô phỏng tức thì.' }),
      tr(language, { en: 'Long or short with 1–100× sizing and a liquidation preview.', ja: '1〜100倍のロング/ショートと清算プレビュー。', th: 'Long/Short ขนาด 1–100× พร้อมพรีวิวล้างพอร์ต', vi: 'Long hoặc short 1–100× kèm xem trước thanh lý.' }),
      tr(language, { en: 'Cash, holdings and PnL in one view — every number reconciles.', ja: '現金・保有・損益をひと目で。', th: 'เงินสด ถือครอง กำไรขาดทุนในหน้าเดียว', vi: 'Tiền, nắm giữ và PnL trong một màn hình.' }),
    ],

    orangeLead: tr(language, { en: 'How it works.', ja: '仕組み。', th: 'ทำงานอย่างไร', vi: 'Cách hoạt động.' }),
    props: [
      { t: tr(language, { en: 'AI reads the whole market', ja: 'AIが市場全体を読む', th: 'AI อ่านทั้งตลาด', vi: 'AI đọc toàn thị trường' }), d: tr(language, { en: 'News, economic data, trending markets and price charts — your AI analyzes them all before every trade, with a confidence score and written reasoning.', ja: 'ニュース・経済指標・トレンド市場・価格チャートを、AIが取引前にすべて分析。信頼度スコアと根拠付き。', th: 'ข่าว ข้อมูลเศรษฐกิจ ตลาดมาแรง และกราฟราคา — AI วิเคราะห์ทั้งหมดก่อนทุกการเทรด พร้อมคะแนนความมั่นใจและเหตุผล', vi: 'Tin tức, dữ liệu kinh tế, thị trường xu hướng và biểu đồ giá — AI phân tích tất cả trước mỗi lệnh, kèm điểm tin cậy và lý do.' }) },
      { t: tr(language, { en: 'Trades on your rules', ja: 'あなたのルールで売買', th: 'เทรดตามกฎของคุณ', vi: 'Giao dịch theo quy tắc của bạn' }), d: tr(language, { en: 'Set the symbol, model, schedule, size and confidence threshold. It trades automatically — only when your conditions are met.', ja: '銘柄・モデル・スケジュール・サイズ・信頼度のしきい値を設定。条件を満たした時だけ自動で売買。', th: 'ตั้งเหรียญ โมเดล ตาราง ขนาด และเกณฑ์ความมั่นใจ มันเทรดอัตโนมัติเมื่อเข้าเงื่อนไขเท่านั้น', vi: 'Đặt mã, mô hình, lịch, khối lượng và ngưỡng tin cậy. Giao dịch tự động — chỉ khi đủ điều kiện của bạn.' }) },
      { t: tr(language, { en: 'Crypto, US stocks & predictions', ja: '暗号資産・米国株・予測市場', th: 'คริปโต หุ้นสหรัฐ และตลาดทำนาย', vi: 'Crypto, cổ phiếu Mỹ & dự đoán' }), d: tr(language, { en: 'Live prices from Hyperliquid, Alpha Vantage and Polymarket — positions tracked by polling, never routed to a real broker.', ja: 'Hyperliquid・Alpha Vantage・Polymarketのライブ価格。ポジションは価格ポーリングで追跡し、実際のブローカーには送りません。', th: 'ราคาสดจาก Hyperliquid, Alpha Vantage และ Polymarket โพซิชันติดตามด้วยการดึงราคา ไม่ส่งไปโบรกเกอร์จริง', vi: 'Giá trực tiếp từ Hyperliquid, Alpha Vantage và Polymarket — vị thế theo dõi bằng polling, không gửi tới broker thật.' }) },
      { t: tr(language, { en: 'Backtest before you automate', ja: '自動化の前にバックテスト', th: 'แบ็กเทสต์ก่อนใช้อัตโนมัติ', vi: 'Backtest trước khi tự động' }), d: tr(language, { en: 'Test any strategy on historical data, then let it run live — with reputation, scoring and leaderboards to keep it honest.', ja: '戦略を過去データでテストしてからライブ運用。評価・スコア・リーダーボードで健全性を担保。', th: 'ทดสอบกลยุทธ์กับข้อมูลย้อนหลัง แล้วปล่อยรันจริง พร้อมชื่อเสียง คะแนน และลีดเดอร์บอร์ด', vi: 'Kiểm tra chiến lược trên dữ liệu lịch sử, rồi chạy thật — với uy tín, điểm số và bảng xếp hạng.' }) },
    ],

    appHeroH1: tr(language, { en: 'Trading on autopilot,', ja: '自動売買を、', th: 'เทรดแบบออโต้', vi: 'Giao dịch tự động,' }),
    appHeroH2: tr(language, { en: 'configured by you.', ja: 'あなたの設定で。', th: 'ตั้งค่าโดยคุณ', vi: 'do bạn cấu hình.' }),
    appHeroS: tr(language, { en: 'Set it up once — your AI watches the markets and trades for you. Takes a minute.', ja: '一度設定すれば、AIが市場を監視して代わりに売買。1分で完了。', th: 'ตั้งค่าครั้งเดียว — AI เฝ้าตลาดและเทรดให้คุณ ใช้เวลาแค่นาทีเดียว', vi: 'Cài đặt một lần — AI theo dõi thị trường và giao dịch cho bạn. Chỉ mất một phút.' }),
    getStarted: tr(language, { en: 'Get Started', ja: 'はじめる', th: 'เริ่มต้น', vi: 'Bắt đầu' }),
    phoneTitle: tr(language, { en: 'AI Analyst', ja: 'AIアナリスト', th: 'นักวิเคราะห์ AI', vi: 'Nhà phân tích AI' }),
    phoneBody: tr(language, { en: 'Configure your AI once — it reads news, economic data and charts to trade crypto, US stocks and prediction markets automatically. Tracked on live prices, no real money at risk.', ja: 'AIを一度設定すれば、ニュース・経済指標・チャートを読んで暗号資産・米国株・予測市場を自動売買。ライブ価格で追跡、実際の資金はリスクゼロ。', th: 'ตั้งค่า AI ครั้งเดียว — มันอ่านข่าว ข้อมูลเศรษฐกิจ และกราฟ เพื่อเทรดคริปโต หุ้นสหรัฐ และตลาดทำนายอัตโนมัติ ติดตามด้วยราคาสด ไม่มีเงินจริงเสี่ยง', vi: 'Cấu hình AI một lần — nó đọc tin tức, dữ liệu kinh tế và biểu đồ để giao dịch crypto, cổ phiếu Mỹ và thị trường dự đoán tự động. Theo giá trực tiếp, không rủi ro tiền thật.' }),
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
    calloutD: tr(language, { en: 'This is where your AI executes its trades — sized 1× to 100×, with the liquidation math shown before any fill. All simulated: real mechanics, zero real risk.', ja: 'AIが取引を執行する場所。1〜100倍のサイズ設定と、約定前の清算計算を表示。すべて模擬で、仕組みは本物、リスクはゼロ。', th: 'ที่นี่คือที่ AI ดำเนินการเทรด — ขนาด 1× ถึง 100× แสดงคณิตการล้างพอร์ตก่อนเติมทุกครั้ง ทั้งหมดจำลอง กลไกจริง ไม่มีความเสี่ยงจริง', vi: 'Đây là nơi AI thực thi giao dịch — cỡ 1× đến 100×, phép toán thanh lý hiển thị trước mỗi lệnh. Tất cả mô phỏng: cơ chế thật, không rủi ro thật.' }),
    learnMore: tr(language, { en: 'Learn more', ja: '詳しく', th: 'เรียนรู้เพิ่ม', vi: 'Tìm hiểu thêm' }),

    convH1: tr(language, { en: 'Convert USDT', ja: 'USDTを', th: 'แปลง USDT', vi: 'Chuyển USDT' }),
    convH2: tr(language, { en: 'to BTC easily.', ja: 'BTCへ簡単に。', th: 'เป็น BTC ง่ายๆ', vi: 'sang BTC dễ dàng.' }),
    convD: tr(language, { en: 'Live rate — the same feed your simulated trades fill against.', ja: 'ライブレート。模擬取引が約定するのと同じフィード。', th: 'เรตสด — ฟีดเดียวกับที่เทรดจำลองของคุณใช้', vi: 'Tỷ giá trực tiếp — cùng nguồn giá lệnh mô phỏng của bạn.' }),

    voicesH: tr(language, { en: 'Hear it from the AI analysts', ja: 'AIアナリストの声', th: 'ฟังจากนักวิเคราะห์ AI', vi: 'Nghe từ các nhà phân tích AI' }),
    voices: [
      { title: tr(language, { en: 'Recommended', ja: 'おすすめ', th: 'แนะนำ', vi: 'Khuyên dùng' }), who: 'News analyst · AI', quote: tr(language, { en: 'Quiet tape. No adverse headlines in 48 hours. Constructive.', ja: '静かな相場。48時間、悪材料なし。', th: 'ตลาดเงียบ ไม่มีข่าวร้ายใน 48 ชม.', vi: 'Thị trường yên. Không tin xấu 48 giờ.' }) },
      { title: tr(language, { en: 'Not euphoric yet', ja: 'まだ過熱ではない', th: 'ยังไม่คลั่ง', vi: 'Chưa hưng phấn' }), who: 'Sentiment analyst · AI', quote: tr(language, { en: 'StockTwits runs 12–4 bullish. A tailwind, not a top.', ja: 'StockTwitsは12対4で強気。追い風だ。', th: 'StockTwits กระทิง 12–4 เป็นลมส่ง ไม่ใช่ยอดดอย', vi: 'StockTwits 12–4 tăng. Gió thuận, chưa phải đỉnh.' }) },
      { title: tr(language, { en: 'No heroics', ja: '無理はしない', th: 'ไม่เล่นใหญ่', vi: 'Không liều' }), who: 'Risk manager · AI', quote: tr(language, { en: 'Small long justified. Stop under 60,000 — that is the deal.', ja: '小さめのロングは妥当。損切りは60,000割れ。', th: 'Long เล็กสมเหตุผล ตัดขาดทุนใต้ 60,000', vi: 'Long nhỏ hợp lý. Cắt lỗ dưới 60.000.' }) },
      { title: tr(language, { en: 'Every number reconciled', ja: '数字はすべて一致', th: 'ตัวเลขตรงทุกตัว', vi: 'Mọi con số đều khớp' }), who: 'demo-bot · resident test agent', quote: tr(language, { en: 'Four trades in. Cash, fees, PnL — all correct. I am a bot; I checked.', ja: '4回取引して現金・手数料・損益すべて正確。ボットの私が確認。', th: 'เทรดไป 4 ครั้ง เงินสด ค่าธรรมเนียม กำไรขาดทุน — ถูกทุกตัว', vi: 'Bốn lệnh. Tiền, phí, PnL — đều đúng. Tôi là bot; tôi đã kiểm.' }) },
    ],

    boldH: tr(language, { en: '$100,000 of paper money. Let the AI trade it.', ja: '10万ドルの模擬資金を、AIに任せて売買。', th: 'เงินจำลอง $100,000 ให้ AI เทรดให้', vi: '$100.000 tiền mô phỏng. Để AI giao dịch.' }),
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
        <b style={{ ...mono, color: '#47764f', fontSize: 20 }}>BUY</b>
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
          <span style={{ color: MUT }}>{a}</span><span style={{ ...mono, color: b === '● active' ? '#47764f' : INK }}>{b}</span>
        </div>
      ))}
    </div>,
    <div key={2} style={{ padding: 18 }}>
      {[[62181.2, 0.33], [62181.0, 12.0]].map(([p, q], i) => (
        <div key={i} style={{ ...mono, display: 'flex', justifyContent: 'space-between', fontSize: 12.5, color: '#a13a26', padding: '3px 0' }}>
          <span>{p.toLocaleString()}</span><span>{q}</span>
        </div>
      ))}
      <div style={{ ...mono, fontWeight: 800, fontSize: 18, color: '#47764f', padding: '6px 0', borderTop: `1px solid ${LINE}`, borderBottom: `1px solid ${LINE}` }}>
        {btc ? btc.price.toLocaleString(undefined, { maximumFractionDigits: 1 }) : '62,180.0'}
      </div>
      {[[62179.9, 515.7], [62179.6, 0.63]].map(([p, q], i) => (
        <div key={i} style={{ ...mono, display: 'flex', justifyContent: 'space-between', fontSize: 12.5, color: '#47764f', padding: '3px 0' }}>
          <span>{p.toLocaleString()}</span><span>{q}</span>
        </div>
      ))}
    </div>,
    <div key={3} style={{ padding: 18, fontSize: 13 }}>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <span style={{ flex: 1, textAlign: 'center', background: '#47764f', color: '#fff', borderRadius: 8, padding: '7px 0', fontWeight: 700 }}>Long</span>
        <span style={{ flex: 1, textAlign: 'center', background: '#a13a26', color: '#fff', borderRadius: 8, padding: '7px 0', fontWeight: 700 }}>Short</span>
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
        @keyframes jtGlow{0%,100%{filter:drop-shadow(0 0 10px rgba(194,85,59,.45))}50%{filter:drop-shadow(0 0 26px rgba(194,85,59,.8))}}
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
        /* hero background: slow living glow (Jeton-style warm field) */
        @keyframes heroGlow{0%,100%{opacity:.8;transform:translate(0,0) scale(1)}50%{opacity:1;transform:translate(-2.5%,2%) scale(1.08)}}
        .hero-glow{animation:heroGlow 15s ease-in-out infinite;will-change:opacity,transform}

        /* Jeton "Unify" scroll-convergence floating cards */
        @keyframes uniFloat{0%,100%{transform:translateY(0) rotate(var(--rot,0deg))}50%{transform:translateY(-16px) rotate(var(--rot,0deg))}}
        .uni-card{position:absolute;transform:translate(var(--tx,0px),var(--ty,0px)) scale(var(--sc,1));opacity:var(--op,1);will-change:transform,opacity}
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
          .uni-card{position:static!important;transform:none!important;opacity:1!important;margin:8px auto}
          .uni-float{animation:none}
        }
        /* Reduced motion: keep the small AI/robot animations, drop the large
           idle-float and background drift/spin. */
        @media(prefers-reduced-motion:reduce){
          .hero-glow,.uni-ring,.uni-ring-r,.uni-phone,.uni-float{animation:none!important}
        }
      `}</style>
      <div className="jt">

        {/* ══ HERO — Claude light theme + 3D AI robot ══ */}
        <section style={{ position: 'relative', minHeight: 'min(78vh, 680px)', overflow: 'hidden', background: BG }}>

          {/* Paper Ledger field: warm paper + drifting constellation dots */}
          <div aria-hidden className="hero-glow" style={{ position: 'absolute', inset: 0, backgroundImage: 'radial-gradient(rgba(194,85,59,0.30) 1.4px, transparent 1.6px), radial-gradient(rgba(36,33,27,0.14) 1.1px, transparent 1.3px)', backgroundSize: '96px 96px, 148px 148px', backgroundPosition: '0 0, 48px 64px' }} />

          {/* whisper ledger grid */}
          <div aria-hidden style={{ position: 'absolute', inset: 0, opacity: 0.5, backgroundImage: `linear-gradient(${LINE} 1px, transparent 1px), linear-gradient(90deg, ${LINE} 1px, transparent 1px)`, backgroundSize: '76px 76px' }} />

          {/* rising candlestick chart, right side (green on cream) */}
          <svg viewBox="0 0 700 500" style={{ position: 'absolute', right: 0, top: '5%', width: 'min(56vw, 740px)', height: '82%', opacity: 0.95 }} aria-hidden>
            {[
              { x: 40, y: 340, h: 70, up: true }, { x: 105, y: 360, h: 55, up: false }, { x: 170, y: 300, h: 85, up: true },
              { x: 235, y: 260, h: 70, up: true }, { x: 300, y: 285, h: 50, up: false }, { x: 365, y: 210, h: 95, up: true },
              { x: 430, y: 170, h: 75, up: true }, { x: 495, y: 195, h: 48, up: false }, { x: 560, y: 110, h: 100, up: true },
              { x: 625, y: 60, h: 85, up: true },
            ].map((c, i) => (
              <g key={i} className="jt-candlebar" style={{ ['--d' as any]: `${3 + (i % 4) * 0.5}s`, ['--dl' as any]: `${-i * 0.4}s` }}>
                <line x1={c.x + 14} y1={c.y - 26} x2={c.x + 14} y2={c.y + c.h + 26} stroke={c.up ? 'rgba(71,118,79,0.75)' : 'rgba(161,58,38,0.45)'} strokeWidth="3" />
                <rect x={c.x} y={c.y} width="28" height={c.h} rx="5" fill={c.up ? 'rgba(71,118,79,0.30)' : 'rgba(161,58,38,0.18)'} stroke={c.up ? 'rgba(71,118,79,0.8)' : 'rgba(161,58,38,0.5)'} strokeWidth="1.5" />
              </g>
            ))}
            <path className="jt-line" d="M20,400 L110,380 L180,330 L250,300 L320,315 L390,240 L460,205 L530,225 L600,140 L670,80"
              fill="none" stroke={ORANGE} strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="2600" />
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
              <span style={{ width: 30, height: 30, borderRadius: '50%', background: ORANGE, color: BG, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 16 }}>s</span>
              <span style={{ fontWeight: 700, fontSize: 22, color: INK }}>Sooppiy</span>
              <span style={{ marginLeft: 'auto', display: 'flex', gap: 2, background: CARD, border: `1px solid ${LINE}`, borderRadius: 999, padding: '4px 8px' }}>
                <span aria-hidden style={{ color: FAINT, fontSize: 13, padding: '3px 2px 0 4px' }}>🌐</span>
                {Object.entries(LANGS).map(([code, label]) => (
                  <button key={code} onClick={() => setLanguage(code as any)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 12.5, padding: '4px 6px', color: language === code ? INK : FAINT, fontWeight: language === code ? 700 : 400 }}>{label}</button>
                ))}
              </span>
              <Link to="/login" style={{ ...pill, color: INK, padding: '11px 20px', background: 'transparent' }}>{T.login}</Link>
              <Link to="/register" style={{ ...pill, color: BG, padding: '11px 22px', background: ORANGE, borderRadius: 6 }}>{T.signup}</Link>
            </div>
          </header>

          {/* stacked thumbnail headline, left */}
          <div className="jt-hero" style={{ position: 'absolute', zIndex: 3, left: 'max(24px, calc(50vw - 560px))', top: '15vh', maxWidth: 640, fontFamily: 'var(--font-ui, Inter, sans-serif)' }}>
            <div style={{ fontSize: 'clamp(30px,3.6vw,44px)', fontWeight: 700, color: INK, letterSpacing: '-.01em', lineHeight: 1.05 }}>{T.thThe}</div>
            <div style={{ display: 'inline-block', background: ORANGE, color: BG, fontSize: 'clamp(40px,5.6vw,68px)', fontWeight: 700, letterSpacing: '-.02em', lineHeight: 1, padding: '6px 16px', borderRadius: 8, margin: '8px 0', boxShadow: '0 10px 26px rgba(36,33,27,0.14)' }}>{T.thEasiest}</div>
            <div style={{ fontSize: 'clamp(26px,3.2vw,40px)', fontWeight: 700, color: INK, letterSpacing: '-.01em', lineHeight: 1.1 }}>{T.thWay}</div>
            <div style={{ fontSize: 'clamp(44px,6vw,74px)', fontWeight: 700, lineHeight: 1.04, letterSpacing: '-.02em', margin: '6px 0 0', color: INK }}>
              <span>{T.thAi}</span>{' '}
              <span style={{ color: ORANGE }}>{T.thBot}</span>
            </div>

            {/* BUILD → AI → PROFIT strip */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 34, flexWrap: 'wrap' }}>
              {[
                { icon: '</>', label: T.stBuild, color: ORANGE },
                { icon: '🧠', label: T.stAi, color: UP },
                { icon: '📈', label: T.stProfit, color: UP, note: T.stNote },
              ].map((s, i) => (
                <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                  <span className="jt-step" style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'center', gap: 6, ['--dl' as any]: `${-i}s` }}>
                    <span style={{ width: 62, height: 50, borderRadius: 8, border: `1.5px solid ${s.color}`, background: CARD, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: s.icon === '</>' ? 17 : 22, fontWeight: 700, color: s.color, fontFamily: '"JetBrains Mono",ui-monospace,monospace', boxShadow: '0 4px 14px rgba(36,33,27,0.07)' }}>{s.icon}</span>
                    <span style={{ ...mono, fontSize: 12, fontWeight: 600, color: INK, letterSpacing: '.08em' }}>{s.label}{s.note && <span style={{ fontWeight: 400, color: FAINT, textTransform: 'lowercase' }}> · {s.note}</span>}</span>
                  </span>
                  {i < 2 && <span style={{ color: ORANGE, fontWeight: 700, fontSize: 20, marginBottom: 20 }}>›</span>}
                </span>
              ))}
            </div>

            {/* sub + CTAs */}
            <p style={{ ...serif, fontSize: 18, fontWeight: 400, color: MUT, margin: '30px 0 16px', lineHeight: 1.55, maxWidth: 460 }}>{T.heroS}</p>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <Link to="/register" style={{ ...pill, background: ORANGE, color: BG, padding: '13px 24px', fontSize: 15, borderRadius: 6 }}>◐ {T.ctaSim}</Link>
              <Link to="/login" style={{ ...pill, background: 'rgba(255,255,255,0.7)', color: INK, padding: '13px 24px', fontSize: 15, borderRadius: 6, border: '1.5px solid #c9c2b2' }}>◆ {T.ctaBoard}</Link>
            </div>
          </div>

          {/* scroll pill bottom-left */}
          <span style={{ ...mono, position: 'absolute', zIndex: 3, left: 22, bottom: 20, fontSize: 11.5, color: MUT, background: CARD, border: `1px solid ${LINE}`, padding: '7px 14px', borderRadius: 999 }}>⌄ {T.scroll}</span>
          {/* support pill bottom-right */}
          <a href="mailto:support@sooppiy.app" style={{ position: 'absolute', zIndex: 3, right: 22, bottom: 20, fontSize: 13, fontWeight: 600, color: BG, background: ORANGE, padding: '10px 18px', borderRadius: 6, textDecoration: 'none' }}>💬 {T.support}</a>
        </section>

        {/* ══ floating bottom dock (Jeton's signature nav) — persists on scroll ══ */}
        <nav style={{ position: 'fixed', zIndex: 60, left: '50%', transform: 'translateX(-50%)', bottom: 18, display: 'flex', alignItems: 'center', gap: 4, background: ORANGE, borderRadius: 999, padding: '7px 10px', boxShadow: '0 14px 40px rgba(36,33,27,0.25)' }}>
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
            <div className="uni-card" data-dx="200" data-dy="-140" style={{ top: 8, right: -6 }}>
              <div className="uni-float" style={{ ['--d' as any]: '6.5s', ['--rot' as any]: '3deg', background: '#fff', border: '1.5px solid #c9c2b2', borderRadius: 12, padding: 20, width: 258, boxShadow: '0 34px 70px -24px rgba(36,33,27,0.28)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontWeight: 700, fontSize: 15 }}>🟢 BTC/USDT <span style={{ marginLeft: 'auto', color: ORANGE, fontSize: 12 }}>▾</span></div>
                <div style={{ ...mono, fontSize: 40, fontWeight: 800, margin: '12px 0 2px', letterSpacing: '-.02em' }}>$250</div>
                <div style={{ fontSize: 13, color: MUT }}>{T.uniBalance}: $65,019.53</div>
                <div style={{ ...mono, marginTop: 16, textAlign: 'center', background: 'rgba(194,85,59,0.10)', color: ORANGE, borderRadius: 8, padding: '11px 0', fontWeight: 600, fontSize: 13.5 }}>AI · {T.uniOrder}</div>
              </div>
            </div>

            {/* AI decision card (green) — left */}
            <div className="uni-card" data-dx="-240" data-dy="-30" style={{ top: 176, left: -8 }}>
              <div className="uni-float" style={{ ['--d' as any]: '7.5s', ['--dl' as any]: '-1.5s', ['--rot' as any]: '-4deg', background: 'linear-gradient(160deg,#4f8258,#3c6443)', color: '#faf8f3', borderRadius: 12, padding: 22, width: 260, boxShadow: '0 34px 66px -22px rgba(60,100,67,0.45)' }}>
                <div style={{ fontSize: 13.5, fontWeight: 700, opacity: 0.92 }}>⇄ {T.uniDecision}</div>
                <div style={{ ...mono, fontSize: 32, fontWeight: 800, marginTop: 10, letterSpacing: '-.01em' }}>BUY · 72%</div>
                <div style={{ ...mono, fontSize: 16, fontWeight: 700, opacity: 0.95, marginTop: 2 }}>BTC/USDT</div>
                <div style={{ marginTop: 16, display: 'inline-block', background: 'rgba(255,255,255,0.28)', borderRadius: 999, padding: '5px 14px', fontSize: 13, fontWeight: 700 }}>✓ {T.uniExecuted}</div>
              </div>
            </div>

            {/* analyst card (pink) — bottom centre */}
            <div className="uni-card" data-dx="20" data-dy="200" style={{ bottom: 6, left: '41%' }}>
              <div className="uni-float" style={{ ['--d' as any]: '6.8s', ['--dl' as any]: '-3s', ['--rot' as any]: '2deg', background: '#f3efe6', border: `1px solid ${LINE}`, borderRadius: 12, padding: 20, width: 236, boxShadow: '0 34px 66px -24px rgba(36,33,27,0.24)' }}>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
                  <span style={{ width: 48, height: 48, borderRadius: '50%', background: 'linear-gradient(135deg,#c2553b,#a13a26)', color: '#faf8f3', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 16 }}>NA</span>
                  <span style={{ fontWeight: 700, color: ORANGE, fontSize: 15 }}>{T.uniAnalyst}</span>
                </div>
                <div style={{ ...mono, textAlign: 'center', fontSize: 12, color: MUT, margin: '12px 0' }}>🔒 {T.uniReasoning}</div>
                <div style={{ textAlign: 'center', background: '#fff', border: `1px solid ${LINE}`, borderRadius: 8, padding: '10px 0', fontWeight: 700, fontSize: 14.5, color: ORANGE }}>{T.uniRun}</div>
              </div>
            </div>

            {/* live BTC mini-chart tile — top left */}
            <div className="uni-card" data-dx="-205" data-dy="-175" style={{ top: 24, left: '9%' }}>
              <div className="uni-float" style={{ ['--d' as any]: '8s', ['--dl' as any]: '-2s', ['--rot' as any]: '-6deg', background: '#fff', border: '1px solid #e7e1d3', borderRadius: 12, padding: 16, width: 174, boxShadow: '0 30px 60px -24px rgba(36,33,27,0.22)' }}>
                <div style={{ fontSize: 12.5, fontWeight: 700, color: MUT, marginBottom: 8 }}>{T.uniLiveBtc}</div>
                <svg viewBox="0 0 140 48" style={{ width: '100%', height: 48 }} aria-hidden>
                  <polyline points="4,42 26,32 44,36 68,20 88,28 110,12 136,5" fill="none" stroke="#47764f" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <div style={{ ...mono, fontSize: 17, fontWeight: 800, marginTop: 8 }}>{btc ? `$${btc.price.toLocaleString()}` : '$62,180'}</div>
              </div>
            </div>

            {/* leaderboard tile — bottom right */}
            <div className="uni-card" data-dx="220" data-dy="155" style={{ bottom: 56, right: '3%' }}>
              <div className="uni-float" style={{ ['--d' as any]: '7s', ['--dl' as any]: '-4s', ['--rot' as any]: '5deg', background: '#fff', border: '1px solid #e7e1d3', borderRadius: 12, padding: 16, width: 224, boxShadow: '0 30px 60px -24px rgba(36,33,27,0.22)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, fontSize: 15 }}>🏆 demo-bot <span style={{ marginLeft: 'auto', color: '#47764f' }}>#1</span></div>
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
        <section style={{ position: 'relative', overflow: 'hidden', minHeight: '94vh', display: 'flex', alignItems: 'center', background: 'linear-gradient(118deg,#24211b 0%,#3a2e26 38%,#7d352f 72%,#a1543b 100%)' }}>
          {/* 3D-style coiled torus (bead rings) */}
          <svg viewBox="0 0 900 900" preserveAspectRatio="xMidYMid slice" aria-hidden
            style={{ position: 'absolute', right: '-10%', top: '50%', transform: 'translateY(-50%)', width: 'min(128vh, 1200px)', height: 'min(128vh, 1200px)' }}>
            <defs>
              <linearGradient id="gCoilA" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#e7a498" /><stop offset="48%" stopColor="#b5544a" /><stop offset="100%" stopColor="#7d352f" /></linearGradient>
              <linearGradient id="gCoilB" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#8ba377" /><stop offset="50%" stopColor="#47764f" /><stop offset="100%" stopColor="#2e4a33" /></linearGradient>
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
                <div style={{ position: 'relative', borderRadius: 42, overflow: 'hidden', background: 'linear-gradient(168deg,#c2553b 0%,#d97a4f 55%,#e8b28e 100%)', height: 588, padding: '20px 20px 0' }}>
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
                  <div style={{ position: 'absolute', left: 30, bottom: 40, width: 172, height: 108, borderRadius: 20, background: 'linear-gradient(140deg,#f6e3d3,#d97a4f)', transform: 'rotate(-12deg)', boxShadow: '0 22px 46px rgba(120,30,20,0.4)', padding: 14 }}>
                    <div style={{ ...mono, color: '#7a2e18', fontWeight: 800, fontSize: 17 }}>BUY 72%</div>
                    <div style={{ ...mono, color: 'rgba(122,46,24,0.8)', fontSize: 12, marginTop: 5 }}>BTC · executed</div>
                  </div>
                  <div style={{ position: 'absolute', right: 26, bottom: 84, width: 134, height: 84, borderRadius: 16, background: 'rgba(255,255,255,0.94)', transform: 'rotate(9deg)', boxShadow: '0 16px 38px rgba(120,30,20,0.3)', padding: 12 }}>
                    <div style={{ ...mono, color: '#47764f', fontWeight: 800, fontSize: 15 }}>+ paper</div>
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
            <div style={{ height: 10, background: `linear-gradient(90deg, ${ORANGE}, #d97a4f)` }} />
            {mockPanels[3]}
          </div>
        </section>

        {/* ══ 5 · converter calculator ("Convert fiat cash easily.") ══ */}
        <section style={{ ...wrap, padding: '9vh 24px', textAlign: 'center' }}>
          <h2 style={{ ...h2, fontSize: 'clamp(34px,5vw,58px)' }}>{T.convH1}<br />{T.convH2}</h2>
          <p style={{ color: MUT, marginBottom: 28 }}>{T.convD}</p>
          <div style={{ ...cardS, display: 'inline-flex', alignItems: 'center', gap: 16, padding: '20px 28px', flexWrap: 'wrap', justifyContent: 'center', borderRadius: 24 }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ width: 30, height: 30, borderRadius: '50%', background: '#47764f', color: '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 13 }}>$</span>
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
            <span style={{ ...mono, fontSize: 12.5, color: btc && btc.pct >= 0 ? '#47764f' : '#a13a26', width: '100%', textAlign: 'center' }}>
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
        <section style={{ background: 'linear-gradient(135deg,#c2553b,#d97a4f)', padding: '13vh 24px', textAlign: 'center' }}>
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
              [T.footMarkets, [['Leaderboard', '/login'], ['Financial events', '/login'], ['Backtest', '/login']]],
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
