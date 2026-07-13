import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useLanguage } from '../appShared'
import { tr } from '../i18n'

const LANGS: Record<string, string> = { en: 'EN', ja: 'JA', th: 'TH', vi: 'VI' }

// Public landing page — structured after jeton.com:
// sticky nav · clean hero · tabbed product carousel · value cards · numbered
// steps · mid-page CTA · feature callout · live converter demo · voices ·
// trust badges · multi-column footer. White canvas, orange pill CTAs.

const ORANGE = '#e2551f'
const INK = '#191512'
const MUT = 'rgba(25,21,18,0.6)'
const FAINT = 'rgba(25,21,18,0.42)'
const BG = '#faf7f2'
const CARD = '#ffffff'
const LINE = 'rgba(25,21,18,0.10)'

const mono: any = { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontVariantNumeric: 'tabular-nums' }

export function MarketingPage() {
  const { language, setLanguage } = useLanguage()
  const [tab, setTab] = useState(0)
  const [btc, setBtc] = useState<{ price: number; pct: number } | null>(null)
  const [usd, setUsd] = useState('1000')

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

  const T = {
    navProduct: tr(language, { en: 'Product', ja: '製品', th: 'ผลิตภัณฑ์', vi: 'Sản phẩm' }),
    navHow: tr(language, { en: 'How it works', ja: '使い方', th: 'วิธีใช้งาน', vi: 'Cách hoạt động' }),
    navFaq: tr(language, { en: 'FAQ', ja: 'FAQ', th: 'คำถาม', vi: 'FAQ' }),
    login: tr(language, { en: 'Log In', ja: 'ログイン', th: 'เข้าสู่ระบบ', vi: 'Đăng nhập' }),
    signup: tr(language, { en: 'Sign Up', ja: '登録', th: 'สมัคร', vi: 'Đăng ký' }),
    heroH: tr(language, { en: 'One desk for all your trades', ja: 'すべてのトレードをひとつのデスクに', th: 'โต๊ะเดียวสำหรับทุกการเทรดของคุณ', vi: 'Một bàn làm việc cho mọi giao dịch' }),
    heroS: tr(language, { en: 'A single simulated account for AI analysis, automation, spot and futures', ja: 'AI分析・自動売買・現物・先物をひとつの模擬口座で', th: 'บัญชีจำลองเดียวสำหรับการวิเคราะห์ AI ระบบอัตโนมัติ สปอต และฟิวเจอร์ส', vi: 'Một tài khoản mô phỏng cho phân tích AI, tự động hóa, spot và futures' }),
    openAccount: tr(language, { en: 'Open simulator account', ja: 'シミュレーター口座を開く', th: 'เปิดบัญชีจำลอง', vi: 'Mở tài khoản mô phỏng' }),
    seeBoard: tr(language, { en: 'See the leaderboard', ja: 'リーダーボードを見る', th: 'ดูลีดเดอร์บอร์ด', vi: 'Xem bảng xếp hạng' }),
    scroll: tr(language, { en: 'Scroll', ja: 'スクロール', th: 'เลื่อน', vi: 'Cuộn' }),

    unifyH: tr(language, { en: 'Unify your trading', ja: 'トレードをひとつに', th: 'รวมการเทรดของคุณ', vi: 'Hợp nhất giao dịch' }),
    tabs: [
      { k: tr(language, { en: 'Analyze', ja: '分析', th: 'วิเคราะห์', vi: 'Phân tích' }) },
      { k: tr(language, { en: 'Automate', ja: '自動化', th: 'อัตโนมัติ', vi: 'Tự động' }) },
      { k: tr(language, { en: 'Spot', ja: '現物', th: 'สปอต', vi: 'Spot' }) },
      { k: tr(language, { en: 'Futures', ja: '先物', th: 'ฟิวเจอร์ส', vi: 'Futures' }) },
      { k: tr(language, { en: 'Assets', ja: '資産', th: 'ทรัพย์สิน', vi: 'Tài sản' }) },
    ],
    tabDesc: [
      tr(language, { en: 'Four AI analysts read news, sentiment, macro and charts — a trader and risk manager debate the call.', ja: '4人のAIアナリストがニュース・センチメント・マクロ・チャートを読み、トレーダーとリスク管理者が議論します。', th: 'นักวิเคราะห์ AI สี่คนอ่านข่าว อารมณ์ตลาด มหภาค และกราฟ — เทรดเดอร์และผู้จัดการความเสี่ยงถกเถียงกัน', vi: 'Bốn nhà phân tích AI đọc tin, tâm lý, vĩ mô và biểu đồ — trader và quản trị rủi ro tranh luận.' }),
      tr(language, { en: 'Set symbol, model, schedule and confidence. It trades only when your rules are met.', ja: '銘柄・モデル・スケジュール・信頼度を設定。条件を満たした時だけ取引します。', th: 'ตั้งเหรียญ โมเดล ตาราง และความมั่นใจ มันจะเทรดเมื่อเข้าเงื่อนไขเท่านั้น', vi: 'Đặt mã, mô hình, lịch và độ tin cậy. Chỉ giao dịch khi đủ điều kiện.' }),
      tr(language, { en: 'A real OKX order book, live prices, instant simulated fills.', ja: '本物のOKX板・ライブ価格・即時の模擬約定。', th: 'สมุดคำสั่ง OKX จริง ราคาสด เติมคำสั่งจำลองทันที', vi: 'Sổ lệnh OKX thật, giá trực tiếp, khớp mô phỏng tức thì.' }),
      tr(language, { en: 'Long or short with 1–100× sizing and a liquidation preview.', ja: '1〜100倍のロング/ショートと清算プレビュー。', th: 'Long หรือ Short ขนาด 1–100× พร้อมพรีวิวราคาล้างพอร์ต', vi: 'Long hoặc short 1–100× kèm xem trước thanh lý.' }),
      tr(language, { en: 'Cash, holdings and PnL in one view — every number reconciles.', ja: '現金・保有・損益をひと目で。すべての数字が一致します。', th: 'เงินสด ถือครอง และกำไรขาดทุนในหน้าเดียว — ทุกตัวเลขตรงกัน', vi: 'Tiền mặt, nắm giữ và PnL trong một màn hình — mọi con số khớp nhau.' }),
    ],

    cardsH: tr(language, { en: 'Why Sooppiy', ja: 'Sooppiyの理由', th: 'ทำไมต้อง Sooppiy', vi: 'Vì sao Sooppiy' }),
    cards: [
      { t: tr(language, { en: 'AI that argues before it acts', ja: '行動の前に議論するAI', th: 'AI ที่ถกเถียงก่อนลงมือ', vi: 'AI tranh luận trước khi hành động' }), d: tr(language, { en: 'Every decision comes with a confidence score and the reasoning in writing.', ja: 'すべての判断に信頼度と文書化された理由が付きます。', th: 'ทุกการตัดสินใจมาพร้อมคะแนนความมั่นใจและเหตุผลเป็นลายลักษณ์อักษร', vi: 'Mỗi quyết định kèm điểm tin cậy và lý do bằng văn bản.' }) },
      { t: tr(language, { en: 'Bring any AI you like', ja: '好きなAIを持ち込む', th: 'ใช้ AI ตัวไหนก็ได้', vi: 'Dùng AI nào tùy bạn' }), d: tr(language, { en: 'OpenAI, Gemini, Grok, Qwen, GLM, Claude — or a local model, free.', ja: 'OpenAI・Gemini・Grok・Qwen・GLM・Claude、またはローカルモデル。', th: 'OpenAI, Gemini, Grok, Qwen, GLM, Claude — หรือโมเดลโลคอล ฟรี', vi: 'OpenAI, Gemini, Grok, Qwen, GLM, Claude — hoặc mô hình cục bộ.' }) },
      { t: tr(language, { en: 'Real markets, everywhere', ja: 'リアルな市場データ', th: 'ตลาดจริงทุกที่', vi: 'Thị trường thật' }), d: tr(language, { en: 'Crypto, US stocks and event markets — live prices from OKX, Hyperliquid, Alpha Vantage and Polymarket.', ja: '暗号資産・米国株・イベント市場。OKX・Hyperliquid・Alpha Vantage・Polymarketのライブ価格。', th: 'คริปโต หุ้นสหรัฐ และตลาดเหตุการณ์ — ราคาสดจาก OKX, Hyperliquid, Alpha Vantage และ Polymarket', vi: 'Crypto, cổ phiếu Mỹ và thị trường sự kiện — giá trực tiếp.' }) },
      { t: tr(language, { en: 'Fast and safe — it is simulated', ja: '速くて安全（模擬だから）', th: 'เร็วและปลอดภัย — เพราะเป็นแบบจำลอง', vi: 'Nhanh và an toàn — vì là mô phỏng' }), d: tr(language, { en: 'No real funds can move here. Learn the expensive lessons for free.', ja: '実際の資金は動きません。高くつく教訓を無料で。', th: 'ไม่มีเงินจริงเคลื่อนไหวที่นี่ เรียนบทเรียนราคาแพงได้ฟรี', vi: 'Không tiền thật. Học bài học đắt giá miễn phí.' }) },
    ],

    stepsH: tr(language, { en: 'Automate a trade in five steps', ja: '5ステップで自動売買', th: 'ตั้งเทรดอัตโนมัติใน 5 ขั้น', vi: 'Tự động hóa trong 5 bước' }),
    steps: [
      tr(language, { en: 'Account', ja: '口座', th: 'บัญชี', vi: 'Tài khoản' }),
      tr(language, { en: 'AI key', ja: 'AIキー', th: 'คีย์ AI', vi: 'Khóa AI' }),
      tr(language, { en: 'Analyze', ja: '分析', th: 'วิเคราะห์', vi: 'Phân tích' }),
      tr(language, { en: 'Rule', ja: 'ルール', th: 'กฎ', vi: 'Quy tắc' }),
      tr(language, { en: 'Done', ja: '完了', th: 'เสร็จ', vi: 'Xong' }),
    ],

    midH: tr(language, { en: 'All your trading, in one desk', ja: 'すべてのトレードをひとつのデスクで', th: 'ทุกการเทรดของคุณ ในโต๊ะเดียว', vi: 'Mọi giao dịch, một bàn làm việc' }),
    midS: tr(language, { en: 'Start with $100,000 of simulated money today', ja: '今日、10万ドルの模擬資金でスタート', th: 'เริ่มวันนี้ด้วยเงินจำลอง $100,000', vi: 'Bắt đầu hôm nay với $100.000 mô phỏng' }),

    calloutH: tr(language, { en: 'The futures terminal', ja: '先物ターミナル', th: 'เทอร์มินัลฟิวเจอร์ส', vi: 'Terminal futures' }),
    calloutD: tr(language, { en: 'Leverage? Sure. Live order book? Check. Liquidation preview? Also check.', ja: 'レバレッジ？もちろん。ライブ板？あり。清算プレビュー？それもあり。', th: 'เลเวอเรจ? ได้ สมุดคำสั่งสด? มี พรีวิวล้างพอร์ต? มีเช่นกัน', vi: 'Đòn bẩy? Có. Sổ lệnh trực tiếp? Có. Xem trước thanh lý? Cũng có.' }),
    learnMore: tr(language, { en: 'Learn more', ja: '詳しく見る', th: 'เรียนรู้เพิ่ม', vi: 'Tìm hiểu thêm' }),

    convH: tr(language, { en: 'Watch the market move, live', ja: '市場の動きをライブで', th: 'ดูตลาดขยับแบบสด', vi: 'Xem thị trường chuyển động trực tiếp' }),
    convD: tr(language, { en: 'The same feed your simulated trades fill against.', ja: '模擬取引が約定するのと同じ価格フィードです。', th: 'ฟีดเดียวกับที่การเทรดจำลองของคุณใช้เติมคำสั่ง', vi: 'Cùng nguồn giá mà lệnh mô phỏng của bạn khớp.' }),

    voicesH: tr(language, { en: 'Voices from the desk', ja: 'デスクからの声', th: 'เสียงจากโต๊ะเทรด', vi: 'Tiếng nói từ bàn làm việc' }),
    voices: [
      { who: 'News analyst', tag: 'AI', quote: tr(language, { en: '“Quiet tape. No adverse headlines in 48 hours.”', ja: '「静かな相場。48時間、悪材料なし。」', th: '“ตลาดเงียบ ไม่มีข่าวร้ายใน 48 ชั่วโมง”', vi: '“Thị trường yên. Không tin xấu trong 48 giờ.”' }) },
      { who: 'Sentiment analyst', tag: 'AI', quote: tr(language, { en: '“StockTwits runs 12–4 bullish. Not euphoric yet.”', ja: '「StockTwitsは12対4で強気。まだ過熱ではない。」', th: '“StockTwits กระทิง 12–4 ยังไม่ถึงขั้นคลั่ง”', vi: '“StockTwits 12–4 nghiêng tăng. Chưa hưng phấn.”' }) },
      { who: 'Risk manager', tag: 'AI', quote: tr(language, { en: '“Small long justified. Stop under 60,000 — no heroics.”', ja: '「小さめのロングは妥当。損切りは60,000割れ。無理はしない。」', th: '“Long เล็กๆ สมเหตุผล ตัดขาดทุนใต้ 60,000 — อย่าเล่นใหญ่”', vi: '“Long nhỏ hợp lý. Cắt lỗ dưới 60.000 — đừng liều.”' }) },
      { who: 'demo-bot', tag: tr(language, { en: 'resident test agent', ja: '常駐テストエージェント', th: 'เอเจนต์ทดสอบประจำ', vi: 'agent thử nghiệm' }), quote: tr(language, { en: '“I have made 4 trades and every number reconciled. I am a bot; I checked.”', ja: '「4回取引して、数字はすべて一致。ボットの私が確認済み。」', th: '“ฉันเทรด 4 ครั้ง ตัวเลขตรงทุกตัว ฉันเป็นบอท ฉันเช็คแล้ว”', vi: '“Tôi đã giao dịch 4 lần và mọi con số đều khớp. Tôi là bot; tôi đã kiểm tra.”' }) },
    ],

    trustH: tr(language, { en: 'Built on real market plumbing', ja: '本物の市場インフラの上に', th: 'สร้างบนโครงสร้างตลาดจริง', vi: 'Xây trên hạ tầng thị trường thật' }),

    footGet: tr(language, { en: 'Get Started', ja: 'はじめる', th: 'เริ่มต้น', vi: 'Bắt đầu' }),
    footDiscover: tr(language, { en: 'Discover', ja: '見る', th: 'สำรวจ', vi: 'Khám phá' }),
    footMarkets: tr(language, { en: 'Markets', ja: 'マーケット', th: 'ตลาด', vi: 'Thị trường' }),
    footHelp: tr(language, { en: 'Help', ja: 'ヘルプ', th: 'ช่วยเหลือ', vi: 'Trợ giúp' }),
    legal: tr(language, {
      en: 'Sooppiy is research and education software. All trading on this platform is simulated: no real funds are held, moved, or at risk. Market data is provided for information only. Nothing on this site is investment advice.',
      ja: 'Sooppiyは研究・教育用ソフトウェアです。当プラットフォームのすべての取引は模擬であり、実際の資金は保有・移動・リスクにさらされません。市場データは情報提供のみを目的とします。投資助言ではありません。',
      th: 'Sooppiy คือซอฟต์แวร์วิจัยและการศึกษา การเทรดทั้งหมดบนแพลตฟอร์มนี้เป็นแบบจำลอง: ไม่มีเงินจริงถูกถือ เคลื่อนย้าย หรือเสี่ยง ข้อมูลตลาดมีไว้เพื่อข้อมูลเท่านั้น ไม่ใช่คำแนะนำการลงทุน',
      vi: 'Sooppiy là phần mềm nghiên cứu và giáo dục. Mọi giao dịch trên nền tảng này đều mô phỏng: không có tiền thật. Dữ liệu thị trường chỉ mang tính thông tin. Không phải lời khuyên đầu tư.',
    }),
  }

  // hand-built mock panels for the tab carousel
  const mockPanels = [
    /* Analyze */
    <div key={0} style={{ padding: 18 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <b style={{ ...mono, color: '#16a34a', fontSize: 20 }}>BUY</b>
        <span style={mono}>BTC/USDT</span>
        <span style={{ ...mono, marginLeft: 'auto', fontSize: 12, color: MUT }}>confidence 72%</span>
      </div>
      {[['News', '—'], ['Sentiment', '12–4 bullish'], ['Macro', 'neutral'], ['Technical', 'above support']].map(([a, b], i) => (
        <div key={i} style={{ display: 'flex', fontSize: 12.5, padding: '5px 0', borderTop: `1px solid ${LINE}`, marginTop: i === 0 ? 10 : 0 }}>
          <span style={{ color: ORANGE, minWidth: 84, fontWeight: 600 }}>{a}</span><span style={{ color: MUT }}>{b}</span>
        </div>
      ))}
    </div>,
    /* Automate */
    <div key={1} style={{ padding: 18, fontSize: 13 }}>
      <div style={{ fontWeight: 700, marginBottom: 10 }}>BTC · crypto</div>
      {[['Run every', '60 min'], ['Min confidence', '65%'], ['Size', '$250'], ['Account', 'simulator'], ['Status', '● active']].map(([a, b], i) => (
        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderTop: `1px solid ${LINE}` }}>
          <span style={{ color: MUT }}>{a}</span><span style={{ ...mono, color: b === '● active' ? '#16a34a' : INK }}>{b}</span>
        </div>
      ))}
    </div>,
    /* Spot */
    <div key={2} style={{ padding: 18 }}>
      {[[62181.2, 0.33], [62181.0, 12.0], [62180.8, 0.58]].map(([p, q], i) => (
        <div key={i} style={{ ...mono, display: 'flex', justifyContent: 'space-between', fontSize: 12.5, color: '#dc2626', padding: '3px 0' }}>
          <span>{p.toLocaleString()}</span><span>{q}</span>
        </div>
      ))}
      <div style={{ ...mono, fontWeight: 800, fontSize: 18, color: '#16a34a', padding: '6px 0', borderTop: `1px solid ${LINE}`, borderBottom: `1px solid ${LINE}` }}>
        {btc ? btc.price.toLocaleString(undefined, { maximumFractionDigits: 1 }) : '62,180.0'}
      </div>
      {[[62179.9, 515.7], [62179.6, 0.63], [62179.4, 0.01]].map(([p, q], i) => (
        <div key={i} style={{ ...mono, display: 'flex', justifyContent: 'space-between', fontSize: 12.5, color: '#16a34a', padding: '3px 0' }}>
          <span>{p.toLocaleString()}</span><span>{q}</span>
        </div>
      ))}
    </div>,
    /* Futures */
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
    /* Assets */
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
  const h2: any = { fontSize: 'clamp(28px,4vw,42px)', fontWeight: 800, letterSpacing: '-.02em', color: INK, margin: '0 0 14px', lineHeight: 1.15 }
  const cardS: any = { background: CARD, border: `1px solid ${LINE}`, borderRadius: 16, boxShadow: '0 2px 12px rgba(25,21,18,0.05)' }
  const usdN = parseFloat(usd) || 0

  return (
    <div style={{ minHeight: '100vh', background: BG, color: INK, fontFamily: 'var(--font-ui, Inter, sans-serif)' }}>
      <style>{`
        .jt a{transition:opacity .15s,transform .15s} .jt a:hover{opacity:.9}
        .jt-tab{transition:all .15s;cursor:pointer;border:none;background:none}
        @keyframes jtIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
        .jt-hero>*{animation:jtIn .55s ease both}
        .jt-hero>*:nth-child(2){animation-delay:.1s}.jt-hero>*:nth-child(3){animation-delay:.2s}
        .jt-grid{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}

        /* ── hero background animation: automated trading ── */
        @keyframes jtFloat{0%,100%{transform:translateY(0) rotate(var(--r,0deg))}50%{transform:translateY(-26px) rotate(var(--r,0deg))}}
        @keyframes jtDrift{0%,100%{transform:translate(0,0) scale(1)}50%{transform:translate(30px,-40px) scale(1.06)}}
        @keyframes jtRise{0%{transform:translateY(40px);opacity:0}12%{opacity:.95}82%{opacity:.95}100%{transform:translateY(-72vh);opacity:0}}
        @keyframes jtDash{from{stroke-dashoffset:2600}to{stroke-dashoffset:0}}
        @keyframes jtTick{0%,100%{opacity:.5}50%{opacity:1}}
        .jt-candle{position:absolute;animation:jtFloat var(--d,7s) ease-in-out infinite;animation-delay:var(--dl,0s);will-change:transform}
        .jt-disc{position:absolute;border-radius:50%;filter:blur(2px);animation:jtDrift var(--d,16s) ease-in-out infinite;animation-delay:var(--dl,0s);will-change:transform}
        .jt-chip{position:absolute;animation:jtRise var(--d,11s) linear infinite;animation-delay:var(--dl,0s);will-change:transform,opacity}
        .jt-line{stroke-dasharray:2600;animation:jtDash 12s linear infinite}
        @media (prefers-reduced-motion: reduce){.jt-candle,.jt-disc,.jt-chip,.jt-line,.jt-hero>*{animation:none!important}}
      `}</style>
      <div className="jt">

        {/* ── full-bleed animated hero (Jeton) — automated-trading background ── */}
        <section style={{ position: 'relative', minHeight: '94vh', overflow: 'hidden', background: 'linear-gradient(135deg,#f2607a 0%,#f77a5f 45%,#f9a06b 100%)', display: 'flex', flexDirection: 'column' }}>

          {/* layer 1 — soft drifting discs (Jeton's coins) */}
          {[
            { w: 420, l: '52%', t: '-8%', d: '18s', dl: '0s', o: 0.35 },
            { w: 300, l: '68%', t: '30%', d: '22s', dl: '-6s', o: 0.28 },
            { w: 220, l: '38%', t: '18%', d: '15s', dl: '-3s', o: 0.30 },
            { w: 160, l: '12%', t: '8%', d: '19s', dl: '-9s', o: 0.22 },
          ].map((c, i) => (
            <span key={i} className="jt-disc" style={{ width: c.w, height: c.w, left: c.l, top: c.t, opacity: c.o, background: 'radial-gradient(circle at 32% 28%, #ffe3c2, #f7906d 60%, rgba(247,144,109,0))', ['--d' as any]: c.d, ['--dl' as any]: c.dl }} />
          ))}

          {/* layer 2 — self-drawing price line */}
          <svg viewBox="0 0 1400 600" preserveAspectRatio="none" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', opacity: 0.5 }} aria-hidden>
            <path className="jt-line" d="M-20,420 L90,395 L170,430 L260,340 L340,365 L450,285 L540,320 L640,240 L730,275 L840,195 L930,235 L1040,150 L1130,185 L1240,110 L1330,140 L1440,70"
              fill="none" stroke="rgba(255,255,255,0.85)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
          </svg>

          {/* layer 3 — floating candlesticks */}
          {[
            { l: '20%', t: '22%', h: 84, up: true, d: '7s', dl: '0s', r: '-6deg' },
            { l: '31%', t: '48%', h: 62, up: false, d: '8.5s', dl: '-2s', r: '5deg' },
            { l: '47%', t: '30%', h: 100, up: true, d: '6.5s', dl: '-4s', r: '-3deg' },
            { l: '60%', t: '56%', h: 70, up: true, d: '9s', dl: '-1s', r: '7deg' },
            { l: '74%', t: '24%', h: 90, up: false, d: '7.5s', dl: '-5s', r: '-8deg' },
            { l: '86%', t: '46%', h: 64, up: true, d: '8s', dl: '-3s', r: '4deg' },
          ].map((c, i) => (
            <span key={i} className="jt-candle" style={{ left: c.l, top: c.t, ['--d' as any]: c.d, ['--dl' as any]: c.dl, ['--r' as any]: c.r }}>
              <span style={{ display: 'block', width: 3, height: c.h * 1.5, background: 'rgba(255,255,255,0.55)', borderRadius: 2, margin: '0 auto' }} />
              <span style={{ display: 'block', width: 18, height: c.h, borderRadius: 5, marginTop: -c.h * 1.25, background: c.up ? 'rgba(255,255,255,0.92)' : 'rgba(120,20,30,0.35)', border: '1.5px solid rgba(255,255,255,0.8)', boxShadow: '0 8px 24px rgba(120,20,30,0.18)' }} />
            </span>
          ))}

          {/* layer 4 — rising AI order tickets (the "automation") */}
          {[
            { txt: 'AI · BUY BTC · 72%', l: '16%', d: '11s', dl: '0s', c: '#0a7f3f' },
            { txt: 'rule met · +$250', l: '40%', d: '13s', dl: '-4s', c: '#0a7f3f' },
            { txt: 'AI · HOLD ETH · 51%', l: '58%', d: '12s', dl: '-7s', c: '#8a5a00' },
            { txt: 'AI · SELL SOL · 68%', l: '78%', d: '14s', dl: '-2s', c: '#a02020' },
          ].map((c, i) => (
            <span key={i} className="jt-chip" style={{ left: c.l, bottom: '-6%', ['--d' as any]: c.d, ['--dl' as any]: c.dl, ...mono, fontSize: 12, fontWeight: 700, color: c.c, background: 'rgba(255,255,255,0.92)', padding: '7px 13px', borderRadius: 999, boxShadow: '0 10px 30px rgba(120,20,30,0.22)' }}>{c.txt}</span>
          ))}

          {/* transparent nav over the gradient (Jeton) */}
          <header style={{ position: 'relative', zIndex: 3 }}>
            <div style={{ ...wrap, display: 'flex', alignItems: 'center', gap: 20, height: 76 }}>
              <span style={{ fontWeight: 800, fontSize: 22, color: '#fff' }}>Sooppiy</span>
              <nav style={{ display: 'flex', gap: 18, fontSize: 14, color: 'rgba(255,255,255,0.85)' }}>
                <a href="#product" style={{ color: 'inherit', textDecoration: 'none' }}>{T.navProduct}</a>
                <a href="#how" style={{ color: 'inherit', textDecoration: 'none' }}>{T.navHow}</a>
                <a href="#faq" style={{ color: 'inherit', textDecoration: 'none' }}>{T.navFaq}</a>
              </nav>
              <span style={{ marginLeft: 'auto', display: 'flex', gap: 2 }}>
                {Object.entries(LANGS).map(([code, label]) => (
                  <button key={code} onClick={() => setLanguage(code as any)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 12.5, padding: '4px 7px', color: language === code ? '#fff' : 'rgba(255,255,255,0.6)', fontWeight: language === code ? 700 : 400 }}>{label}</button>
                ))}
              </span>
              <Link to="/login" style={{ ...pill, color: '#fff', padding: '10px 20px', border: '1.5px solid rgba(255,255,255,0.75)' }}>{T.login}</Link>
              <Link to="/register" style={{ ...pill, color: ORANGE, padding: '11px 22px', background: '#fff' }}>{T.signup}</Link>
            </div>
          </header>

          {/* bottom row — headline left, sub + CTAs right (Jeton) */}
          <div className="jt-hero" style={{ ...wrap, position: 'relative', zIndex: 3, marginTop: 'auto', paddingBottom: '7vh', display: 'flex', alignItems: 'flex-end', gap: 30, flexWrap: 'wrap', width: '100%' }}>
            <h1 style={{ flex: '1 1 460px', fontSize: 'clamp(48px,7.8vw,96px)', fontWeight: 800, letterSpacing: '-.03em', lineHeight: 1.0, margin: 0, color: '#fff', fontFamily: 'var(--font-ui, Inter, sans-serif)' }}>
              {T.heroH}
            </h1>
            <div style={{ flex: '0 1 320px' }}>
              <p style={{ fontSize: 19, fontWeight: 600, color: '#fff', margin: '0 0 20px', lineHeight: 1.45 }}>{T.heroS}</p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, alignItems: 'flex-start' }}>
                <Link to="/register" style={{ ...pill, background: '#fff', color: ORANGE, padding: '14px 26px', fontSize: 15.5 }}>{T.openAccount}</Link>
                <Link to="/login" style={{ ...pill, border: '1.5px solid rgba(255,255,255,0.8)', color: '#fff', padding: '13px 24px', fontSize: 15.5 }}>{T.seeBoard}</Link>
              </div>
            </div>
          </div>
          <div style={{ position: 'relative', zIndex: 3, textAlign: 'center', paddingBottom: 18, fontSize: 12, color: 'rgba(255,255,255,0.75)', letterSpacing: '.14em' }}>↓ {T.scroll}</div>
        </section>

        {/* ── tabbed product carousel (Jeton "unify finances") ── */}
        <section id="product" style={{ ...wrap, padding: '8vh 24px' }}>
          <h2 style={{ ...h2, textAlign: 'center' }}>{T.unifyH}</h2>
          <div style={{ display: 'flex', gap: 6, justifyContent: 'center', flexWrap: 'wrap', margin: '26px 0 30px' }}>
            {T.tabs.map((t, i) => (
              <button key={i} className="jt-tab" onClick={() => setTab(i)}
                style={{ padding: '9px 20px', borderRadius: 999, fontSize: 14.5, fontWeight: 600, background: tab === i ? INK : 'transparent', color: tab === i ? '#fff' : MUT, border: tab === i ? 'none' : `1px solid ${LINE}` }}>
                <span style={{ ...mono, fontSize: 11, marginRight: 7, color: tab === i ? ORANGE : FAINT }}>{String(i + 1).padStart(2, '0')}</span>{t.k}
              </button>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 34, alignItems: 'center', flexWrap: 'wrap', maxWidth: 880, margin: '0 auto' }}>
            <div style={{ ...cardS, flex: '0 1 340px', margin: '0 auto', minWidth: 280, overflow: 'hidden' }}>
              <div style={{ height: 10, background: `linear-gradient(90deg, ${ORANGE}, #f59e0b)` }} />
              {mockPanels[tab]}
            </div>
            <p style={{ flex: '1 1 300px', fontSize: 16.5, lineHeight: 1.7, color: MUT }}>{T.tabDesc[tab]}</p>
          </div>
        </section>

        {/* ── value cards (Jeton 4-up) ── */}
        <section style={{ ...wrap, padding: '8vh 24px' }}>
          <h2 style={{ ...h2, textAlign: 'center', marginBottom: 30 }}>{T.cardsH}</h2>
          <div className="jt-grid">
            {T.cards.map((c, i) => (
              <div key={i} style={{ ...cardS, padding: '24px 22px' }}>
                <div style={{ width: 38, height: 38, borderRadius: 10, background: 'rgba(226,85,31,0.1)', color: ORANGE, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, marginBottom: 14 }}>{['◆', '◇', '◈', '◐'][i]}</div>
                <div style={{ fontWeight: 700, fontSize: 16.5, marginBottom: 8 }}>{c.t}</div>
                <div style={{ fontSize: 14, lineHeight: 1.6, color: MUT }}>{c.d}</div>
              </div>
            ))}
          </div>
        </section>

        {/* ── 5-step process (Jeton) ── */}
        <section id="how" style={{ ...wrap, padding: '8vh 24px', textAlign: 'center' }}>
          <h2 style={h2}>{T.stepsH}</h2>
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginTop: 34 }}>
            {T.steps.map((s, i) => (
              <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
                  <span style={{ width: 44, height: 44, borderRadius: '50%', background: i === T.steps.length - 1 ? ORANGE : CARD, color: i === T.steps.length - 1 ? '#fff' : INK, border: `1.5px solid ${i === T.steps.length - 1 ? ORANGE : LINE}`, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800 }}>{i + 1}</span>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{s}</span>
                </span>
                {i < T.steps.length - 1 && <span style={{ color: FAINT, marginBottom: 22 }}>→</span>}
              </span>
            ))}
          </div>
        </section>

        {/* ── mid-page CTA (Jeton) ── */}
        <section style={{ background: INK, padding: '10vh 24px', textAlign: 'center' }}>
          <h2 style={{ ...h2, color: '#faf7f2' }}>{T.midH}</h2>
          <p style={{ color: 'rgba(250,247,242,0.65)', fontSize: 17, margin: '0 0 30px' }}>{T.midS}</p>
          <Link to="/register" style={{ ...pill, background: ORANGE, color: '#fff', padding: '15px 32px', fontSize: 16 }}>{T.openAccount}</Link>
        </section>

        {/* ── feature callout (Jeton card section) ── */}
        <section style={{ ...wrap, padding: '9vh 24px', display: 'flex', gap: 36, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ flex: '1 1 300px' }}>
            <h2 style={h2}>{T.calloutH}</h2>
            <p style={{ fontSize: 17, lineHeight: 1.7, color: MUT, marginBottom: 20 }}>{T.calloutD}</p>
            <Link to="/register" style={{ color: ORANGE, fontWeight: 700, textDecoration: 'none', fontSize: 15.5 }}>{T.learnMore} →</Link>
          </div>
          <div style={{ ...cardS, flex: '0 1 340px', margin: '0 auto', overflow: 'hidden' }}>
            <div style={{ height: 10, background: `linear-gradient(90deg, ${ORANGE}, #f59e0b)` }} />
            {mockPanels[3]}
          </div>
        </section>

        {/* ── live converter demo (Jeton exchange) ── */}
        <section style={{ ...wrap, padding: '7vh 24px', textAlign: 'center' }}>
          <h2 style={h2}>{T.convH}</h2>
          <p style={{ color: MUT, marginBottom: 28 }}>{T.convD}</p>
          <div style={{ ...cardS, display: 'inline-flex', alignItems: 'center', gap: 16, padding: '18px 26px', flexWrap: 'wrap', justifyContent: 'center' }}>
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

        {/* ── voices (Jeton testimonials) — honestly labeled ── */}
        <section id="faq" style={{ ...wrap, padding: '8vh 24px' }}>
          <h2 style={{ ...h2, textAlign: 'center', marginBottom: 30 }}>{T.voicesH}</h2>
          <div className="jt-grid">
            {T.voices.map((v, i) => (
              <div key={i} style={{ ...cardS, padding: '22px 20px' }}>
                <div style={{ color: ORANGE, fontSize: 13, letterSpacing: 2 }}>★★★★★</div>
                <p style={{ fontSize: 14.5, lineHeight: 1.65, margin: '12px 0 14px' }}>{v.quote}</p>
                <div style={{ fontSize: 13, fontWeight: 700 }}>{v.who} <span style={{ fontWeight: 400, color: FAINT }}>· {v.tag}</span></div>
              </div>
            ))}
          </div>
        </section>

        {/* ── trust badges (Jeton certifications) ── */}
        <section style={{ ...wrap, padding: '5vh 24px 8vh', textAlign: 'center' }}>
          <div style={{ fontSize: 12.5, color: FAINT, letterSpacing: '.14em', marginBottom: 18 }}>{T.trustH.toUpperCase()}</div>
          <div style={{ display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap' }}>
            {['OKX', 'Hyperliquid', 'Polymarket', 'Alpha Vantage', 'OpenAI', 'Gemini', 'Claude', 'Local LLM'].map((b) => (
              <span key={b} style={{ ...cardS, padding: '10px 20px', fontWeight: 700, fontSize: 14, color: MUT, borderRadius: 999 }}>{b}</span>
            ))}
          </div>
        </section>

        {/* ── footer (Jeton 5-column) ── */}
        <footer style={{ background: INK, color: 'rgba(250,247,242,0.7)', padding: '8vh 24px 4vh' }}>
          <div style={{ ...wrap, display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))', gap: 28 }}>
            <div>
              <div style={{ fontWeight: 800, fontSize: 19, color: ORANGE, marginBottom: 10 }}>Sooppiy</div>
              <div style={{ fontSize: 13, lineHeight: 1.6 }}>AI · analyze · automate<br />EN · 日本語 · ไทย · Tiếng Việt</div>
            </div>
            {[
              [T.footGet, [[T.signup, '/register'], [T.login, '/login']]],
              [T.footDiscover, [['AI Analyst', '/login'], ['Automation', '/login'], ['Spot', '/login'], ['Futures', '/login']]],
              [T.footMarkets, [['Leaderboard', '/login'], ['Financial events', '/login'], ['Copy trading', '/login']]],
              [T.footHelp, [['For developers', '/login'], ['FAQ', '#faq']]],
            ].map(([title, links]: any, i) => (
              <div key={i}>
                <div style={{ fontWeight: 700, color: '#faf7f2', marginBottom: 12, fontSize: 14 }}>{title}</div>
                {links.map(([label, href]: any) => (
                  href.startsWith('#')
                    ? <a key={label} href={href} style={{ display: 'block', color: 'inherit', textDecoration: 'none', fontSize: 13.5, padding: '4px 0' }}>{label}</a>
                    : <Link key={label} to={href} style={{ display: 'block', color: 'inherit', textDecoration: 'none', fontSize: 13.5, padding: '4px 0' }}>{label}</Link>
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
