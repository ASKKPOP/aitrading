import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useLanguage } from '../appShared'
import { tr } from '../i18n'

const LANGS: Record<string, string> = { en: 'EN', ja: 'JA', th: 'TH', vi: 'VI' }

// Public landing page — quiet editorial, zero animation, compact blocks.
// Narrative: the AI *measures* market footprints (quant × qualitative × psychology
// proxies), decides on your rules, and paper-trades with hard risk limits.
// Design system: Editorial Terracotta tokens from index.css (Cormorant display,
// Inter Tight UI, JetBrains Mono ledger).

/* theme shorthands (fall back to the terracotta palette) */
const V = {
  bg: 'var(--bg-primary, #f1ead8)',
  bg2: 'var(--bg-secondary, #e8dfc8)',
  card: 'var(--bg-card, #faf6ec)',
  ink: 'var(--text-primary, #0b1220)',
  mut: 'var(--text-secondary, rgba(11,18,32,0.55))',
  faint: 'var(--text-muted, rgba(11,18,32,0.35))',
  line: 'var(--border-color, rgba(11,18,32,0.15))',
  lineStrong: 'var(--border-strong, rgba(11,18,32,0.30))',
  accent: 'var(--accent-primary, #b8542f)',
  accentOn: 'var(--accent-contrast, #faf6ec)',
  up: 'var(--up, #2d9e6b)',
  down: 'var(--down, #8b3a2a)',
  display: 'var(--font-display, "Cormorant Garamond", Georgia, serif)',
  sans: 'var(--font-sans, "Inter Tight", sans-serif)',
  mono: 'var(--font-mono, "JetBrains Mono", monospace)',
}

const wrap: any = { maxWidth: 1040, margin: '0 auto', padding: '0 24px' }
const kicker: any = { fontFamily: V.mono, fontSize: 11.5, letterSpacing: '0.14em', textTransform: 'uppercase', color: V.accent, fontWeight: 500 }
const cardS: any = { background: V.card, border: `1px solid ${V.line}`, borderRadius: 12, padding: '18px 20px' }
const h2S: any = { fontFamily: V.display, fontWeight: 500, fontSize: 'clamp(28px,3.6vw,40px)', letterSpacing: '-0.02em', lineHeight: 1.08, color: V.ink, margin: '10px 0 10px' }

