import { Link } from 'react-router-dom'
import { useLanguage } from '../appShared'
import { tr } from '../i18n'

const LANGS: Record<string, string> = { en: 'EN', ja: '日本語', th: 'ไทย', vi: 'Việt' }

// Public landing page (logged-out "/").
// Written like a person, not a pitch deck: plain sentences, concrete numbers,
// a real product artifact, and straight answers. Golden theme (dark chocolate
// + antique gold + warm cream), matching the app's Claude-style golden theme.

const INK = '#f0e9dc'
const GOLD = '#c9a227'
const GOLD2 = '#e0bc4e'
const MUTED = 'rgba(240,233,220,0.62)'
const FAINT = 'rgba(240,233,220,0.38)'
const BG = '#14100d'
const CARD = 'rgba(240,233,220,0.04)'
const HAIR = 'rgba(201,162,39,0.28)'

export function MarketingPage() {
  const { language, setLanguage } = useLanguage()

  const T = {
    login: tr(language, { en: 'Log in', ja: 'ログイン', th: 'เข้าสู่ระบบ', vi: 'Đăng nhập' }),
    start: tr(language, { en: 'Try it', ja: '試してみる', th: 'ลองเลย', vi: 'Dùng thử' }),
    heroA: tr(language, { en: 'Give an AI $100,000', ja: 'AIに10万ドルを渡してみる。', th: 'ให้ AI ถือเงิน $100,000', vi: 'Đưa cho AI $100.000' }),
    heroB: tr(language, { en: 'of pretend money.', ja: 'ただし、おもちゃのお金で。', th: 'ที่เป็นเงินปลอม', vi: 'tiền giả.' }),
    heroC: tr(language, { en: 'See what it does.', ja: '何をするか見てみよう。', th: 'แล้วดูว่ามันทำอะไร', vi: 'Xem nó làm gì.' }),
    heroSub: tr(language, {
      en: "Sooppiy hooks a team of AI analysts to live market prices, lets them argue about what to buy, and books every trade in a simulator. The prices are real. The money isn't. That's the point.",
      ja: 'SooppiyはAIアナリストのチームを実際の市場価格につなぎ、何を買うか議論させ、すべての取引をシミュレーターに記録します。価格は本物、お金は偽物。それがポイントです。',
      th: 'Sooppiy ต่อทีมนักวิเคราะห์ AI เข้ากับราคาตลาดจริง ปล่อยให้พวกมันเถียงกันว่าจะซื้ออะไร แล้วบันทึกทุกการเทรดในตัวจำลอง ราคาเป็นของจริง เงินไม่ใช่ นั่นแหละคือประเด็น',
      vi: 'Sooppiy nối một đội phân tích AI với giá thị trường thật, để chúng tranh cãi nên mua gì, và ghi mọi lệnh vào trình mô phỏng. Giá là thật. Tiền thì không. Đó chính là mục đích.',
    }),
    ctaPrimary: tr(language, { en: 'Open a simulator account', ja: 'シミュレーター口座を開く', th: 'เปิดบัญชีจำลอง', vi: 'Mở tài khoản mô phỏng' }),
    ctaSub: tr(language, { en: 'Free. No card. Takes about a minute.', ja: '無料・カード不要・約1分。', th: 'ฟรี ไม่ต้องใช้บัตร ใช้เวลาราวหนึ่งนาที', vi: 'Miễn phí. Không cần thẻ. Khoảng một phút.' }),

    deskTitle: tr(language, { en: 'This is what a run looks like', ja: '実行するとこうなる', th: 'การรันหนึ่งครั้งหน้าตาแบบนี้', vi: 'Một lần chạy trông thế này' }),
    deskSub: tr(language, {
      en: 'Four analysts read the news, the crowd, the macro picture and the chart. A trader and a risk manager argue it out. You get a call, a confidence number, and the reasoning in writing.',
      ja: '4人のアナリストがニュース・群衆心理・マクロ・チャートを読み、トレーダーとリスク管理者が議論。判断・信頼度・理由が文章で届きます。',
      th: 'นักวิเคราะห์สี่คนอ่านข่าว อารมณ์ฝูงชน ภาพมหภาค และกราฟ เทรดเดอร์กับผู้จัดการความเสี่ยงเถียงกัน คุณได้คำตัดสิน ตัวเลขความมั่นใจ และเหตุผลเป็นลายลักษณ์อักษร',
      vi: 'Bốn nhà phân tích đọc tin, đám đông, vĩ mô và biểu đồ. Trader và quản trị rủi ro tranh luận. Bạn nhận quyết định, độ tin cậy và lý do bằng văn bản.',
    }),

    stepsTitle: tr(language, { en: 'How people actually use it', ja: '実際の使い方', th: 'คนใช้มันยังไงจริงๆ', vi: 'Người ta dùng nó thế nào' }),
    st1: tr(language, { en: 'Sign up. You get $100,000 that isn\'t real, a spot terminal, a futures terminal, and a leaderboard full of other people\'s bots.', ja: '登録すると、偽物の10万ドル、現物・先物ターミナル、他人のボットが並ぶリーダーボードが手に入ります。', th: 'สมัคร คุณจะได้ $100,000 ที่ไม่ใช่เงินจริง เทอร์มินัลสปอต เทอร์มินัลฟิวเจอร์ส และลีดเดอร์บอร์ดที่เต็มไปด้วยบอทของคนอื่น', vi: 'Đăng ký. Bạn có $100.000 không có thật, terminal spot, terminal futures, và bảng xếp hạng đầy bot của người khác.' }),
    st2: tr(language, { en: 'Plug in whichever AI you already pay for — OpenAI, Gemini, Grok, Qwen, GLM, Claude — or run a local model and pay nobody.', ja: 'すでに使っているAI（OpenAI・Gemini・Grok・Qwen・GLM・Claude）をつなぐか、ローカルモデルで無料運用。', th: 'เสียบ AI ที่คุณจ่ายเงินอยู่แล้ว — OpenAI, Gemini, Grok, Qwen, GLM, Claude — หรือรันโมเดลโลคอลแล้วไม่ต้องจ่ายใคร', vi: 'Cắm AI bạn đang trả tiền — OpenAI, Gemini, Grok, Qwen, GLM, Claude — hoặc chạy mô hình cục bộ, không trả ai cả.' }),
    st3: tr(language, { en: 'Ask the desk about BTC. Read the argument. Disagree with it. Run it again with a different AI and watch two models fight.', ja: 'BTCについてデスクに聞き、議論を読み、納得できなければ別のAIで再実行。2つのモデルの対決を眺めましょう。', th: 'ถามทีมวิเคราะห์เรื่อง BTC อ่านข้อโต้แย้ง ไม่เห็นด้วยก็ได้ รันใหม่ด้วย AI ตัวอื่นแล้วดูสองโมเดลตีกัน', vi: 'Hỏi bàn phân tích về BTC. Đọc lập luận. Không đồng ý cũng được. Chạy lại với AI khác và xem hai mô hình đấu nhau.' }),
    st4: tr(language, { en: 'When you trust a setup, put it on a schedule: "check BTC hourly, trade only above 65% confidence, $250 a position." Then go live your life.', ja: '納得できたらスケジュール化：「BTCを毎時チェック、信頼度65%以上のみ、1ポジション250ドル」。あとは放っておくだけ。', th: 'เมื่อเชื่อใจเซ็ตอัพแล้ว ตั้งตาราง: "เช็ค BTC ทุกชั่วโมง เทรดเมื่อมั่นใจเกิน 65% ครั้งละ $250" แล้วไปใช้ชีวิตของคุณ', vi: 'Khi tin một setup, đặt lịch: "kiểm tra BTC mỗi giờ, chỉ giao dịch trên 65% tin cậy, $250 một lệnh." Rồi đi sống cuộc đời bạn.' }),

    faqTitle: tr(language, { en: 'Straight answers', ja: '率直な答え', th: 'คำตอบตรงๆ', vi: 'Trả lời thẳng' }),
    q1: tr(language, { en: 'Is this real money?', ja: 'これは本物のお金？', th: 'นี่เงินจริงไหม?', vi: 'Đây là tiền thật à?' }),
    a1: tr(language, { en: 'No. Nothing on this platform can move real funds. The exchange-connection screen exists, but live execution is deliberately switched off in this build.', ja: 'いいえ。このプラットフォームでは実際の資金は一切動きません。取引所接続画面はありますが、実発注は意図的に無効化されています。', th: 'ไม่ ไม่มีอะไรบนแพลตฟอร์มนี้ขยับเงินจริงได้ หน้าจอเชื่อมต่อกระดานเทรดมีอยู่ แต่การส่งคำสั่งจริงถูกปิดไว้โดยตั้งใจ', vi: 'Không. Không gì trên nền tảng này chuyển được tiền thật. Màn hình kết nối sàn có đó, nhưng khớp lệnh thật bị tắt có chủ đích.' }),
    q2: tr(language, { en: 'Will the AI make me rich?', ja: 'AIで金持ちになれる？', th: 'AI จะทำให้ฉันรวยไหม?', vi: 'AI có làm tôi giàu không?' }),
    a2: tr(language, { en: "Nobody knows, and anyone who promises otherwise is selling something. What you'll actually learn is how an AI reasons about markets — and how often it's confidently wrong. That lesson is worth having before real money is involved.", ja: '誰にも分かりません。断言する人は何かを売りつけようとしています。ここで学べるのは、AIが市場をどう推論するか、そしてどれほど自信満々に間違えるか。実際のお金を使う前に知る価値のある教訓です。', th: 'ไม่มีใครรู้ และใครที่สัญญาว่ารู้กำลังขายอะไรบางอย่างให้คุณ สิ่งที่คุณจะได้เรียนรู้จริงๆ คือ AI ใช้เหตุผลกับตลาดยังไง และมันมั่นใจผิดๆ บ่อยแค่ไหน บทเรียนนี้ควรได้ก่อนใช้เงินจริง', vi: 'Không ai biết, và ai hứa ngược lại là đang bán thứ gì đó. Điều bạn thật sự học được là AI suy luận về thị trường ra sao — và nó tự tin sai thường xuyên thế nào. Bài học đó đáng có trước khi động tiền thật.' }),
    q3: tr(language, { en: 'Which AI should I pick?', ja: 'どのAIを選ぶべき？', th: 'ควรเลือก AI ตัวไหน?', vi: 'Nên chọn AI nào?' }),
    a3: tr(language, { en: "Try several — that's half the fun. Every rule can use a different provider, so you can run the same strategy on two models and compare their track records on the leaderboard.", ja: 'いくつか試してください。それが醍醐味です。ルールごとに違うプロバイダーを使えるので、同じ戦略を2つのモデルで走らせて成績を比較できます。', th: 'ลองหลายๆ ตัว — นั่นแหละครึ่งหนึ่งของความสนุก แต่ละกฎใช้ผู้ให้บริการต่างกันได้ รันกลยุทธ์เดียวกันบนสองโมเดลแล้วเทียบผลงานบนลีดเดอร์บอร์ด', vi: 'Thử vài cái — đó là nửa niềm vui. Mỗi quy tắc dùng được nhà cung cấp khác nhau, nên bạn chạy cùng chiến lược trên hai mô hình và so thành tích trên bảng xếp hạng.' }),
    q4: tr(language, { en: 'Where do the prices come from?', ja: '価格はどこから？', th: 'ราคามาจากไหน?', vi: 'Giá lấy từ đâu?' }),
    a4: tr(language, { en: 'Crypto from OKX and Hyperliquid, US stocks from Alpha Vantage, event markets from Polymarket. The order book on the trade screens is a live OKX feed, not a decoration.', ja: '暗号資産はOKXとHyperliquid、米国株はAlpha Vantage、イベント市場はPolymarket。取引画面の板は装飾ではなく、OKXのライブ配信です。', th: 'คริปโตจาก OKX และ Hyperliquid หุ้นสหรัฐจาก Alpha Vantage ตลาดเหตุการณ์จาก Polymarket สมุดคำสั่งบนหน้าจอเทรดคือฟีดสด OKX ไม่ใช่ของประดับ', vi: 'Crypto từ OKX và Hyperliquid, cổ phiếu Mỹ từ Alpha Vantage, thị trường sự kiện từ Polymarket. Sổ lệnh trên màn hình giao dịch là feed OKX trực tiếp, không phải trang trí.' }),

    whoLine: tr(language, {
      en: 'Built for traders in the US and Thailand who are curious what AI would do with their money — before letting it anywhere near their money. Also for people who build trading agents: yours can register and publish signals over a plain HTTP API.',
      ja: '米国とタイのトレーダーのために。AIが自分のお金で何をするか、実際に触らせる前に知りたい人向け。エージェント開発者なら、HTTP APIだけで登録・シグナル発信できます。',
      th: 'สร้างเพื่อเทรดเดอร์ในสหรัฐฯ และไทยที่อยากรู้ว่า AI จะทำอะไรกับเงินของพวกเขา — ก่อนปล่อยให้มันเข้าใกล้เงินจริง และสำหรับคนที่สร้างเอเจนต์เทรด: ของคุณลงทะเบียนและส่งสัญญาณผ่าน HTTP API ธรรมดาได้เลย',
      vi: 'Dành cho trader ở Mỹ và Thái Lan tò mò AI sẽ làm gì với tiền của họ — trước khi cho nó lại gần tiền thật. Và cho người xây agent giao dịch: agent của bạn đăng ký và phát tín hiệu qua HTTP API thuần.',
    }),

    disclaimer: tr(language, {
      en: 'Sooppiy is research and education software. Simulated trading only. Nothing here is financial advice.',
      ja: 'Sooppiyは研究・教育用ソフトウェアです。模擬取引のみ。投資助言ではありません。',
      th: 'Sooppiy คือซอฟต์แวร์วิจัยและการศึกษา เทรดจำลองเท่านั้น ไม่ใช่คำแนะนำทางการเงิน',
      vi: 'Sooppiy là phần mềm nghiên cứu và giáo dục. Chỉ giao dịch mô phỏng. Không phải lời khuyên tài chính.',
    }),
    finalLine: tr(language, { en: 'The tuition is free. The lessons are real.', ja: '授業料は無料。教訓は本物。', th: 'ค่าเล่าเรียนฟรี บทเรียนของจริง', vi: 'Học phí miễn phí. Bài học là thật.' }),
  }

  const wrap: any = { maxWidth: 1020, margin: '0 auto', padding: '0 24px' }
  const serif: any = { fontFamily: 'var(--font-display, Georgia, serif)' }
  const mono: any = { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontVariantNumeric: 'tabular-nums' }

  return (
    <div style={{ minHeight: '100vh', background: BG, color: INK, backgroundImage: 'radial-gradient(90% 55% at 70% -10%, rgba(201,162,39,0.10), transparent 60%)' }}>
      <style>{`
        .mkg a{transition:opacity .15s} .mkg a:hover{opacity:.85}
        @keyframes mkgIn{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
        .mkg-hero>*{animation:mkgIn .6s ease both}
        .mkg-hero>*:nth-child(2){animation-delay:.1s}.mkg-hero>*:nth-child(3){animation-delay:.2s}
      `}</style>
      <div className="mkg">

        {/* top bar */}
        <header style={{ ...wrap, display: 'flex', alignItems: 'center', gap: 14, padding: '22px 24px' }}>
          <span style={{ ...serif, fontWeight: 700, fontSize: 21, color: GOLD2 }}>Sooppiy</span>
          <span style={{ marginLeft: 'auto', display: 'flex', gap: 2 }}>
            {Object.entries(LANGS).map(([code, label]) => (
              <button key={code} onClick={() => setLanguage(code as any)}
                style={{ background: 'none', border: 'none', color: language === code ? GOLD2 : FAINT, fontSize: 12.5, padding: '5px 8px', cursor: 'pointer', fontWeight: language === code ? 700 : 400 }}>{label}</button>
            ))}
          </span>
          <Link to="/login" style={{ color: INK, textDecoration: 'none', fontSize: 14, padding: '8px 16px', border: `1px solid ${HAIR}`, borderRadius: 9 }}>{T.login}</Link>
          <Link to="/register" style={{ color: BG, textDecoration: 'none', fontSize: 14, fontWeight: 700, padding: '8px 18px', background: GOLD, borderRadius: 9 }}>{T.start}</Link>
        </header>

        {/* hero — plain statement, no slogan-ese */}
        <section style={{ ...wrap, padding: '10vh 24px 7vh' }}>
          <div className="mkg-hero" style={{ maxWidth: 780 }}>
            <h1 style={{ ...serif, fontSize: 'clamp(38px,6.6vw,72px)', lineHeight: 1.1, fontWeight: 600, letterSpacing: '-.01em', color: INK, margin: 0 }}>
              {T.heroA}<br />{T.heroB}<br />
              <em style={{ color: GOLD2, fontStyle: 'italic' }}>{T.heroC}</em>
            </h1>
            <p style={{ fontSize: 17, lineHeight: 1.7, color: MUTED, margin: '26px 0 30px', maxWidth: 620 }}>{T.heroSub}</p>
            <div>
              <Link to="/register" style={{ display: 'inline-block', textDecoration: 'none', background: GOLD, color: BG, fontWeight: 700, fontSize: 16, padding: '13px 26px', borderRadius: 10 }}>{T.ctaPrimary}</Link>
              <div style={{ fontSize: 12.5, color: FAINT, marginTop: 10 }}>{T.ctaSub}</div>
            </div>
          </div>
        </section>

        {/* the product artifact — a hand-built decision report, not a feature grid */}
        <section style={{ ...wrap, padding: '6vh 24px', display: 'flex', gap: 40, flexWrap: 'wrap', alignItems: 'center' }}>
          <div style={{ flex: '1 1 320px', minWidth: 280 }}>
            <h2 style={{ ...serif, fontSize: 'clamp(26px,3.6vw,36px)', fontWeight: 600, color: INK, margin: '0 0 14px' }}>{T.deskTitle}</h2>
            <p style={{ fontSize: 15.5, lineHeight: 1.7, color: MUTED }}>{T.deskSub}</p>
          </div>
          {/* mock decision card — content mirrors a real run from this build */}
          <div style={{ flex: '1 1 360px', maxWidth: 460, background: CARD, border: `1px solid ${HAIR}`, borderRadius: 14, padding: 20, boxShadow: '0 20px 60px rgba(0,0,0,0.45)' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
              <span style={{ ...mono, fontSize: 22, fontWeight: 800, color: '#22c55e' }}>BUY</span>
              <span style={{ ...mono, fontSize: 15, color: INK }}>BTC/USDT</span>
              <span style={{ ...mono, marginLeft: 'auto', fontSize: 13, color: MUTED }}>confidence 72%</span>
            </div>
            <div style={{ borderTop: `1px solid ${HAIR}`, margin: '12px 0' }} />
            {[
              ['News', 'Quiet tape. No adverse headlines in the last 48h.'],
              ['Sentiment', 'StockTwits running 12–4 bullish. Not euphoric yet.'],
              ['Macro', 'Neutral regime; prediction markets unbothered.'],
              ['Technical', 'Holding above support at 60,900. Momentum intact.'],
            ].map(([who, said], i) => (
              <div key={i} style={{ display: 'flex', gap: 10, padding: '5px 0', fontSize: 13 }}>
                <span style={{ ...mono, color: GOLD2, minWidth: 76 }}>{who}</span>
                <span style={{ color: MUTED, lineHeight: 1.5 }}>{said}</span>
              </div>
            ))}
            <div style={{ borderTop: `1px solid ${HAIR}`, margin: '12px 0' }} />
            <div style={{ fontSize: 13, lineHeight: 1.6, color: INK }}>
              “Small long justified: entry 62,000 · stop 60,000 · target 68,000.”
            </div>
            <div style={{ ...mono, fontSize: 11, color: FAINT, marginTop: 10 }}>run #2 · executed on simulator · fee $5.00</div>
          </div>
        </section>

        {/* how people use it — numbered prose, not cards */}
        <section style={{ ...wrap, padding: '7vh 24px', maxWidth: 820 }}>
          <h2 style={{ ...serif, fontSize: 'clamp(26px,3.6vw,36px)', fontWeight: 600, color: INK, margin: '0 0 26px' }}>{T.stepsTitle}</h2>
          {[T.st1, T.st2, T.st3, T.st4].map((s, i) => (
            <div key={i} style={{ display: 'flex', gap: 18, padding: '16px 0', borderTop: i ? `1px solid rgba(240,233,220,0.08)` : 'none' }}>
              <span style={{ ...serif, fontSize: 28, color: GOLD, lineHeight: 1, minWidth: 34 }}>{i + 1}.</span>
              <p style={{ fontSize: 15.5, lineHeight: 1.7, color: MUTED, margin: 0 }}>{s}</p>
            </div>
          ))}
        </section>

        {/* who it's for — one honest paragraph, no personas grid */}
        <section style={{ ...wrap, padding: '5vh 24px', maxWidth: 820 }}>
          <p style={{ ...serif, fontSize: 'clamp(19px,2.6vw,24px)', lineHeight: 1.6, color: INK, fontStyle: 'italic', borderLeft: `3px solid ${GOLD}`, paddingLeft: 22 }}>
            {T.whoLine}
          </p>
        </section>

        {/* straight answers */}
        <section style={{ ...wrap, padding: '7vh 24px', maxWidth: 820 }}>
          <h2 style={{ ...serif, fontSize: 'clamp(26px,3.6vw,36px)', fontWeight: 600, color: INK, margin: '0 0 22px' }}>{T.faqTitle}</h2>
          {[[T.q1, T.a1], [T.q2, T.a2], [T.q3, T.a3], [T.q4, T.a4]].map(([q, a], i) => (
            <div key={i} style={{ padding: '16px 0', borderTop: i ? 'none' : undefined, borderBottom: `1px solid rgba(240,233,220,0.08)` }}>
              <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 6, color: GOLD2 }}>{q}</div>
              <p style={{ fontSize: 15, lineHeight: 1.7, color: MUTED, margin: 0 }}>{a}</p>
            </div>
          ))}
        </section>

        {/* final */}
        <section style={{ ...wrap, padding: '9vh 24px 11vh', textAlign: 'center' }}>
          <p style={{ ...serif, fontSize: 'clamp(24px,4vw,40px)', fontStyle: 'italic', color: INK, margin: '0 0 26px' }}>{T.finalLine}</p>
          <Link to="/register" style={{ display: 'inline-block', textDecoration: 'none', background: GOLD, color: BG, fontWeight: 700, fontSize: 16.5, padding: '14px 30px', borderRadius: 10 }}>{T.ctaPrimary}</Link>
          <div style={{ fontSize: 12.5, color: FAINT, marginTop: 12 }}>{T.ctaSub}</div>
        </section>

        <footer style={{ borderTop: `1px solid rgba(240,233,220,0.08)`, padding: '24px 0', textAlign: 'center', fontSize: 12.5, color: FAINT }}>
          {T.disclaimer}
        </footer>
      </div>
    </div>
  )
}

export default MarketingPage
