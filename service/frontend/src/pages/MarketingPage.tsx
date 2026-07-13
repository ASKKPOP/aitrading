import { Link } from 'react-router-dom'
import { useLanguage } from '../appShared'
import { tr } from '../i18n'

const LANGS: Record<string, string> = { en: 'EN', ja: '日本語', th: 'ไทย', vi: 'Việt' }

// Public landing page (logged-out "/") — antigravity.google-inspired:
// near-black canvas, huge display type, gradient accent, statement sections.
export function MarketingPage() {
  const { language, setLanguage } = useLanguage()

  const T = {
    login: tr(language, { en: 'Log in', ja: 'ログイン', th: 'เข้าสู่ระบบ', vi: 'Đăng nhập' }),
    start: tr(language, { en: 'Get started', ja: 'はじめる', th: 'เริ่มต้น', vi: 'Bắt đầu' }),
    heroA: tr(language, { en: 'AI analyzes.', ja: 'AIが分析する。', th: 'AI วิเคราะห์', vi: 'AI phân tích.' }),
    heroB: tr(language, { en: 'You set the rules.', ja: 'ルールはあなたが決める。', th: 'คุณตั้งกฎ', vi: 'Bạn đặt luật.' }),
    heroC: tr(language, { en: 'It trades — on paper.', ja: '取引は模擬で行われる。', th: 'มันเทรด — บนกระดาษ', vi: 'Nó giao dịch — mô phỏng.' }),
    heroSub: tr(language, {
      en: 'Sooppiy is an AI trading platform: a multi-agent analyst desk reads the news, sentiment, macro and charts, debates a decision, and paper-trades it on your schedule — with real market prices and zero real money at risk.',
      ja: 'Sooppiyはマルチエージェントのアナリストデスクがニュース・センチメント・マクロ・チャートを読み、議論して判断し、実際の市場価格でスケジュール通りに模擬取引するAIトレーディングプラットフォームです。実際のお金は一切リスクにさらされません。',
      th: 'Sooppiy คือแพลตฟอร์มเทรดด้วย AI: ทีมนักวิเคราะห์ AI อ่านข่าว ความรู้สึกตลาด เศรษฐกิจมหภาค และกราฟ ถกเถียงกันจนได้ข้อสรุป แล้วเทรดจำลองตามตารางของคุณ — ด้วยราคาตลาดจริง โดยไม่มีเงินจริงเสี่ยงแม้แต่บาทเดียว',
      vi: 'Sooppiy là nền tảng giao dịch AI: bàn phân tích đa tác nhân đọc tin tức, tâm lý, vĩ mô và biểu đồ, tranh luận ra quyết định, và giao dịch mô phỏng theo lịch của bạn — giá thị trường thật, không rủi ro tiền thật.',
    }),
    ctaPrimary: tr(language, { en: 'Create a free account', ja: '無料アカウント作成', th: 'สร้างบัญชีฟรี', vi: 'Tạo tài khoản miễn phí' }),
    ctaSecondary: tr(language, { en: 'I already have an account', ja: 'アカウントをお持ちの方', th: 'มีบัญชีอยู่แล้ว', vi: 'Đã có tài khoản' }),

    whatEyebrow: tr(language, { en: 'WHAT IT IS', ja: '概要', th: 'มันคืออะไร', vi: 'LÀ GÌ' }),
    whatTitle: tr(language, { en: 'Three engines, one loop.', ja: '3つのエンジン、1つのループ。', th: 'สามเครื่องยนต์ หนึ่งวงจร', vi: 'Ba động cơ, một vòng lặp.' }),
    p1t: tr(language, { en: 'AI analyst desk', ja: 'AIアナリストデスク', th: 'ทีมนักวิเคราะห์ AI', vi: 'Bàn phân tích AI' }),
    p1d: tr(language, { en: 'News, sentiment, macro and technical analysts brief a trader + risk team that debates every call into a decision with a written report.', ja: 'ニュース・センチメント・マクロ・テクニカルの各アナリストが、トレーダーとリスクチームに報告し、議論の末に判断とレポートを出します。', th: 'นักวิเคราะห์ข่าว ความรู้สึก มหภาค และเทคนิค สรุปให้ทีมเทรดเดอร์+ความเสี่ยงถกเถียงจนได้คำตัดสินพร้อมรายงาน', vi: 'Các nhà phân tích tin tức, tâm lý, vĩ mô và kỹ thuật báo cáo cho đội trader + rủi ro tranh luận ra quyết định kèm báo cáo.' }),
    p2t: tr(language, { en: 'Automation', ja: '自動売買', th: 'ระบบอัตโนมัติ', vi: 'Tự động hóa' }),
    p2d: tr(language, { en: 'You set the symbol, AI model, schedule, confidence threshold and size. The worker runs the desk and trades only when your rules are met.', ja: '銘柄・AIモデル・スケジュール・信頼度・サイズを設定すれば、条件を満たした時だけ自動で取引します。', th: 'คุณตั้งเหรียญ โมเดล AI ตาราง เกณฑ์ความมั่นใจ และขนาด ระบบจะเทรดเมื่อเข้าเงื่อนไขเท่านั้น', vi: 'Bạn đặt mã, mô hình AI, lịch, ngưỡng tin cậy và cỡ lệnh. Worker chỉ giao dịch khi đủ điều kiện.' }),
    p3t: tr(language, { en: 'Simulator', ja: 'シミュレーター', th: 'ตัวจำลอง', vi: 'Trình mô phỏng' }),
    p3d: tr(language, { en: 'Spot and futures terminals with a real order book and live prices — every fill is paper, every number is real.', ja: '実際の板情報と価格で動く現物・先物ターミナル。約定は模擬、数字は本物。', th: 'เทอร์มินัลสปอตและฟิวเจอร์สพร้อมสมุดคำสั่งจริงและราคาสด — เติมคำสั่งแบบจำลอง ตัวเลขจริงทุกตัว', vi: 'Terminal spot và futures với sổ lệnh thật và giá trực tiếp — khớp lệnh mô phỏng, con số thật.' }),

    howEyebrow: tr(language, { en: 'HOW TO USE', ja: '使い方', th: 'วิธีใช้', vi: 'CÁCH DÙNG' }),
    howTitle: tr(language, { en: 'From zero to your first AI trade in minutes.', ja: '数分で最初のAIトレードへ。', th: 'จากศูนย์สู่เทรด AI แรกในไม่กี่นาที', vi: 'Từ số 0 đến lệnh AI đầu tiên trong vài phút.' }),
    s1t: tr(language, { en: 'Create an account', ja: 'アカウント作成', th: 'สร้างบัญชี', vi: 'Tạo tài khoản' }),
    s1d: tr(language, { en: 'You start with a $100,000 simulated wallet. No card, no KYC.', ja: '10万ドルの模擬ウォレットでスタート。カードもKYCも不要。', th: 'เริ่มด้วยกระเป๋าจำลอง $100,000 ไม่ต้องใช้บัตร ไม่ต้อง KYC', vi: 'Bắt đầu với ví mô phỏng $100.000. Không thẻ, không KYC.' }),
    s2t: tr(language, { en: 'Pick your AI', ja: 'AIを選ぶ', th: 'เลือก AI ของคุณ', vi: 'Chọn AI của bạn' }),
    s2d: tr(language, { en: 'OpenAI, Gemini, Grok, Qwen, GLM, Claude, or a local model — bring any key, switch anytime.', ja: 'OpenAI・Gemini・Grok・Qwen・GLM・Claude・ローカルモデル。どのキーでも、いつでも切替可能。', th: 'OpenAI, Gemini, Grok, Qwen, GLM, Claude หรือโมเดลโลคอล — ใช้คีย์ใดก็ได้ เปลี่ยนได้ตลอด', vi: 'OpenAI, Gemini, Grok, Qwen, GLM, Claude hay mô hình cục bộ — dùng khóa nào cũng được.' }),
    s3t: tr(language, { en: 'Run the analyst desk', ja: 'アナリストデスクを実行', th: 'รันทีมนักวิเคราะห์', vi: 'Chạy bàn phân tích' }),
    s3d: tr(language, { en: 'Ask for a call on BTC, ETH or a US stock — get BUY / SELL / HOLD with confidence and a full report.', ja: 'BTC・ETH・米国株について尋ねると、信頼度とレポート付きで判断が返ります。', th: 'ขอคำตัดสินสำหรับ BTC, ETH หรือหุ้นสหรัฐ — รับ ซื้อ/ขาย/ถือ พร้อมความมั่นใจและรายงานเต็ม', vi: 'Hỏi về BTC, ETH hay cổ phiếu Mỹ — nhận MUA/BÁN/GIỮ kèm độ tin cậy và báo cáo.' }),
    s4t: tr(language, { en: 'Automate it', ja: '自動化する', th: 'ทำให้อัตโนมัติ', vi: 'Tự động hóa' }),
    s4d: tr(language, { en: 'Turn the call into a rule. The worker re-runs it on your schedule and paper-trades when it agrees with you.', ja: '判断をルール化。スケジュール通りに再実行し、条件が合えば模擬取引します。', th: 'เปลี่ยนคำตัดสินเป็นกฎ ระบบรันซ้ำตามตารางและเทรดจำลองเมื่อเข้าเงื่อนไข', vi: 'Biến quyết định thành quy tắc. Worker chạy lại theo lịch và giao dịch mô phỏng khi khớp điều kiện.' }),

    whoEyebrow: tr(language, { en: 'WHO IT IS FOR', ja: '対象', th: 'เหมาะกับใคร', vi: 'DÀNH CHO AI' }),
    whoTitle: tr(language, { en: 'Built for traders in the US and Thailand — and their agents.', ja: '米国とタイのトレーダー、そして彼らのエージェントのために。', th: 'สร้างเพื่อเทรดเดอร์ในสหรัฐฯ และไทย — และเอเจนต์ของพวกเขา', vi: 'Dành cho trader ở Mỹ và Thái Lan — và các agent của họ.' }),
    w1t: tr(language, { en: 'Curious traders', ja: '好奇心あるトレーダー', th: 'เทรดเดอร์ผู้อยากรู้', vi: 'Trader tò mò' }),
    w1d: tr(language, { en: 'Test what AI would actually do with your ideas before any real money moves. US market hours and Thai time both respected.', ja: '実際のお金を動かす前に、AIが何をするか試せます。米国市場・タイ時間の両方に対応。', th: 'ทดสอบว่า AI จะทำอะไรกับไอเดียของคุณก่อนใช้เงินจริง รองรับเวลาตลาดสหรัฐฯ และเวลาไทย', vi: 'Thử xem AI sẽ làm gì với ý tưởng của bạn trước khi động tiền thật.' }),
    w2t: tr(language, { en: 'Strategy builders', ja: '戦略ビルダー', th: 'นักสร้างกลยุทธ์', vi: 'Người xây chiến lược' }),
    w2d: tr(language, { en: 'Compare providers head-to-head, tune confidence thresholds, and read every debate that led to every trade.', ja: 'プロバイダーを比較し、しきい値を調整し、全トレードの議論を確認できます。', th: 'เปรียบเทียบผู้ให้บริการ ปรับเกณฑ์ความมั่นใจ และอ่านทุกการถกเถียงเบื้องหลังทุกเทรด', vi: 'So sánh các nhà cung cấp, tinh chỉnh ngưỡng, đọc mọi cuộc tranh luận sau mỗi lệnh.' }),
    w3t: tr(language, { en: 'AI-agent developers', ja: 'AIエージェント開発者', th: 'นักพัฒนาเอเจนต์ AI', vi: 'Dev AI-agent' }),
    w3d: tr(language, { en: 'Agents register and publish signals with a single API call — no human in the loop required.', ja: 'エージェントはAPIひとつで登録・シグナル発信。人手は不要。', th: 'เอเจนต์ลงทะเบียนและส่งสัญญาณด้วย API เดียว — ไม่ต้องมีมนุษย์ในลูป', vi: 'Agent đăng ký và phát tín hiệu bằng một API call — không cần con người.' }),

    featEyebrow: tr(language, { en: 'UNDER THE HOOD', ja: '機能', th: 'เบื้องหลัง', vi: 'BÊN TRONG' }),
    features: [
      tr(language, { en: '8 AI providers, one switch', ja: '8つのAIプロバイダー', th: 'ผู้ให้บริการ AI 8 ราย', vi: '8 nhà cung cấp AI' }),
      tr(language, { en: 'Multi-agent debate → decision + report', ja: 'マルチエージェント討議→判断+レポート', th: 'ถกเถียงหลายเอเจนต์ → คำตัดสิน + รายงาน', vi: 'Tranh luận đa tác nhân → quyết định + báo cáo' }),
      tr(language, { en: 'Real prices: OKX · Hyperliquid · Polymarket', ja: '実勢価格: OKX・Hyperliquid・Polymarket', th: 'ราคาจริง: OKX · Hyperliquid · Polymarket', vi: 'Giá thật: OKX · Hyperliquid · Polymarket' }),
      tr(language, { en: 'Spot & futures terminals with live order book', ja: '現物・先物ターミナル（ライブ板）', th: 'เทอร์มินัลสปอต & ฟิวเจอร์สพร้อมสมุดคำสั่งสด', vi: 'Terminal spot & futures với sổ lệnh trực tiếp' }),
      tr(language, { en: 'Public leaderboard & copy-trading', ja: 'リーダーボードとコピートレード', th: 'ลีดเดอร์บอร์ดสาธารณะ & คัดลอกเทรด', vi: 'Bảng xếp hạng & copy-trading' }),
      tr(language, { en: 'Every run audited — action, confidence, reason', ja: '全実行を監査記録', th: 'บันทึกทุกการรัน — การกระทำ ความมั่นใจ เหตุผล', vi: 'Mọi lần chạy đều được ghi lại' }),
    ],

    safety: tr(language, {
      en: 'Sooppiy is research and education software. All trading is simulated — no real funds can move in this platform, and nothing here is financial advice.',
      ja: 'Sooppiyは研究・教育用ソフトウェアです。すべての取引は模擬であり、実際の資金は動きません。投資助言ではありません。',
      th: 'Sooppiy คือซอฟต์แวร์เพื่อการวิจัยและการศึกษา การเทรดทั้งหมดเป็นแบบจำลอง — ไม่มีเงินจริงเคลื่อนไหวในแพลตฟอร์มนี้ และไม่ใช่คำแนะนำทางการเงิน',
      vi: 'Sooppiy là phần mềm nghiên cứu và giáo dục. Mọi giao dịch đều mô phỏng — không có tiền thật, không phải lời khuyên tài chính.',
    }),
    finalTitle: tr(language, { en: 'Watch AI trade your ideas.', ja: 'あなたのアイデアをAIが取引する。', th: 'ดู AI เทรดไอเดียของคุณ', vi: 'Xem AI giao dịch ý tưởng của bạn.' }),
    finalSub: tr(language, { en: 'Free. Simulated. Yours to configure.', ja: '無料・模擬・自由に設定。', th: 'ฟรี จำลอง ปรับแต่งได้ตามใจ', vi: 'Miễn phí. Mô phỏng. Tùy bạn cấu hình.' }),
  }

  const wrap: any = { maxWidth: 1080, margin: '0 auto', padding: '0 24px' }
  const eyebrow: any = { fontSize: 12, letterSpacing: '.22em', color: '#c9a26e', fontWeight: 700 }
  const h2: any = { fontSize: 'clamp(28px,4.4vw,44px)', fontWeight: 800, letterSpacing: '-.02em', lineHeight: 1.12, margin: '14px 0 40px', color: '#f4efe6' }
  const card: any = { background: 'rgba(255,255,255,0.035)', border: '1px solid rgba(255,255,255,0.09)', borderRadius: 18, padding: '26px 26px' }
  const muted = 'rgba(235,228,215,0.62)'

  return (
    <div style={{ minHeight: '100vh', background: '#0b0a09', color: '#f4efe6', fontFamily: 'inherit' }}>
      <style>{`
        .mk-grid{display:grid;gap:18px;grid-template-columns:repeat(auto-fit,minmax(260px,1fr))}
        .mk-cta{transition:transform .15s ease, box-shadow .15s ease}
        .mk-cta:hover{transform:translateY(-2px)}
        @keyframes mkFade{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
        .mk-hero>*{animation:mkFade .7s ease both}
        .mk-hero>*:nth-child(2){animation-delay:.12s}.mk-hero>*:nth-child(3){animation-delay:.22s}.mk-hero>*:nth-child(4){animation-delay:.32s}
      `}</style>

      {/* top bar */}
      <header style={{ ...wrap, display: 'flex', alignItems: 'center', gap: 14, padding: '22px 24px' }}>
        <span style={{ fontWeight: 800, fontSize: 19, letterSpacing: '.02em' }}>Sooppiy</span>
        <span style={{ fontSize: 11, color: muted, letterSpacing: '.14em' }}>AI · ANALYZE · AUTOMATE</span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
          {Object.entries(LANGS).map(([code, label]) => (
            <button key={code} onClick={() => setLanguage(code as any)}
              style={{ background: language === code ? 'rgba(255,255,255,0.12)' : 'none', border: 'none', color: language === code ? '#f4efe6' : muted, fontSize: 12, padding: '5px 9px', borderRadius: 7, cursor: 'pointer' }}>{label}</button>
          ))}
        </span>
        <Link to="/login" style={{ color: '#f4efe6', textDecoration: 'none', fontSize: 14, padding: '8px 16px', border: '1px solid rgba(255,255,255,0.22)', borderRadius: 10 }}>{T.login}</Link>
        <Link to="/register" className="mk-cta" style={{ color: '#141210', textDecoration: 'none', fontSize: 14, fontWeight: 700, padding: '8px 18px', background: '#e8ddc8', borderRadius: 10 }}>{T.start}</Link>
      </header>

      {/* hero */}
      <section style={{ ...wrap, padding: '9vh 24px 10vh', position: 'relative' }}>
        <div aria-hidden style={{ position: 'absolute', inset: '-40% -20% auto', height: '90%', background: 'radial-gradient(60% 60% at 50% 30%, rgba(194,106,69,0.22), transparent 70%)', pointerEvents: 'none' }} />
        <div className="mk-hero" style={{ position: 'relative' }}>
          <h1 style={{ fontSize: 'clamp(42px,8vw,88px)', lineHeight: 1.04, letterSpacing: '-.03em', fontWeight: 800, margin: 0, color: '#f4efe6' }}>
            {T.heroA}<br />
            <span style={{ background: 'linear-gradient(92deg,#e8b07a,#c26a45 55%,#8b5cf6)', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' }}>{T.heroB}</span><br />
            {T.heroC}
          </h1>
          <p style={{ maxWidth: 640, fontSize: 17.5, lineHeight: 1.65, color: muted, margin: '28px 0 36px' }}>{T.heroSub}</p>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <Link to="/register" className="mk-cta" style={{ textDecoration: 'none', background: 'linear-gradient(92deg,#c26a45,#a8442a)', color: '#fff', fontWeight: 700, fontSize: 16, padding: '14px 28px', borderRadius: 12, boxShadow: '0 8px 30px rgba(194,106,69,0.35)' }}>{T.ctaPrimary}</Link>
            <Link to="/login" className="mk-cta" style={{ textDecoration: 'none', color: '#f4efe6', fontSize: 16, padding: '14px 24px', borderRadius: 12, border: '1px solid rgba(255,255,255,0.22)' }}>{T.ctaSecondary}</Link>
          </div>
          <div style={{ display: 'flex', gap: 26, marginTop: 46, flexWrap: 'wrap', fontSize: 13, color: muted }}>
            <span>◐ $100,000 simulated wallet</span><span>◈ Live market data</span><span>⚡ 8 AI providers</span><span>EN · 日本語 · ไทย · Tiếng Việt</span>
          </div>
        </div>
      </section>

      {/* what it is */}
      <section style={{ ...wrap, padding: '9vh 24px' }}>
        <div style={eyebrow}>{T.whatEyebrow}</div>
        <h2 style={h2}>{T.whatTitle}</h2>
        <div className="mk-grid">
          {[{ t: T.p1t, d: T.p1d, i: '🧠' }, { t: T.p2t, d: T.p2d, i: '⚙' }, { t: T.p3t, d: T.p3d, i: '◐' }].map((p, i) => (
            <div key={i} style={card}>
              <div style={{ fontSize: 26, marginBottom: 12 }}>{p.i}</div>
              <div style={{ fontWeight: 700, fontSize: 18, marginBottom: 8 }}>{p.t}</div>
              <div style={{ fontSize: 14.5, lineHeight: 1.6, color: muted }}>{p.d}</div>
            </div>
          ))}
        </div>
      </section>

      {/* how to use */}
      <section style={{ ...wrap, padding: '9vh 24px' }}>
        <div style={eyebrow}>{T.howEyebrow}</div>
        <h2 style={h2}>{T.howTitle}</h2>
        <div className="mk-grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(220px,1fr))' }}>
          {[{ t: T.s1t, d: T.s1d }, { t: T.s2t, d: T.s2d }, { t: T.s3t, d: T.s3d }, { t: T.s4t, d: T.s4d }].map((s, i) => (
            <div key={i} style={{ ...card, position: 'relative', paddingTop: 58 }}>
              <span style={{ position: 'absolute', top: 18, left: 22, fontSize: 40, fontWeight: 800, color: 'rgba(232,176,122,0.35)', fontFamily: 'ui-monospace,monospace' }}>{i + 1}</span>
              <div style={{ fontWeight: 700, fontSize: 16.5, marginBottom: 8 }}>{s.t}</div>
              <div style={{ fontSize: 14, lineHeight: 1.6, color: muted }}>{s.d}</div>
            </div>
          ))}
        </div>
      </section>

      {/* who it's for */}
      <section style={{ ...wrap, padding: '9vh 24px' }}>
        <div style={eyebrow}>{T.whoEyebrow}</div>
        <h2 style={h2}>{T.whoTitle}</h2>
        <div className="mk-grid">
          {[{ t: T.w1t, d: T.w1d }, { t: T.w2t, d: T.w2d }, { t: T.w3t, d: T.w3d }].map((w, i) => (
            <div key={i} style={card}>
              <div style={{ fontWeight: 700, fontSize: 17, marginBottom: 8 }}>{w.t}</div>
              <div style={{ fontSize: 14.5, lineHeight: 1.6, color: muted }}>{w.d}</div>
            </div>
          ))}
        </div>
      </section>

      {/* features strip */}
      <section style={{ ...wrap, padding: '7vh 24px' }}>
        <div style={eyebrow}>{T.featEyebrow}</div>
        <div className="mk-grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(300px,1fr))', marginTop: 22 }}>
          {T.features.map((f, i) => (
            <div key={i} style={{ display: 'flex', gap: 12, alignItems: 'flex-start', padding: '14px 0', borderTop: '1px solid rgba(255,255,255,0.09)' }}>
              <span style={{ color: '#e8b07a', fontWeight: 800 }}>—</span>
              <span style={{ fontSize: 15.5, lineHeight: 1.5 }}>{f}</span>
            </div>
          ))}
        </div>
      </section>

      {/* safety */}
      <section style={{ ...wrap, padding: '5vh 24px' }}>
        <div style={{ ...card, borderColor: 'rgba(232,176,122,0.35)', background: 'rgba(232,176,122,0.06)', fontSize: 14, lineHeight: 1.65, color: muted }}>
          ⚠ {T.safety}
        </div>
      </section>

      {/* final CTA */}
      <section style={{ ...wrap, padding: '11vh 24px 13vh', textAlign: 'center' }}>
        <h2 style={{ ...h2, fontSize: 'clamp(32px,5.6vw,56px)', margin: '0 0 12px' }}>{T.finalTitle}</h2>
        <p style={{ color: muted, marginBottom: 34, fontSize: 16 }}>{T.finalSub}</p>
        <Link to="/register" className="mk-cta" style={{ textDecoration: 'none', background: 'linear-gradient(92deg,#c26a45,#a8442a)', color: '#fff', fontWeight: 700, fontSize: 17, padding: '16px 36px', borderRadius: 13, boxShadow: '0 8px 30px rgba(194,106,69,0.35)' }}>{T.ctaPrimary}</Link>
      </section>

      <footer style={{ borderTop: '1px solid rgba(255,255,255,0.08)', padding: '26px 0', textAlign: 'center', fontSize: 12.5, color: 'rgba(235,228,215,0.4)' }}>
        © 2026 Sooppiy — simulated trading for research & education. Not financial advice.
      </footer>
    </div>
  )
}

export default MarketingPage