export function MarketingPage() {
  const { language, setLanguage } = useLanguage()
  const [btc, setBtc] = useState<{ price: number; pct: number } | null>(null)

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
    const iv = setInterval(load, 15000)
    return () => { alive = false; clearInterval(iv) }
  }, [])

  const T = {
    login: tr(language, { en: 'Log in', ja: 'ログイン', th: 'เข้าสู่ระบบ', vi: 'Đăng nhập' }),
    signup: tr(language, { en: 'Sign up', ja: '登録', th: 'สมัคร', vi: 'Đăng ký' }),

    heroKicker: tr(language, { en: 'AI AUTO-TRADING · PAPER ONLY', ja: 'AI自動売買 · 模擬のみ', th: 'เทรดอัตโนมัติด้วย AI · จำลองเท่านั้น', vi: 'GIAO DỊCH AI TỰ ĐỘNG · CHỈ MÔ PHỎNG' }),
    heroH1a: tr(language, { en: 'Signals are measured,', ja: 'シグナルは予測ではなく、', th: 'สัญญาณคือสิ่งที่วัดได้', vi: 'Tín hiệu là thứ đo được,' }),
    heroH1b: tr(language, { en: 'not predicted.', ja: '測定するもの。', th: 'ไม่ใช่การทำนาย', vi: 'không phải dự đoán.' }),
    heroSub: tr(language, {
      en: 'The AI reads the traces a market already left — volume surges, whale wallets, news, crowd psychology — combines them with quant triggers, and paper-trades on your rules with hard risk limits.',
      ja: 'AIは市場に残された痕跡 — 出来高急増・クジラのウォレット・ニュース・群集心理 — を読み取り、定量トリガーと組み合わせ、厳格なリスク制限のもとであなたのルール通りに模擬売買します。',
      th: 'AI อ่านร่องรอยที่ตลาดทิ้งไว้ — ปริมาณพุ่ง กระเป๋าวาฬ ข่าว จิตวิทยาฝูงชน — ผสานกับทริกเกอร์เชิงปริมาณ แล้วเทรดจำลองตามกฎของคุณพร้อมลิมิตความเสี่ยงที่ตายตัว',
      vi: 'AI đọc các dấu vết thị trường để lại — khối lượng tăng vọt, ví cá voi, tin tức, tâm lý đám đông — kết hợp với trigger định lượng, rồi giao dịch mô phỏng theo quy tắc của bạn với giới hạn rủi ro cứng.',
    }),
    ctaStart: tr(language, { en: 'Start free', ja: '無料で始める', th: 'เริ่มฟรี', vi: 'Bắt đầu miễn phí' }),
    ctaBoard: tr(language, { en: 'See leaderboard', ja: 'リーダーボード', th: 'ดูลีดเดอร์บอร์ด', vi: 'Xem bảng xếp hạng' }),
    heroNote: tr(language, { en: 'Research & education software. Every trade is simulated — no real funds, no advice.', ja: '研究・教育用ソフトウェアです。すべての取引は模擬であり、実資金や投資助言はありません。', th: 'ซอฟต์แวร์เพื่อการวิจัยและการศึกษา ทุกการเทรดเป็นแบบจำลอง — ไม่มีเงินจริง ไม่ใช่คำแนะนำ', vi: 'Phần mềm nghiên cứu & giáo dục. Mọi giao dịch đều mô phỏng — không tiền thật, không phải lời khuyên.' }),

    readKicker: tr(language, { en: 'WHAT THE AI READS', ja: 'AIが読むもの', th: 'สิ่งที่ AI อ่าน', vi: 'AI ĐỌC GÌ' }),
    readH: tr(language, { en: 'Six signal elements', ja: '6つのシグナル要素', th: 'องค์ประกอบสัญญาณ 6 อย่าง', vi: 'Sáu yếu tố tín hiệu' }),
    read: [
      { t: tr(language, { en: 'Which coin', ja: 'どのコイン', th: 'เหรียญไหน', vi: 'Coin nào' }), d: tr(language, { en: 'Scans volume surges, social mention spikes, whale wallet moves and new listings to shortlist candidates.', ja: '出来高急増・ソーシャル言及の急上昇・クジラの移動・新規上場をスキャンして候補を絞ります。', th: 'สแกนปริมาณพุ่ง การพูดถึงในโซเชียล การเคลื่อนไหวกระเป๋าวาฬ และเหรียญลิสต์ใหม่เพื่อคัดตัวเลือก', vi: 'Quét khối lượng tăng vọt, lượt nhắc mạng xã hội, ví cá voi và niêm yết mới để chọn ứng viên.' }) },
      { t: tr(language, { en: 'Why it moved', ja: 'なぜ動いたか', th: 'ทำไมถึงขยับ', vi: 'Vì sao biến động' }), d: tr(language, { en: 'The LLM matches each price move against live news and events — causal tagging in real time.', ja: 'LLMが価格変動をライブのニュース・イベントと照合し、リアルタイムで因果タグ付けします。', th: 'LLM จับคู่การเคลื่อนไหวราคากับข่าวและเหตุการณ์สด — ติดแท็กเชิงสาเหตุแบบเรียลไทม์', vi: 'LLM đối chiếu mỗi biến động giá với tin tức và sự kiện trực tiếp — gắn nhãn nhân quả theo thời gian thực.' }) },
      { t: tr(language, { en: 'When to buy', ja: 'いつ買うか', th: 'ซื้อเมื่อไร', vi: 'Khi nào mua' }), d: tr(language, { en: 'Quant triggers (RSI, basis, funding) combined with qualitative ones (sentiment spikes, odds shifts).', ja: '定量トリガー（RSI・ベーシス・資金調達率）と定性トリガー（感性スパイク・オッズ変化）を結合。', th: 'ทริกเกอร์เชิงปริมาณ (RSI, เบสิส, ฟันดิง) ผสานทริกเกอร์เชิงคุณภาพ (เซนติเมนต์พุ่ง, อัตราต่อรองเปลี่ยน)', vi: 'Trigger định lượng (RSI, basis, funding) kết hợp trigger định tính (tâm lý tăng vọt, tỷ lệ cược đổi).' }) },
      { t: tr(language, { en: 'When to sell', ja: 'いつ売るか', th: 'ขายเมื่อไร', vi: 'Khi nào bán' }), d: tr(language, { en: 'Overheat (RSI overbought), negative sentiment spikes, whale outflows or 3σ volatility force exits.', ja: '過熱（RSI過買い）・部定感性の急増・クジラ流出・3σ変動で強制的に手仕舞います。', th: 'ความร้อนแรงเกิน (RSI ซื้อมากไป) เซนติเมนต์ลบพุ่ง วาฬไหลออก หรือความผันผวน 3σ บังคับปิดสถานะ', vi: 'Quá nóng (RSI quá mua), tâm lý tiêu cực tăng vọt, cá voi rút hoặc biến động 3σ buộc thoát lệnh.' }) },
      { t: tr(language, { en: 'News & hot issues', ja: 'ニュース・注目イベント', th: 'ข่าวและประเด็นร้อน', vi: 'Tin tức & vấn đề nóng' }), d: tr(language, { en: 'News APIs and social feeds, summarised and importance-scored by the LLM to estimate market impact.', ja: 'ニュースAPIとソーシャルフィードをLLMが要約・重要度スコア化し、市場影響を推定します。', th: 'API ข่าวและฟีดโซเชียล ถูก LLM สรุปและให้คะแนนความสำคัญเพื่อประเมินผลกระทบต่อตลาด', vi: 'API tin tức và mạng xã hội được LLM tóm tắt, chấm điểm mức quan trọng để ước tính tác động thị trường.' }) },
      { t: tr(language, { en: 'Psychology', ja: '心理', th: 'จิตวิทยา', vi: 'Tâm lý' }), d: tr(language, { en: 'Fear, shock and anticipation — approximated with proxies: mentions, sentiment scores, volatility, liquidations, odds.', ja: '恐怖・衝撃・期待感 — 言及量・感性スコア・変動率・清算・オッズという代用指標で近似します。', th: 'ความกลัว ช็อก และความคาดหวัง — ประมาณด้วยตัวแทน: การพูดถึง คะแนนเซนติเมนต์ ความผันผวน การล้างพอร์ต อัตราต่อรอง', vi: 'Sợ hãi, sốc và kỳ vọng — xấp xỉ bằng proxy: lượt nhắc, điểm tâm lý, biến động, thanh lý, tỷ lệ cược.' }) },
    ],

    psyKicker: tr(language, { en: 'PSYCHOLOGY, QUANTIFIED', ja: '心理の定量化', th: 'จิตวิทยาเชิงตัวเลข', vi: 'TÂM LÝ ĐƯỢC LƯỢNG HÓA' }),
    psyH: tr(language, { en: 'Not emotions — their footprints', ja: '感情そのものではなく、その痕跡を', th: 'ไม่ใช่อารมณ์ — แต่คือรอยเท้าของมัน', vi: 'Không phải cảm xúc — mà là dấu vết của chúng' }),
    psyRows: [
      { k: tr(language, { en: 'Fear / Greed', ja: '恐怖／強欲', th: 'กลัว / โลภ', vi: 'Sợ / Tham' }), v: tr(language, { en: 'Fear & Greed index · volatility · liquidation data', ja: 'Fear&Greed指数 · 変動率 · 清算データ', th: 'ดัชนี Fear & Greed · ความผันผวน · ข้อมูลการล้างพอร์ต', vi: 'Chỉ số Fear & Greed · biến động · dữ liệu thanh lý' }) },
      { k: tr(language, { en: 'Shock', ja: '衝撃', th: 'ช็อก', vi: 'Sốc' }), v: tr(language, { en: 'Sudden negative sentiment spikes · volume explosions', ja: '部定感性の急激なスパイク · 出来高の爆発', th: 'เซนติเมนต์ลบพุ่งฉับพลัน · ปริมาณระเบิด', vi: 'Tâm lý tiêu cực tăng đột biến · khối lượng bùng nổ' }) },
      { k: tr(language, { en: 'Anticipation', ja: '期待感', th: 'ความคาดหวัง', vi: 'Kỳ vọng' }), v: tr(language, { en: 'Pre-event mention growth · prediction-market odds shifts', ja: 'イベント前の言及増加 · 予測市場オッズの変化', th: 'การพูดถึงก่อนเหตุการณ์เพิ่มขึ้น · อัตราต่อรองตลาดคาดการณ์เปลี่ยน', vi: 'Lượt nhắc tăng trước sự kiện · tỷ lệ cược thị trường dự đoán đổi' }) },
    ],
    psyNote: tr(language, {
      en: 'Honest limits: psychology signals lag and carry noise; the AI measures and reacts — it does not predict feelings. They are never traded alone, always cross-checked against quant signals.',
      ja: '正直な限界：心理シグナルは遅行しノイズが多く、AIは感情を予測するのではなく測定・反応します。単独では売買せず、必ず定量シグナルと照合します。',
      th: 'ข้อจำกัดตามจริง: สัญญาณจิตวิทยาล่าช้าและมีนอยส์ AI วัดและตอบสนอง — ไม่ได้ทำนายความรู้สึก จึงไม่ใช้เดี่ยว ๆ ต้องตรวจไขว้กับสัญญาณเชิงปริมาณเสมอ',
      vi: 'Giới hạn thẳng thắn: tín hiệu tâm lý trễ và nhiễu; AI đo và phản ứng — không dự đoán cảm xúc. Không bao giờ giao dịch đơn lẻ, luôn kiểm chéo với tín hiệu định lượng.',
    }),

    dashKicker: tr(language, { en: 'SIGNAL DASHBOARD', ja: 'シグナルダッシュボード', th: 'แดชบอร์ดสัญญาณ', vi: 'BẢNG TÍN HIỆU' }),
    dashH: tr(language, { en: 'One board, every signal', ja: 'ひとつのボードにすべてのシグナル', th: 'บอร์ดเดียว ครบทุกสัญญาณ', vi: 'Một bảng, mọi tín hiệu' }),
    demoTag: tr(language, { en: 'DEMO · SAMPLE DATA', ja: 'デモ · 例示データ', th: 'เดโม · ข้อมูลตัวอย่าง', vi: 'DEMO · DỮ LIỆU MẪU' }),
    kpiFear: tr(language, { en: 'Fear & Greed', ja: '恐怖・強欲指数', th: 'Fear & Greed', vi: 'Fear & Greed' }),
    kpiFearSub: tr(language, { en: 'neutral → greed', ja: '中立 → 強欲', th: 'กลาง → โลภ', vi: 'trung lập → tham' }),
    kpiNews: tr(language, { en: 'News sentiment (24h)', ja: 'ニュース感性 (24h)', th: 'เซนติเมนต์ข่าว (24 ชม.)', vi: 'Tâm lý tin tức (24h)' }),
    kpiNewsSub: tr(language, { en: '1,284 items analysed', ja: '1,284件を分析', th: 'วิเคราะห์ 1,284 รายการ', vi: 'phân tích 1.284 mục' }),
    kpiShock: tr(language, { en: 'Shock alerts', ja: '衝撃検知', th: 'แจ้งเตือนช็อก', vi: 'Cảnh báo sốc' }),
    kpiShockSub: tr(language, { en: 'volatility · liquidations', ja: '変動率 · 清算', th: 'ความผันผวน · การล้างพอร์ต', vi: 'biến động · thanh lý' }),
    kpiBtc: tr(language, { en: 'Live BTC', ja: 'ライブBTC', th: 'BTC สด', vi: 'BTC trực tiếp' }),
    thCoin: tr(language, { en: 'Coin', ja: 'コイン', th: 'เหรียญ', vi: 'Coin' }),
    thSignal: tr(language, { en: 'Signal', ja: 'シグナル', th: 'สัญญาณ', vi: 'Tín hiệu' }),
    thWhy: tr(language, { en: 'Reason', ja: '根拠', th: 'เหตุผล', vi: 'Lý do' }),
    thWhen: tr(language, { en: 'Trigger', ja: 'トリガー', th: 'ทริกเกอร์', vi: 'Trigger' }),
    sigBuy: tr(language, { en: 'BUY', ja: '買い', th: 'ซื้อ', vi: 'MUA' }),
    sigSell: tr(language, { en: 'SELL', ja: '売り', th: 'ขาย', vi: 'BÁN' }),
    sigHold: tr(language, { en: 'HOLD', ja: '様子見', th: 'ถือ', vi: 'GIỮ' }),
    rows: [
      { coin: 'BTC', sig: 'buy', why: tr(language, { en: 'ETF inflow news + fear index recovering; basis widening', ja: 'ETF流入ニュース + 恐怖指数回復、ベーシス拡大', th: 'ข่าวเงินไหลเข้า ETF + ดัชนีความกลัวฟื้น เบสิสกว้างขึ้น', vi: 'Tin ETF vào ròng + chỉ số sợ hồi phục; basis mở rộng' }), when: tr(language, { en: 'spot–futures gap ≥ 1.2%', ja: '現物-先物ギャップ ≥ 1.2%', th: 'ส่วนต่างสปอต–ฟิวเจอร์ส ≥ 1.2%', vi: 'chênh spot–futures ≥ 1,2%' }) },
      { coin: 'SOL', sig: 'sell', why: tr(language, { en: 'Mentions fading + whale outflow; liquidation risk', ja: '言及減少 + クジラ流出、清算リスク', th: 'การพูดถึงลดลง + วาฬไหลออก เสี่ยงล้างพอร์ต', vi: 'Lượt nhắc giảm + cá voi rút; rủi ro thanh lý' }), when: tr(language, { en: 'RSI 74 + negative sentiment spike', ja: 'RSI 74 + 部定感性スパイク', th: 'RSI 74 + เซนติเมนต์ลบพุ่ง', vi: 'RSI 74 + tâm lý tiêu cực tăng vọt' }) },
      { coin: 'XRP', sig: 'hold', why: tr(language, { en: 'Ruling anticipation; odds moved 0.61 → 0.68', ja: '判決への期待、オッズ 0.61→0.68', th: 'รอคำตัดสิน อัตราต่อรองขยับ 0.61 → 0.68', vi: 'Kỳ vọng phán quyết; tỷ lệ cược 0,61 → 0,68' }), when: tr(language, { en: 'event-driven — wait for headline', ja: 'イベントドリブン — ヘッドライン待ち', th: 'อิงเหตุการณ์ — รอพาดหัวข่าว', vi: 'theo sự kiện — chờ tin chính thức' }) },
    ],
    dashNote: tr(language, { en: 'Signal = quant (basis · RSI · liquidations · on-chain) × qualitative (news sentiment · mentions · prediction-market odds).', ja: 'シグナル = 定量（ベーシス·RSI·清算·オンチェーン）× 定性（ニュース感性·言及量·予測市場オッズ）。', th: 'สัญญาณ = เชิงปริมาณ (เบสิส · RSI · การล้างพอร์ต · ออนเชน) × เชิงคุณภาพ (เซนติเมนต์ข่าว · การพูดถึง · อัตราต่อรอง)', vi: 'Tín hiệu = định lượng (basis · RSI · thanh lý · on-chain) × định tính (tâm lý tin tức · lượt nhắc · tỷ lệ cược).' }),

    skillKicker: tr(language, { en: 'TRADING SKILLS', ja: 'トレーディングスキル', th: 'สกิลเทรดดิ้ง', vi: 'KỸ NĂNG GIAO DỊCH' }),
    skillH: tr(language, { en: 'Composable skills, one workflow', ja: '組み合わせ可能なスキル、ひとつのワークフロー', th: 'สกิลประกอบกันได้ ในเวิร์กโฟลว์เดียว', vi: 'Kỹ năng lắp ghép, một quy trình' }),
    skillSub: tr(language, {
      en: 'Each capability is a small, reusable skill. Chain them: collect signals → score in a sheet → visualise → journal → review.',
      ja: '各機能は小さな再利用可能スキル。連結できます：シグナル収集 → スコアリング → 可視化 → 記録 → 振り返り。',
      th: 'ทุกความสามารถคือสกิลเล็ก ๆ ที่ใช้ซ้ำได้ ต่อกันเป็นสาย: เก็บสัญญาณ → ให้คะแนน → แสดงผล → บันทึก → ทบทวน',
      vi: 'Mỗi năng lực là một kỹ năng nhỏ, tái sử dụng. Xâu chuỗi: thu tín hiệu → chấm điểm → trực quan hóa → ghi nhật ký → đánh giá.',
    }),
    skills: [
      { n: 'trading-signal-collector', d: tr(language, { en: 'Gathers quant + sentiment signals into one scored feed', ja: '定量+感性シグナルを1つのスコア付きフィードに収集', th: 'รวบรวมสัญญาณเชิงปริมาณ+เซนติเมนต์เป็นฟีดเดียวพร้อมคะแนน', vi: 'Gom tín hiệu định lượng + tâm lý vào một feed có điểm' }) },
      { n: 'market-breadth-analyzer', d: tr(language, { en: 'Breadth score distribution from public CSVs — no API key', ja: '公開CSVから市場の広がりスコアを算出 — APIキー不要', th: 'กระจายคะแนนความกว้างตลาดจาก CSV สาธารณะ — ไม่ต้องใช้คีย์', vi: 'Phân bố điểm độ rộng thị trường từ CSV công khai — không cần API key' }) },
      { n: 'uptrend-analyzer', d: tr(language, { en: 'Uptrend participation from public data — no API key', ja: '公開データから上昇トレンド参加率を測定 — APIキー不要', th: 'การมีส่วนร่วมในแนวโน้มขึ้นจากข้อมูลสาธารณะ — ไม่ต้องใช้คีย์', vi: 'Mức tham gia xu hướng tăng từ dữ liệu công khai — không cần API key' }) },
      { n: 'position-sizer', d: tr(language, { en: 'Pure sizing math — Kelly-style bet limits', ja: '純粋なサイジング計算 — ケリー基準のベット制限', th: 'คณิตขนาดสถานะล้วน ๆ — ลิมิตเดิมพันแบบเคลลี', vi: 'Toán khối lượng thuần — giới hạn cược kiểu Kelly' }) },
      { n: 'trader-memory-core', d: tr(language, { en: 'Local journaling of every decision, trade or not', ja: '売買の有無を問わず全判断をローカル記録', th: 'บันทึกทุกการตัดสินใจในเครื่อง ไม่ว่าจะเทรดหรือไม่', vi: 'Nhật ký cục bộ mọi quyết định, có lệnh hay không' }) },
      { n: 'signal-postmortem', d: tr(language, { en: 'Review framework — prune what loses, keep what works', ja: '振り返りフレームワーク — 負けを削り、勝ちを残す', th: 'กรอบทบทวน — ตัดที่แพ้ เก็บที่ได้ผล', vi: 'Khung đánh giá — cắt cái thua, giữ cái hiệu quả' }) },
    ],
    caps: [
      tr(language, { en: 'Backtesting', ja: 'バックテスト', th: 'แบ็กเทสต์', vi: 'Backtest' }),
      tr(language, { en: 'Signal generation', ja: 'シグナル生成', th: 'สร้างสัญญาณ', vi: 'Tạo tín hiệu' }),
      tr(language, { en: 'Order execution (paper)', ja: '注文執行（模擬）', th: 'ส่งคำสั่ง (จำลอง)', vi: 'Khớp lệnh (mô phỏng)' }),
      tr(language, { en: 'Trade journaling', ja: '取引記録', th: 'บันทึกการเทรด', vi: 'Nhật ký giao dịch' }),
      tr(language, { en: 'Risk management', ja: 'リスク管理', th: 'จัดการความเสี่ยง', vi: 'Quản trị rủi ro' }),
    ],

    riskKicker: tr(language, { en: 'RISK, HARD-CODED', ja: 'リスクはコードに固定', th: 'ความเสี่ยงถูกฝังในโค้ด', vi: 'RỦI RO ĐƯỢC MÃ HÓA CỨNG' }),
    riskH: tr(language, { en: 'The part that is not optional', ja: '省略できない部分', th: 'ส่วนที่ไม่มีข้อยกเว้น', vi: 'Phần không thể bỏ qua' }),
    risks: [
      { t: tr(language, { en: 'Position sizing', ja: 'ポジションサイジング', th: 'ขนาดสถานะ', vi: 'Khối lượng vị thế' }), d: tr(language, { en: 'Kelly-criterion style limits cap every bet before it is placed.', ja: 'ケリー基準の制限が、すべてのベットを発注前に制御します。', th: 'ลิมิตแบบเคลลีคุมทุกการเดิมพันก่อนส่งคำสั่ง', vi: 'Giới hạn kiểu Kelly chặn mọi lệnh trước khi đặt.' }) },
      { t: tr(language, { en: 'Hard stop-losses', ja: 'ハード損切り', th: 'จุดตัดขาดทุนตายตัว', vi: 'Cắt lỗ cứng' }), d: tr(language, { en: 'Stops and max-loss limits live in code, where emotions cannot touch them.', ja: '損切りと最大損失の上限はコード内にあり、感情は介入できません。', th: 'จุดตัดขาดทุนและลิมิตขาดทุนสูงสุดอยู่ในโค้ด อารมณ์แตะต้องไม่ได้', vi: 'Điểm dừng và giới hạn lỗ tối đa nằm trong code, cảm xúc không chạm tới.' }) },
      { t: tr(language, { en: 'Circuit breakers', ja: 'サーキットブレーカー', th: 'เซอร์กิตเบรกเกอร์', vi: 'Ngắt mạch' }), d: tr(language, { en: 'Auto-halt on 3σ volatility, API lag or suspected manipulation.', ja: '3σ変動・API遅延・操作疑いで自動停止します。', th: 'หยุดอัตโนมัติเมื่อผันผวน 3σ, API หน่วง หรือสงสัยการปั่นราคา', vi: 'Tự dừng khi biến động 3σ, API trễ hoặc nghi thao túng.' }) },
    ],

    ctaH: tr(language, { en: '$100,000 of paper money. Zero real risk.', ja: '10万ドルの模擬資金。実リスクはゼロ。', th: 'เงินจำลอง $100,000 ความเสี่ยงจริงเป็นศูนย์', vi: '$100.000 tiền mô phỏng. Rủi ro thật bằng không.' }),
    ctaSub: tr(language, { en: 'Configure once. The AI measures, decides and journals — you review.', ja: '一度設定すれば、AIが測定・判断・記録し、あなたは確認するだけ。', th: 'ตั้งค่าครั้งเดียว AI วัด ตัดสินใจ และบันทึก — คุณแค่ทบทวน', vi: 'Cấu hình một lần. AI đo, quyết định và ghi lại — bạn chỉ xem xét.' }),

    legal: tr(language, {
      en: 'Sooppiy is research and education software. All trading on this platform is simulated: no real funds are held, moved, or at risk. Market data is provided for information only. Nothing on this site is investment advice.',
      ja: 'Sooppiyは研究・教育用ソフトウェアです。すべての取引は模擬であり、実際の資金は保有・移動・リスクにさらされません。投資助言ではありません。',
      th: 'Sooppiy คือซอฟต์แวร์วิจัยและการศึกษา การเทรดทั้งหมดเป็นแบบจำลอง ไม่มีเงินจริง ไม่ใช่คำแนะนำการลงทุน',
      vi: 'Sooppiy là phần mềm nghiên cứu và giáo dục. Mọi giao dịch đều mô phỏng. Không phải lời khuyên đầu tư.',
    }),
  }

  const pillBtn: any = { fontFamily: V.sans, fontWeight: 600, fontSize: 14.5, textDecoration: 'none', borderRadius: 8, padding: '11px 22px', display: 'inline-block' }
  const sigPill = (sig: string) => {
    const map: any = {
      buy: { bg: 'var(--up-soft, rgba(45,158,107,0.10))', c: V.up, label: `▲ ${T.sigBuy}` },
      sell: { bg: 'var(--down-soft, rgba(139,58,42,0.10))', c: V.down, label: `▼ ${T.sigSell}` },
      hold: { bg: V.bg2, c: V.mut, label: `■ ${T.sigHold}` },
    }
    const m = map[sig]
    return <span style={{ fontFamily: V.mono, fontSize: 11.5, fontWeight: 600, background: m.bg, color: m.c, borderRadius: 999, padding: '4px 10px', whiteSpace: 'nowrap' }}>{m.label}</span>
  }

  return (
    <div style={{ minHeight: '100vh', background: V.bg, color: V.ink, fontFamily: V.sans, lineHeight: 1.55 }}>

      {/* ── topbar ── */}
      <header style={{ position: 'sticky', top: 0, zIndex: 20, background: V.card, borderBottom: `1px solid ${V.line}` }}>
        <div style={{ ...wrap, display: 'flex', alignItems: 'center', gap: 12, height: 62 }}>
          <span style={{ width: 26, height: 26, borderRadius: '50%', background: V.accent, color: V.accentOn, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 14 }}>s</span>
          <span style={{ fontFamily: V.display, fontStyle: 'italic', fontSize: 21, fontWeight: 500 }}>Sooppiy</span>
          <span style={{ marginLeft: 'auto', display: 'flex', gap: 2, border: `1px solid ${V.line}`, borderRadius: 999, padding: '3px 6px' }}>
            {Object.entries(LANGS).map(([code, label]) => (
              <button key={code} onClick={() => setLanguage(code as any)}
                style={{ background: language === code ? V.accent : 'none', color: language === code ? V.accentOn : V.mut, border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600, padding: '4px 9px', borderRadius: 999, fontFamily: V.sans }}>{label}</button>
            ))}
          </span>
          <Link to="/login" style={{ ...pillBtn, color: V.ink, padding: '9px 16px' }}>{T.login}</Link>
          <Link to="/register" style={{ ...pillBtn, color: V.accentOn, background: V.accent, padding: '9px 18px' }}>{T.signup}</Link>
        </div>
      </header>

      {/* ── hero ── */}
      <section style={{ borderBottom: `1px solid ${V.line}`, padding: '64px 0 56px' }}>
        <div style={wrap}>
          <div style={kicker}>{T.heroKicker}</div>
          <h1 style={{ fontFamily: V.display, fontWeight: 500, fontSize: 'clamp(40px,6vw,72px)', lineHeight: 1.04, letterSpacing: '-0.02em', margin: '14px 0 18px', maxWidth: '18ch' }}>
            {T.heroH1a}<br /><em style={{ fontStyle: 'italic', color: V.accent }}>{T.heroH1b}</em>
          </h1>
          <p style={{ fontSize: 17, color: V.mut, maxWidth: '58ch', margin: '0 0 26px' }}>{T.heroSub}</p>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
            <Link to="/register" style={{ ...pillBtn, background: V.accent, color: V.accentOn }}>{T.ctaStart}</Link>
            <Link to="/login" style={{ ...pillBtn, color: V.ink, border: `1.5px solid ${V.lineStrong}`, background: V.card }}>{T.ctaBoard}</Link>
          </div>
          <p style={{ fontFamily: V.mono, fontSize: 11.5, color: V.faint, marginTop: 20 }}>{T.heroNote}</p>
        </div>
      </section>

      {/* ── six signal elements ── */}
      <section style={{ borderBottom: `1px solid ${V.line}`, padding: '56px 0' }}>
        <div style={wrap}>
          <div style={kicker}>{T.readKicker}</div>
          <h2 style={h2S}>{T.readH}</h2>
          <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', marginTop: 18 }}>
            {T.read.map((r, i) => (
              <div key={i} style={cardS}>
                <div style={{ fontFamily: V.mono, fontSize: 11, color: V.accent, marginBottom: 6 }}>{String(i + 1).padStart(2, '0')}</div>
                <div style={{ fontWeight: 700, fontSize: 16.5, marginBottom: 6 }}>{r.t}</div>
                <div style={{ fontSize: 14, color: V.mut }}>{r.d}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── psychology proxies ── */}
      <section style={{ borderBottom: `1px solid ${V.line}`, padding: '56px 0' }}>
        <div style={wrap}>
          <div style={kicker}>{T.psyKicker}</div>
          <h2 style={h2S}>{T.psyH}</h2>
          <div style={{ ...cardS, padding: 0, marginTop: 18, overflow: 'hidden' }}>
            {T.psyRows.map((r, i) => (
              <div key={i} style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'baseline', padding: '14px 20px', borderBottom: i < T.psyRows.length - 1 ? `1px solid ${V.line}` : 'none' }}>
                <span style={{ fontFamily: V.mono, fontSize: 12.5, fontWeight: 600, color: V.accent, width: 150 }}>{r.k}</span>
                <span style={{ fontSize: 14.5, color: V.ink, flex: 1, minWidth: 240 }}>{r.v}</span>
              </div>
            ))}
          </div>
          <p style={{ fontSize: 13.5, color: V.mut, marginTop: 14, maxWidth: '72ch' }}>{T.psyNote}</p>
        </div>
      </section>

      {/* ── dashboard preview ── */}
      <section style={{ borderBottom: `1px solid ${V.line}`, padding: '56px 0' }}>
        <div style={wrap}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
            <div style={kicker}>{T.dashKicker}</div>
            <span style={{ fontFamily: V.mono, fontSize: 10.5, color: V.faint, border: `1px solid ${V.line}`, borderRadius: 999, padding: '2px 9px' }}>{T.demoTag}</span>
          </div>
          <h2 style={h2S}>{T.dashH}</h2>

          <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', marginTop: 18 }}>
            <div style={cardS}>
              <div style={{ fontFamily: V.mono, fontSize: 11, color: V.faint, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{T.kpiFear}</div>
              <div style={{ fontFamily: V.mono, fontSize: 30, fontWeight: 600, margin: '6px 0 2px' }}>58</div>
              <div style={{ fontSize: 12.5, color: V.mut }}>{T.kpiFearSub}</div>
            </div>
            <div style={cardS}>
              <div style={{ fontFamily: V.mono, fontSize: 11, color: V.faint, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{T.kpiNews}</div>
              <div style={{ fontFamily: V.mono, fontSize: 30, fontWeight: 600, margin: '6px 0 2px', color: V.up }}>+0.42</div>
              <div style={{ fontSize: 12.5, color: V.mut }}>{T.kpiNewsSub}</div>
            </div>
            <div style={cardS}>
              <div style={{ fontFamily: V.mono, fontSize: 11, color: V.faint, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{T.kpiShock}</div>
              <div style={{ fontFamily: V.mono, fontSize: 30, fontWeight: 600, margin: '6px 0 2px', color: V.down }}>2</div>
              <div style={{ fontSize: 12.5, color: V.mut }}>{T.kpiShockSub}</div>
            </div>
            <div style={cardS}>
              <div style={{ fontFamily: V.mono, fontSize: 11, color: V.faint, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{T.kpiBtc}</div>
              <div style={{ fontFamily: V.mono, fontSize: 30, fontWeight: 600, margin: '6px 0 2px' }}>{btc ? `$${btc.price.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '—'}</div>
              <div style={{ fontSize: 12.5, color: btc && btc.pct >= 0 ? V.up : V.down }}>{btc ? `${btc.pct >= 0 ? '+' : ''}${btc.pct.toFixed(2)}% · 24h` : ''}</div>
            </div>
          </div>

          <div style={{ ...cardS, padding: 0, marginTop: 12, overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5, minWidth: 560 }}>
              <thead>
                <tr>
                  {[T.thCoin, T.thSignal, T.thWhy, T.thWhen].map((h, i) => (
                    <th key={i} style={{ textAlign: 'left', fontFamily: V.mono, fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '0.06em', color: V.faint, fontWeight: 600, padding: '10px 16px', borderBottom: `1px solid ${V.line}` }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {T.rows.map((r, i) => (
                  <tr key={i}>
                    <td style={{ padding: '12px 16px', fontFamily: V.mono, fontWeight: 700, borderBottom: i < T.rows.length - 1 ? `1px solid ${V.line}` : 'none' }}>{r.coin}</td>
                    <td style={{ padding: '12px 16px', borderBottom: i < T.rows.length - 1 ? `1px solid ${V.line}` : 'none' }}>{sigPill(r.sig)}</td>
                    <td style={{ padding: '12px 16px', color: V.mut, borderBottom: i < T.rows.length - 1 ? `1px solid ${V.line}` : 'none' }}>{r.why}</td>
                    <td style={{ padding: '12px 16px', color: V.mut, borderBottom: i < T.rows.length - 1 ? `1px solid ${V.line}` : 'none' }}>{r.when}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p style={{ fontFamily: V.mono, fontSize: 12, color: V.mut, marginTop: 12 }}>{T.dashNote}</p>
        </div>
      </section>

      {/* ── skills ── */}
      <section style={{ borderBottom: `1px solid ${V.line}`, padding: '56px 0' }}>
        <div style={wrap}>
          <div style={kicker}>{T.skillKicker}</div>
          <h2 style={h2S}>{T.skillH}</h2>
          <p style={{ fontSize: 15, color: V.mut, maxWidth: '64ch', margin: '0 0 18px' }}>{T.skillSub}</p>
          <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))' }}>
            {T.skills.map((s, i) => (
              <div key={i} style={cardS}>
                <div style={{ fontFamily: V.mono, fontSize: 13, fontWeight: 600, color: V.accent, marginBottom: 5 }}>{s.n}</div>
                <div style={{ fontSize: 14, color: V.mut }}>{s.d}</div>
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 16 }}>
            {T.caps.map((c, i) => (
              <span key={i} style={{ fontFamily: V.mono, fontSize: 12, color: V.ink, background: V.card, border: `1px solid ${V.line}`, borderRadius: 999, padding: '6px 14px' }}>{c}</span>
            ))}
          </div>
        </div>
      </section>

      {/* ── risk ── */}
      <section style={{ borderBottom: `1px solid ${V.line}`, padding: '56px 0' }}>
        <div style={wrap}>
          <div style={kicker}>{T.riskKicker}</div>
          <h2 style={h2S}>{T.riskH}</h2>
          <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', marginTop: 18 }}>
            {T.risks.map((r, i) => (
              <div key={i} style={{ ...cardS, borderLeft: `3px solid ${V.accent}` }}>
                <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 6 }}>{r.t}</div>
                <div style={{ fontSize: 14, color: V.mut }}>{r.d}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── closing CTA ── */}
      <section style={{ borderBottom: `1px solid ${V.line}`, padding: '64px 0', textAlign: 'center' }}>
        <div style={wrap}>
          <h2 style={{ ...h2S, fontSize: 'clamp(32px,4.6vw,52px)' }}>{T.ctaH}</h2>
          <p style={{ fontSize: 16, color: V.mut, margin: '0 0 24px' }}>{T.ctaSub}</p>
          <Link to="/register" style={{ ...pillBtn, background: V.accent, color: V.accentOn, fontSize: 15.5, padding: '13px 30px' }}>{T.ctaStart}</Link>
        </div>
      </section>

      {/* ── footer ── */}
      <footer style={{ padding: '32px 0 48px' }}>
        <div style={{ ...wrap, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <span style={{ fontFamily: V.display, fontStyle: 'italic', fontSize: 18 }}>Sooppiy</span>
            <span style={{ fontFamily: V.mono, fontSize: 11, color: V.faint }}>AI · ANALYZE · AUTOMATE</span>
            <span style={{ marginLeft: 'auto', display: 'flex', gap: 16, fontSize: 13 }}>
              <Link to="/login" style={{ color: V.mut, textDecoration: 'none' }}>{T.login}</Link>
              <Link to="/register" style={{ color: V.mut, textDecoration: 'none' }}>{T.signup}</Link>
              <a href="mailto:support@sooppiy.app" style={{ color: V.mut, textDecoration: 'none' }}>Support</a>
            </span>
          </div>
          <p style={{ fontSize: 12, color: V.faint, maxWidth: '90ch', margin: 0 }}>{T.legal}</p>
          <p style={{ fontFamily: V.mono, fontSize: 11, color: V.faint, margin: 0 }}>© 2026 Sooppiy</p>
        </div>
      </footer>
    </div>
  )
}

export default MarketingPage
