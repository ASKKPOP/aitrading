"""Generate the member guide "How your fleet decides to trade" in 5 languages.

Source material:
  docs/reports/2026-07-25-extension-e1-e2-analysis.html   (E1 routing, E2 alerts)
  docs/design/order-decision-pipeline.html                (who decides what)

Both sources are engineering documents. This is the member-facing distillation:
no file paths, no function names, no cost models — the questions a member
actually asks ("why did my fleet do that?", "who decided it?", "what protects
me?").

ONE template, five string tables. Writing five HTML files by hand guarantees
they drift; generating them guarantees identical structure and identical
diagrams, so a fix in one is a fix in all.

Usage:  python docs/design/build_decisions_guide.py
Writes: docs/design/decisions-guide-{lang}.html
Then run build_guide_content.py to publish into service/server/guide_content/.

NOTE: ko/en are authored. ja/th/vi are machine-translated from the English and
have NOT had native review — they are marked as such in the page footer.
"""

from __future__ import annotations

import pathlib

LANGS = ("ko", "en", "ja", "th", "vi")
OUT = pathlib.Path(__file__).resolve().parent

# ─────────────────────────── strings ───────────────────────────
S: dict[str, dict[str, str]] = {
    "ko": {
        "html_lang": "ko",
        "font": '"Apple SD Gothic Neo","Malgun Gothic"',
        "title": "자동매매는 어떻게 판단하는가",
        "eyebrow": "Sooppiy · 회원 가이드",
        "lede": "분석부터 실제 주문까지, 매 사이클에 무슨 일이 일어나는지 — 그리고 <strong>무엇을 AI가 결정하고 무엇을 안전장치가 결정하는지</strong>.",
        "rule_t": "핵심 원칙",
        "rule_b": "주문은 AI가 결정하거나, 아예 나가지 않습니다. AI가 <em>할지</em>, <em>어느 방향</em>, <em>얼마나</em>, <em>어디서 끊을지</em>를 정합니다. 안전장치는 그 주문을 <em>허용할지</em>만 정하며, 더 작게·더 타이트하게만 만들 수 있고 결코 키우지 않습니다.",
        "s1": "한 사이클의 여정",
        "s1_p": "보유 종목마다 정해진 간격으로 반복됩니다. 각 단계는 통과하거나, 사유와 함께 사이클을 종료합니다.",
        "f1_t": "분석에서 주문까지",
        "f1_s": "파란색 = AI 판단 · 주황색 = 안전장치 확인",
        "n1": "상황 판별", "d1": "평범한 순간인가, 중대한 순간인가",
        "n2": "분석", "d2": "빠른 판독 또는 애널리스트 4인 전체 회의",
        "n3": "판단", "d3": "매수 · 매도 · 관망, 그리고 확신도",
        "n4": "주문 설계", "d4": "규모 · 손절 · 목표를 이 종목에 맞춰",
        "n5": "안전 확인", "d5": "리스크 한도 · 노출 상한 · 손익비",
        "n6": "주문", "d6": "체결과 근거를 함께 기록",
        "s2": "무엇을 누가 결정하는가",
        "f2_t": "판단 주체",
        "f2_s": "한 사이클의 21개 단계",
        "lg_ai": "AI 판단 — 6단계", "lg_code": "안전장치 확인 — 14단계", "lg_ex": "실행 — 1",
        "f2_c": "숫자만 보면 오해하기 쉽습니다. 14개 안전 단계는 <em>거부하거나 줄이는</em> 역할만 합니다. 거래를 만들어내거나 방향을 정할 수 있는 것은 하나도 없습니다.",
        "t_dec": "결정", "t_who": "주체", "t_other": "반대편이 할 수 있는 일",
        "r1": "거래할 것인가", "r1o": "안전장치는 거부만 가능, 개시 불가",
        "r2": "어느 방향인가", "r2o": "안전장치는 절대 방향을 고르지 않음",
        "r3": "얼마나 크게", "r3o": "안전장치는 줄이기만 — 한도·노출·최소단위",
        "r4": "손절은 어디에", "r4o": "안전장치는 손익비 하한을 강제",
        "r5": "목표는 어디에", "r5o": "안전장치는 더 멀리만 밀 수 있고 가까이 당기지 못함",
        "r6": "이 주문이 허용되는가", "r6o": "AI는 리스크 한도를 넘을 수 없음",
        "r7": "손절로 청산", "r7o": "의도적으로 안전장치 담당 — 아래 설명",
        "s3": "언제 전체 분석팀이 소집되는가",
        "s3_p": "네 가지 신호가 사이클을 정밀 분석으로 보낼 수 있습니다. 신호가 떴다고 자동으로 소집되지는 않습니다 — <strong>이 종목에 정말 중요한지 데스크가 직접 판단합니다.</strong>",
        "g1": "이벤트 구간", "g1d": "주요 경제지표 발표 임박",
        "g2": "시장 충격", "g2d": "비정상 거래량을 동반한 급변동",
        "g3": "군중 심리 극단", "g3d": "공포·탐욕 지표가 극단",
        "g4": "손절 근접", "g4d": "보유 포지션이 손절선에 근접",
        "s4": "AI가 쓰는 주문서",
        "s4_p": "예전에는 모든 종목에 같은 손절 5% · 목표 10%를 적용했습니다. 이제는 AI가 <strong>그 종목에 맞춰</strong> 정합니다. 실제 사례입니다:",
        "th_sym": "종목", "th_vol": "변동성", "th_stop": "AI 손절", "th_tgt": "AI 목표", "th_old": "기존 고정값",
        "s4_c": "같은 날, 같은 데스크입니다. 변동이 큰 종목에는 손절을 <strong>거의 두 배</strong>로 넓게 잡았습니다. 고정값은 둘 다 5%로 취급합니다.",
        "s5": "AI를 읽을 수 없을 때",
        "s5_p": "모든 실패 경로는 <strong>신규 진입 없음</strong>으로 끝납니다. 추측으로 거래하지 않습니다.",
        "th_case": "상황", "th_res": "결과",
        "c1": "AI 응답 불가", "c1r": "관망 — 규칙이 방향을 만들어내지 못함",
        "c2": "응답이 불완전", "c2r": "읽을 수 있는 부분만 복구, 아니면 관망",
        "c3": "AI가 주문 설계를 유보", "c3r": "기존 기본값 적용",
        "c4": "안전 한도 초과", "c4r": "한도까지 축소하거나 거부",
        "c5": "손익비 미달", "c5r": "진입 거부",
        "s6": "왜 청산만은 안전장치가 담당하는가",
        "s6_p": "손절이 AI 응답에 의존한다면, 정작 가장 필요한 순간 — 서비스 장애 시 — 에 작동하지 않습니다. 핵심 원칙은 <strong>진입</strong>에 관한 것입니다. 포지션을 여는 것은 판단이고, 손실을 막으려 닫는 것은 산술입니다.",
        "s7": "맞춤 핫이슈 알림",
        "s7_p": "시장 이벤트는 <strong>시장에 관한 사실</strong>이지만, 그것이 중요한지는 <strong>본인에 관한 사실</strong>입니다. 모든 알림은 발송 전에 본인 포지션과 대조합니다.",
        "a1": "감지", "a1d": "매시간 전 종목",
        "a2": "검증", "a2d": "보유 방향 · 레버리지 · 손절까지 거리",
        "a3a": "유리함", "a3ad": "가벼운 참고",
        "a3b": "불리함", "a3bd": "긴급 알림",
        "a3c": "영향 없음", "a3cd": "알림 없음",
        "s7_c": "하나의 이벤트, 세 가지 결과. 대부분의 회원이 아무 알림도 받지 않는 것이 정상입니다.",
        "s8": "이용자 입장에서 보이는 것",
        "th_see": "이런 경험", "th_why": "이유",
        "w1": "어떤 사이클은 즉시, 어떤 사이클은 오래 걸림", "w1d": "평범한 순간은 빠른 경로, 중대한 순간은 전체 분석팀",
        "w2": "수익 중이던 포지션이 저절로 정리됨", "w2d": "이익 보호가 수익이 사라지기 전에 확정",
        "w3": "손실 중이던 포지션이 일찍 정리됨", "w3d": "손절 작동 — 큰 손실 대신 통제된 손실",
        "w4": "큰 뉴스에도 알림이 없음", "w4d": "포지션과 대조한 결과 영향 없음. 정상 동작",
        "w5": "RUN이 한 번도 거래하지 않음", "w5d": "비용을 넘길 근거가 없었음. 거래하지 않는 것도 정당한 결과",
        "safe_t": "안전이 항상 우선",
        "safe_b": "AI는 제안하고, 결정하는 것은 설정한 리스크 한도입니다. 모든 행동이 계정의 리스크 검사·포지션 한도·손절을 그대로 통과하며, 버튼 하나로 언제든 전체를 정지할 수 있습니다.",
        "mt_note": "이 문서는 한국어로 작성되었습니다.",
    },
    "en": {
        "html_lang": "en", "font": '"Segoe UI"',
        "title": "How your fleet decides to trade",
        "eyebrow": "Sooppiy · Member Guide",
        "lede": "What happens in every cycle, from analysis to a real order — and <strong>which parts the AI decides versus the safety system</strong>.",
        "rule_t": "The core rule",
        "rule_b": "An order is decided by the AI, or it is not placed. The AI decides <em>whether</em> to trade, <em>which way</em>, <em>how big</em>, and <em>where to cut</em>. The safety system decides only whether that order is <em>allowed</em> — it can make an order smaller or tighter, never larger.",
        "s1": "One cycle, end to end",
        "s1_p": "This repeats at a set interval for each symbol you hold. Every step either passes, or ends the cycle with a recorded reason.",
        "f1_t": "From analysis to order",
        "f1_s": "Blue = the AI decides · Orange = safety check",
        "n1": "Situation check", "d1": "ordinary moment, or critical?",
        "n2": "Analysis", "d2": "a fast read, or the full four-analyst desk",
        "n3": "Decision", "d3": "buy · sell · hold, with a confidence",
        "n4": "Order design", "d4": "size · stop · target, sized to this symbol",
        "n5": "Safety checks", "d5": "risk limits · exposure caps · reward vs risk",
        "n6": "Order", "d6": "the fill, recorded with its reason",
        "s2": "Who decides what",
        "f2_t": "Decision ownership", "f2_s": "the 21 steps in one cycle",
        "lg_ai": "AI decides — 6 steps", "lg_code": "Safety checks — 14 steps", "lg_ex": "Execution — 1",
        "f2_c": "The count misleads on its own. The 14 safety steps only <em>refuse or shrink</em>. Not one of them can create a trade or choose a direction.",
        "t_dec": "Decision", "t_who": "Owner", "t_other": "What the other side may do",
        "r1": "Trade or not", "r1o": "Safety may veto, never originate",
        "r2": "Which direction", "r2o": "Safety never chooses a side",
        "r3": "How big", "r3o": "Safety only shrinks — limits, exposure, minimum size",
        "r4": "Where the stop sits", "r4o": "Safety enforces the reward-vs-risk floor",
        "r5": "Where the target sits", "r5o": "Safety may push it further out, never nearer",
        "r6": "Is this order allowed", "r6o": "The AI cannot exceed a risk limit",
        "r7": "Closing on a stop", "r7o": "Deliberately the safety system — see below",
        "s3": "When the full desk is called",
        "s3_p": "Four signals can send a cycle to deep analysis. A signal firing does not call the desk on its own — <strong>the desk itself judges whether it truly matters for this symbol.</strong>",
        "g1": "Event window", "g1d": "a major economic release is imminent",
        "g2": "Market shock", "g2d": "an abnormal move on unusual volume",
        "g3": "Crowd extremes", "g3d": "fear or greed readings at an extreme",
        "g4": "Near your stop", "g4d": "your position is approaching its safety stop",
        "s4": "The order the AI writes",
        "s4_p": "The platform used to apply the same 5% stop and 10% target to everything. The AI now sizes them <strong>to the symbol</strong>. Real examples:",
        "th_sym": "Symbol", "th_vol": "Volatility", "th_stop": "AI stop", "th_tgt": "AI target", "th_old": "Old fixed value",
        "s4_c": "Same day, same desk. The volatile name got a stop nearly <strong>twice as wide</strong>. The fixed value treats both as 5%.",
        "s5": "When the AI cannot be read",
        "s5_p": "Every failure path ends in <strong>no new position</strong>. It never trades on a guess.",
        "th_case": "Situation", "th_res": "Result",
        "c1": "The AI does not answer", "c1r": "Hold — rules may not invent a direction",
        "c2": "The answer is incomplete", "c2r": "Recover what is readable, otherwise hold",
        "c3": "The AI defers on order design", "c3r": "House defaults apply",
        "c4": "A safety limit is exceeded", "c4r": "Shrunk to the limit, or refused",
        "c5": "Reward does not clear risk", "c5r": "Entry refused",
        "s6": "Why exits stay with the safety system",
        "s6_p": "A stop that depended on the AI answering would not fire during an outage — precisely when it matters most. The core rule governs <strong>opening</strong> a position: that is a judgement call. Closing one to cap a loss is arithmetic.",
        "s7": "Personal hot-issue alerts",
        "s7_p": "A market event is <strong>a fact about the market</strong>; whether it matters is <strong>a fact about you</strong>. Every alert is checked against your own position before it is sent.",
        "a1": "Detect", "a1d": "hourly, across every symbol",
        "a2": "Verify", "a2d": "your direction · leverage · distance to your stop",
        "a3a": "Supports you", "a3ad": "gentle note",
        "a3b": "Runs against you", "a3bd": "urgent alert",
        "a3c": "Not material", "a3cd": "no alert",
        "s7_c": "One event, three outcomes. Most members correctly receive nothing.",
        "s8": "What you might notice",
        "th_see": "You might notice", "th_why": "Why",
        "w1": "Some cycles act instantly, others take longer", "w1d": "Ordinary moments take the fast path; critical ones take the full desk",
        "w2": "A winning position closed on its own", "w2d": "Profit protection banked the gain before it slipped away",
        "w3": "A losing position closed early", "w3d": "The stop fired — a controlled loss instead of a large one",
        "w4": "No alert during big news", "w4d": "It was checked against your position and was not material. That is the system working",
        "w5": "A run never opened a trade", "w5d": "Nothing cleared the cost of trading. Not trading is a valid outcome",
        "safe_t": "Safety, always",
        "safe_b": "The AI recommends — your risk limits decide. Every action passes through your account's risk checks, position limits and stops, and you can stop everything with one button at any time.",
        "mt_note": "This document was authored in English.",
    },
    "ja": {
        "html_lang": "ja", "font": '"Hiragino Sans","Yu Gothic"',
        "title": "自動売買はどう判断するのか",
        "eyebrow": "Sooppiy · 会員ガイド",
        "lede": "分析から実際の注文まで、各サイクルで何が起きるのか — そして<strong>どこをAIが決め、どこを安全装置が決めるのか</strong>。",
        "rule_t": "基本原則",
        "rule_b": "注文はAIが決めるか、出さないかのどちらかです。AIが<em>取引するか</em>、<em>どちら向きか</em>、<em>どれだけか</em>、<em>どこで切るか</em>を決めます。安全装置はその注文を<em>許可するか</em>だけを決め、小さく・厳しくすることはできても大きくすることはありません。",
        "s1": "1サイクルの流れ",
        "s1_p": "保有する銘柄ごとに一定間隔で繰り返されます。各ステップは通過するか、理由を記録してサイクルを終了します。",
        "f1_t": "分析から注文まで",
        "f1_s": "青 = AIが判断 · オレンジ = 安全確認",
        "n1": "状況判定", "d1": "平常時か、重要局面か",
        "n2": "分析", "d2": "簡易判断、または4名体制の完全分析",
        "n3": "判断", "d3": "買い・売り・様子見と確信度",
        "n4": "注文設計", "d4": "数量・損切り・目標をこの銘柄に合わせて",
        "n5": "安全確認", "d5": "リスク上限・エクスポージャー・損益比",
        "n6": "注文", "d6": "約定と根拠を記録",
        "s2": "何を誰が決めるか",
        "f2_t": "判断の主体", "f2_s": "1サイクルの21ステップ",
        "lg_ai": "AIが判断 — 6ステップ", "lg_code": "安全確認 — 14ステップ", "lg_ex": "執行 — 1",
        "f2_c": "数だけでは誤解を招きます。14の安全ステップは<em>拒否または縮小</em>するだけです。取引を生み出したり方向を選べるものは一つもありません。",
        "t_dec": "判断", "t_who": "主体", "t_other": "もう一方ができること",
        "r1": "取引するか", "r1o": "安全装置は拒否のみ、開始はできない",
        "r2": "どちら向きか", "r2o": "安全装置が方向を選ぶことはない",
        "r3": "どれだけの大きさか", "r3o": "安全装置は縮小のみ — 上限・エクスポージャー・最小単位",
        "r4": "損切りの位置", "r4o": "安全装置は損益比の下限を強制",
        "r5": "目標の位置", "r5o": "安全装置は遠ざけることはできても近づけられない",
        "r6": "この注文は許可されるか", "r6o": "AIはリスク上限を超えられない",
        "r7": "損切りでの決済", "r7o": "意図的に安全装置の担当 — 下記参照",
        "s3": "完全分析が呼ばれるとき",
        "s3_p": "4つのシグナルがサイクルを詳細分析に送り得ます。シグナルが出ただけでは呼ばれません — <strong>この銘柄にとって本当に重要かをデスク自身が判断します。</strong>",
        "g1": "イベント期間", "g1d": "主要経済指標の発表が近い",
        "g2": "市場ショック", "g2d": "異常な出来高を伴う急変動",
        "g3": "群集心理の極端", "g3d": "恐怖・強欲指数が極端",
        "g4": "損切り接近", "g4d": "保有ポジションが損切り水準に接近",
        "s4": "AIが書く注文書",
        "s4_p": "以前は全銘柄に同じ損切り5%・目標10%を適用していました。今はAIが<strong>銘柄に合わせて</strong>決めます。実例です:",
        "th_sym": "銘柄", "th_vol": "変動性", "th_stop": "AI損切り", "th_tgt": "AI目標", "th_old": "従来の固定値",
        "s4_c": "同じ日、同じデスクです。変動の大きい銘柄には損切りを<strong>約2倍</strong>広く取りました。固定値は両方を5%として扱います。",
        "s5": "AIが読み取れないとき",
        "s5_p": "すべての失敗経路は<strong>新規建てなし</strong>で終わります。推測で取引することはありません。",
        "th_case": "状況", "th_res": "結果",
        "c1": "AIが応答しない", "c1r": "様子見 — ルールが方向を作ることはない",
        "c2": "応答が不完全", "c2r": "読める部分のみ復元、それ以外は様子見",
        "c3": "AIが注文設計を見送る", "c3r": "既定値を適用",
        "c4": "安全上限を超過", "c4r": "上限まで縮小、または拒否",
        "c5": "損益比が不足", "c5r": "エントリー拒否",
        "s6": "なぜ決済だけは安全装置なのか",
        "s6_p": "損切りがAIの応答に依存すると、最も必要なとき — 障害時 — に作動しません。基本原則は<strong>新規建て</strong>に関するものです。ポジションを開くのは判断であり、損失を止めるために閉じるのは算術です。",
        "s7": "個別ホットイシュー通知",
        "s7_p": "市場イベントは<strong>市場に関する事実</strong>ですが、それが重要かどうかは<strong>あなたに関する事実</strong>です。すべての通知は送信前にご自身のポジションと照合されます。",
        "a1": "検知", "a1d": "毎時、全銘柄",
        "a2": "照合", "a2d": "保有方向・レバレッジ・損切りまでの距離",
        "a3a": "有利", "a3ad": "軽い参考通知",
        "a3b": "不利", "a3bd": "緊急通知",
        "a3c": "影響なし", "a3cd": "通知なし",
        "s7_c": "1つのイベント、3つの結果。大半の会員が何も受け取らないのが正常です。",
        "s8": "利用者から見えること",
        "th_see": "こう見えることがあります", "th_why": "理由",
        "w1": "すぐ動くサイクルと時間がかかるサイクルがある", "w1d": "平常時は簡易経路、重要局面は完全分析",
        "w2": "利益が出ていたポジションが自動で決済された", "w2d": "利益保護が利益の消失前に確定させた",
        "w3": "損失中のポジションが早めに決済された", "w3d": "損切り作動 — 大きな損失ではなく制御された損失",
        "w4": "大きなニュースでも通知が来ない", "w4d": "ポジションと照合した結果、影響がなかった。正常動作です",
        "w5": "RUNが一度も取引しない", "w5d": "取引コストを上回る根拠がなかった。取引しないのも正当な結果です",
        "safe_t": "安全が常に最優先",
        "safe_b": "AIは提案し、決定するのは設定したリスク上限です。すべての行動がアカウントのリスク検査・ポジション上限・損切りを通過し、ボタン一つでいつでも全体を停止できます。",
        "mt_note": "この文書は英語版からの機械翻訳です。母語話者による確認は未実施です。",
    },
    "th": {
        "html_lang": "th", "font": '"Noto Sans Thai","Sarabun"',
        "title": "ระบบเทรดอัตโนมัติตัดสินใจอย่างไร",
        "eyebrow": "Sooppiy · คู่มือสมาชิก",
        "lede": "สิ่งที่เกิดขึ้นในแต่ละรอบ ตั้งแต่การวิเคราะห์จนถึงคำสั่งจริง — และ<strong>ส่วนใดที่ AI ตัดสิน เทียบกับระบบความปลอดภัย</strong>",
        "rule_t": "หลักการสำคัญ",
        "rule_b": "คำสั่งซื้อขายต้องตัดสินโดย AI มิฉะนั้นจะไม่ถูกส่ง AI ตัดสินว่า<em>จะเทรดหรือไม่</em> <em>ทิศทางใด</em> <em>ขนาดเท่าใด</em> และ<em>จะตัดขาดทุนที่ใด</em> ระบบความปลอดภัยตัดสินเพียงว่าคำสั่งนั้น<em>ได้รับอนุญาตหรือไม่</em> โดยทำให้เล็กลงหรือรัดกุมขึ้นได้เท่านั้น ไม่มีทางทำให้ใหญ่ขึ้น",
        "s1": "หนึ่งรอบตั้งแต่ต้นจนจบ",
        "s1_p": "ทำซ้ำตามช่วงเวลาที่กำหนดสำหรับแต่ละสินทรัพย์ที่ถืออยู่ แต่ละขั้นตอนจะผ่านไป หรือจบรอบพร้อมบันทึกเหตุผล",
        "f1_t": "จากการวิเคราะห์สู่คำสั่ง",
        "f1_s": "น้ำเงิน = AI ตัดสิน · ส้ม = การตรวจสอบความปลอดภัย",
        "n1": "ตรวจสถานการณ์", "d1": "ช่วงปกติ หรือช่วงวิกฤต",
        "n2": "วิเคราะห์", "d2": "อ่านเร็ว หรือทีมนักวิเคราะห์ 4 คนเต็มรูปแบบ",
        "n3": "ตัดสินใจ", "d3": "ซื้อ · ขาย · ถือ พร้อมระดับความมั่นใจ",
        "n4": "ออกแบบคำสั่ง", "d4": "ขนาด · จุดตัดขาดทุน · เป้าหมาย ให้เหมาะกับสินทรัพย์นี้",
        "n5": "ตรวจความปลอดภัย", "d5": "ขีดจำกัดความเสี่ยง · เพดานการเปิดสถานะ · ผลตอบแทนต่อความเสี่ยง",
        "n6": "คำสั่ง", "d6": "การจับคู่ พร้อมบันทึกเหตุผล",
        "s2": "ใครตัดสินอะไร",
        "f2_t": "ผู้ตัดสิน", "f2_s": "21 ขั้นตอนในหนึ่งรอบ",
        "lg_ai": "AI ตัดสิน — 6 ขั้น", "lg_code": "ตรวจความปลอดภัย — 14 ขั้น", "lg_ex": "ดำเนินการ — 1",
        "f2_c": "ตัวเลขเพียงอย่างเดียวอาจทำให้เข้าใจผิด 14 ขั้นตอนความปลอดภัยทำได้เพียง<em>ปฏิเสธหรือลดขนาด</em> ไม่มีขั้นใดสร้างการเทรดหรือเลือกทิศทางได้",
        "t_dec": "การตัดสิน", "t_who": "ผู้ตัดสิน", "t_other": "อีกฝ่ายทำอะไรได้",
        "r1": "จะเทรดหรือไม่", "r1o": "ความปลอดภัยยับยั้งได้ แต่เริ่มเองไม่ได้",
        "r2": "ทิศทางใด", "r2o": "ความปลอดภัยไม่เคยเลือกทิศทาง",
        "r3": "ขนาดเท่าใด", "r3o": "ความปลอดภัยลดได้อย่างเดียว — ขีดจำกัด เพดาน ขนาดขั้นต่ำ",
        "r4": "จุดตัดขาดทุนอยู่ที่ใด", "r4o": "ความปลอดภัยบังคับอัตราส่วนผลตอบแทนต่อความเสี่ยงขั้นต่ำ",
        "r5": "เป้าหมายอยู่ที่ใด", "r5o": "ความปลอดภัยผลักออกไกลได้ แต่ดึงเข้าใกล้ไม่ได้",
        "r6": "คำสั่งนี้ได้รับอนุญาตหรือไม่", "r6o": "AI ข้ามขีดจำกัดความเสี่ยงไม่ได้",
        "r7": "ปิดสถานะเมื่อถึงจุดตัดขาดทุน", "r7o": "เป็นหน้าที่ของระบบความปลอดภัยโดยเจตนา — ดูด้านล่าง",
        "s3": "เมื่อใดจึงเรียกทีมวิเคราะห์เต็มรูปแบบ",
        "s3_p": "สัญญาณสี่อย่างสามารถส่งรอบนั้นไปวิเคราะห์เชิงลึก การที่สัญญาณเกิดขึ้นไม่ได้เรียกทีมโดยอัตโนมัติ — <strong>ทีมงานเองเป็นผู้ตัดสินว่ามันสำคัญจริงกับสินทรัพย์นี้หรือไม่</strong>",
        "g1": "ช่วงเหตุการณ์สำคัญ", "g1d": "ใกล้ประกาศตัวเลขเศรษฐกิจสำคัญ",
        "g2": "แรงกระแทกตลาด", "g2d": "ความเคลื่อนไหวผิดปกติพร้อมปริมาณซื้อขายผิดปกติ",
        "g3": "อารมณ์ตลาดสุดขั้ว", "g3d": "ดัชนีความกลัวหรือความโลภอยู่ระดับสุดขั้ว",
        "g4": "ใกล้จุดตัดขาดทุน", "g4d": "สถานะของคุณกำลังเข้าใกล้จุดตัดขาดทุน",
        "s4": "คำสั่งที่ AI เขียน",
        "s4_p": "เดิมระบบใช้จุดตัดขาดทุน 5% และเป้าหมาย 10% เท่ากันทุกสินทรัพย์ ตอนนี้ AI กำหนด<strong>ตามสินทรัพย์นั้น</strong> ตัวอย่างจริง:",
        "th_sym": "สินทรัพย์", "th_vol": "ความผันผวน", "th_stop": "จุดตัดขาดทุนโดย AI", "th_tgt": "เป้าหมายโดย AI", "th_old": "ค่าคงที่เดิม",
        "s4_c": "วันเดียวกัน ทีมเดียวกัน สินทรัพย์ที่ผันผวนสูงได้จุดตัดขาดทุนกว้างขึ้น<strong>เกือบสองเท่า</strong> ค่าคงที่มองทั้งคู่เป็น 5% เท่ากัน",
        "s5": "เมื่ออ่านคำตอบของ AI ไม่ได้",
        "s5_p": "ทุกเส้นทางที่ล้มเหลวจบลงที่<strong>ไม่เปิดสถานะใหม่</strong> ไม่มีการเทรดโดยการเดา",
        "th_case": "สถานการณ์", "th_res": "ผลลัพธ์",
        "c1": "AI ไม่ตอบ", "c1r": "ถือ — กฎไม่สามารถสร้างทิศทางขึ้นมาเองได้",
        "c2": "คำตอบไม่สมบูรณ์", "c2r": "กู้เฉพาะส่วนที่อ่านได้ มิฉะนั้นถือ",
        "c3": "AI ขอไม่กำหนดรายละเอียดคำสั่ง", "c3r": "ใช้ค่าเริ่มต้นของระบบ",
        "c4": "เกินขีดจำกัดความปลอดภัย", "c4r": "ลดลงมาที่ขีดจำกัด หรือปฏิเสธ",
        "c5": "ผลตอบแทนไม่คุ้มความเสี่ยง", "c5r": "ปฏิเสธการเข้า",
        "s6": "ทำไมการปิดสถานะจึงยังเป็นของระบบความปลอดภัย",
        "s6_p": "จุดตัดขาดทุนที่ต้องรอ AI ตอบ จะไม่ทำงานตอนระบบขัดข้อง — ซึ่งเป็นตอนที่จำเป็นที่สุด หลักการสำคัญกำกับเรื่อง<strong>การเปิด</strong>สถานะ นั่นคือการใช้วิจารณญาณ ส่วนการปิดเพื่อจำกัดขาดทุนคือการคำนวณ",
        "s7": "การแจ้งเตือนเฉพาะบุคคล",
        "s7_p": "เหตุการณ์ตลาดคือ<strong>ข้อเท็จจริงเกี่ยวกับตลาด</strong> แต่มันสำคัญหรือไม่คือ<strong>ข้อเท็จจริงเกี่ยวกับคุณ</strong> ทุกการแจ้งเตือนถูกตรวจกับสถานะของคุณก่อนส่ง",
        "a1": "ตรวจจับ", "a1d": "ทุกชั่วโมง ครอบคลุมทุกสินทรัพย์",
        "a2": "ตรวจสอบ", "a2d": "ทิศทางที่ถือ · เลเวอเรจ · ระยะถึงจุดตัดขาดทุน",
        "a3a": "เป็นผลดี", "a3ad": "แจ้งเบา ๆ",
        "a3b": "เป็นผลเสีย", "a3bd": "แจ้งเตือนด่วน",
        "a3c": "ไม่มีผล", "a3cd": "ไม่แจ้งเตือน",
        "s7_c": "หนึ่งเหตุการณ์ สามผลลัพธ์ สมาชิกส่วนใหญ่ไม่ได้รับอะไรเลย ซึ่งถูกต้องแล้ว",
        "s8": "สิ่งที่คุณอาจสังเกตเห็น",
        "th_see": "สิ่งที่อาจสังเกตเห็น", "th_why": "เหตุผล",
        "w1": "บางรอบทำทันที บางรอบใช้เวลานาน", "w1d": "ช่วงปกติใช้เส้นทางเร็ว ช่วงวิกฤตใช้ทีมเต็มรูปแบบ",
        "w2": "สถานะที่กำไรถูกปิดเอง", "w2d": "ระบบปกป้องกำไรล็อกกำไรก่อนที่มันจะหายไป",
        "w3": "สถานะที่ขาดทุนถูกปิดเร็ว", "w3d": "จุดตัดขาดทุนทำงาน — ขาดทุนที่ควบคุมได้แทนขาดทุนก้อนใหญ่",
        "w4": "ข่าวใหญ่แต่ไม่มีการแจ้งเตือน", "w4d": "ตรวจกับสถานะของคุณแล้วไม่มีผลกระทบ นี่คือการทำงานที่ถูกต้อง",
        "w5": "RUN ไม่เคยเปิดการเทรดเลย", "w5d": "ไม่มีอะไรคุ้มต้นทุนการเทรด การไม่เทรดก็เป็นผลลัพธ์ที่ถูกต้อง",
        "safe_t": "ความปลอดภัยมาก่อนเสมอ",
        "safe_b": "AI เป็นผู้เสนอ — ขีดจำกัดความเสี่ยงที่คุณตั้งไว้เป็นผู้ตัดสิน ทุกการกระทำผ่านการตรวจความเสี่ยง ขีดจำกัดสถานะ และจุดตัดขาดทุนของบัญชีคุณ และคุณหยุดทั้งหมดได้ด้วยปุ่มเดียวทุกเมื่อ",
        "mt_note": "เอกสารนี้แปลด้วยเครื่องจากฉบับภาษาอังกฤษ ยังไม่ผ่านการตรวจโดยเจ้าของภาษา",
    },
    "vi": {
        "html_lang": "vi", "font": '"Be Vietnam Pro","Segoe UI"',
        "title": "Hệ thống giao dịch tự động quyết định thế nào",
        "eyebrow": "Sooppiy · Hướng dẫn thành viên",
        "lede": "Điều gì diễn ra trong mỗi chu kỳ, từ phân tích đến lệnh thật — và <strong>phần nào do AI quyết định so với hệ thống an toàn</strong>.",
        "rule_t": "Nguyên tắc cốt lõi",
        "rule_b": "Một lệnh phải do AI quyết định, nếu không thì không được đặt. AI quyết định <em>có giao dịch hay không</em>, <em>theo hướng nào</em>, <em>khối lượng bao nhiêu</em>, và <em>cắt lỗ ở đâu</em>. Hệ thống an toàn chỉ quyết định lệnh đó có được <em>cho phép</em> hay không — nó chỉ có thể làm lệnh nhỏ hơn hoặc chặt hơn, không bao giờ lớn hơn.",
        "s1": "Một chu kỳ từ đầu đến cuối",
        "s1_p": "Lặp lại theo chu kỳ cố định cho từng mã bạn đang nắm giữ. Mỗi bước hoặc đi tiếp, hoặc kết thúc chu kỳ kèm lý do được ghi lại.",
        "f1_t": "Từ phân tích đến lệnh",
        "f1_s": "Xanh = AI quyết định · Cam = kiểm tra an toàn",
        "n1": "Kiểm tra tình huống", "d1": "thời điểm bình thường hay quan trọng",
        "n2": "Phân tích", "d2": "đọc nhanh, hoặc hội đồng 4 chuyên gia đầy đủ",
        "n3": "Quyết định", "d3": "mua · bán · giữ, kèm mức tin cậy",
        "n4": "Thiết kế lệnh", "d4": "khối lượng · cắt lỗ · mục tiêu, theo đúng mã này",
        "n5": "Kiểm tra an toàn", "d5": "giới hạn rủi ro · trần trạng thái · lợi nhuận so với rủi ro",
        "n6": "Lệnh", "d6": "khớp lệnh, ghi kèm lý do",
        "s2": "Ai quyết định điều gì",
        "f2_t": "Chủ thể quyết định", "f2_s": "21 bước trong một chu kỳ",
        "lg_ai": "AI quyết định — 6 bước", "lg_code": "Kiểm tra an toàn — 14 bước", "lg_ex": "Thực thi — 1",
        "f2_c": "Chỉ nhìn con số dễ gây hiểu lầm. 14 bước an toàn chỉ <em>từ chối hoặc thu nhỏ</em>. Không bước nào tạo ra giao dịch hay chọn hướng được.",
        "t_dec": "Quyết định", "t_who": "Chủ thể", "t_other": "Bên còn lại được làm gì",
        "r1": "Có giao dịch hay không", "r1o": "An toàn chỉ phủ quyết, không khởi tạo",
        "r2": "Theo hướng nào", "r2o": "An toàn không bao giờ chọn hướng",
        "r3": "Khối lượng bao nhiêu", "r3o": "An toàn chỉ thu nhỏ — giới hạn, trạng thái, khối lượng tối thiểu",
        "r4": "Cắt lỗ đặt ở đâu", "r4o": "An toàn áp mức sàn lợi nhuận trên rủi ro",
        "r5": "Mục tiêu đặt ở đâu", "r5o": "An toàn có thể đẩy xa hơn, không kéo gần lại",
        "r6": "Lệnh này có được phép", "r6o": "AI không thể vượt giới hạn rủi ro",
        "r7": "Đóng lệnh khi chạm cắt lỗ", "r7o": "Thuộc hệ thống an toàn một cách có chủ đích — xem bên dưới",
        "s3": "Khi nào hội đồng đầy đủ được triệu tập",
        "s3_p": "Bốn tín hiệu có thể đưa chu kỳ vào phân tích sâu. Tín hiệu xuất hiện không tự động triệu tập hội đồng — <strong>chính hội đồng đánh giá liệu nó có thực sự quan trọng với mã này hay không.</strong>",
        "g1": "Cửa sổ sự kiện", "g1d": "sắp công bố số liệu kinh tế quan trọng",
        "g2": "Cú sốc thị trường", "g2d": "biến động bất thường kèm khối lượng bất thường",
        "g3": "Tâm lý cực đoan", "g3d": "chỉ số sợ hãi hoặc tham lam ở mức cực đoan",
        "g4": "Gần mức cắt lỗ", "g4d": "trạng thái của bạn đang tiến gần mức cắt lỗ",
        "s4": "Lệnh do AI soạn",
        "s4_p": "Trước đây hệ thống áp cùng mức cắt lỗ 5% và mục tiêu 10% cho mọi mã. Nay AI định mức <strong>theo từng mã</strong>. Ví dụ thực tế:",
        "th_sym": "Mã", "th_vol": "Biến động", "th_stop": "Cắt lỗ AI", "th_tgt": "Mục tiêu AI", "th_old": "Giá trị cố định cũ",
        "s4_c": "Cùng ngày, cùng hội đồng. Mã biến động mạnh nhận mức cắt lỗ rộng gần <strong>gấp đôi</strong>. Giá trị cố định coi cả hai là 5%.",
        "s5": "Khi không đọc được câu trả lời của AI",
        "s5_p": "Mọi đường lỗi đều kết thúc ở <strong>không mở trạng thái mới</strong>. Không bao giờ giao dịch dựa trên phỏng đoán.",
        "th_case": "Tình huống", "th_res": "Kết quả",
        "c1": "AI không trả lời", "c1r": "Giữ — quy tắc không được tự tạo ra hướng đi",
        "c2": "Câu trả lời không đầy đủ", "c2r": "Khôi phục phần đọc được, nếu không thì giữ",
        "c3": "AI không định rõ thông số lệnh", "c3r": "Áp dụng mặc định của hệ thống",
        "c4": "Vượt giới hạn an toàn", "c4r": "Thu về mức giới hạn, hoặc từ chối",
        "c5": "Lợi nhuận không bù được rủi ro", "c5r": "Từ chối vào lệnh",
        "s6": "Vì sao việc đóng lệnh vẫn thuộc hệ thống an toàn",
        "s6_p": "Một lệnh cắt lỗ phụ thuộc vào việc AI trả lời sẽ không kích hoạt khi hệ thống gián đoạn — đúng lúc cần nhất. Nguyên tắc cốt lõi điều chỉnh việc <strong>mở</strong> trạng thái: đó là phán đoán. Đóng lại để chặn lỗ là phép tính.",
        "s7": "Cảnh báo cá nhân hóa",
        "s7_p": "Một sự kiện thị trường là <strong>sự thật về thị trường</strong>; nó có quan trọng hay không là <strong>sự thật về bạn</strong>. Mọi cảnh báo đều được đối chiếu với trạng thái của chính bạn trước khi gửi.",
        "a1": "Phát hiện", "a1d": "mỗi giờ, trên mọi mã",
        "a2": "Đối chiếu", "a2d": "hướng nắm giữ · đòn bẩy · khoảng cách tới cắt lỗ",
        "a3a": "Có lợi cho bạn", "a3ad": "thông báo nhẹ",
        "a3b": "Bất lợi cho bạn", "a3bd": "cảnh báo khẩn",
        "a3c": "Không ảnh hưởng", "a3cd": "không cảnh báo",
        "s7_c": "Một sự kiện, ba kết quả. Phần lớn thành viên không nhận được gì, và như vậy là đúng.",
        "s8": "Những điều bạn có thể nhận thấy",
        "th_see": "Bạn có thể thấy", "th_why": "Lý do",
        "w1": "Có chu kỳ hành động ngay, có chu kỳ lâu hơn", "w1d": "Thời điểm bình thường đi đường nhanh; thời điểm quan trọng dùng hội đồng đầy đủ",
        "w2": "Một trạng thái đang lãi tự đóng", "w2d": "Bảo vệ lợi nhuận đã chốt lãi trước khi nó trôi mất",
        "w3": "Một trạng thái đang lỗ bị đóng sớm", "w3d": "Cắt lỗ đã kích hoạt — khoản lỗ có kiểm soát thay vì khoản lỗ lớn",
        "w4": "Tin lớn nhưng không có cảnh báo", "w4d": "Đã đối chiếu với trạng thái của bạn và không ảnh hưởng. Đó là hệ thống hoạt động đúng",
        "w5": "Một run chưa từng mở lệnh", "w5d": "Không có gì bù được chi phí giao dịch. Không giao dịch cũng là kết quả hợp lệ",
        "safe_t": "An toàn, luôn luôn",
        "safe_b": "AI đề xuất — giới hạn rủi ro bạn đặt mới là bên quyết định. Mọi hành động đều đi qua kiểm tra rủi ro, giới hạn trạng thái và cắt lỗ của tài khoản bạn, và bạn có thể dừng toàn bộ bằng một nút bất cứ lúc nào.",
        "mt_note": "Tài liệu này được dịch máy từ bản tiếng Anh và chưa qua hiệu đính của người bản ngữ.",
    },
}

# Real prod figures — identical in every language.
ROWS = [("ETHUSDT", "3.4%", "2.80%", "6.50%"), ("KAITOUSDT", "12.8%", "5.50%", "15.00%")]

TPL = """<!doctype html>
<html lang="{html_lang}">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root{{--page:#f9f9f7;--card:#fff;--surf:#f1f0ec;--grid:#e1e0d9;--ink:#0b0b0b;--ink2:#52514e;
 --muted:#7a7975;--ai:#2a78d6;--safe:#eb6834;--go:#1baf7a;--warn:#c88a1a;--bd:rgba(11,11,11,.1)}}
@media (prefers-color-scheme:dark){{:root{{--page:#0d0d0d;--card:#202020;--surf:#1a1a19;--grid:#2c2c2a;
 --ink:#fff;--ink2:#c3c2b7;--muted:#8f8d85;--ai:#3987e5;--safe:#d95926;--go:#199e70;--warn:#e0a53a;
 --bd:rgba(255,255,255,.1)}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--page);color:var(--ink);
 font-family:system-ui,-apple-system,{font},sans-serif;line-height:1.72;font-size:14.5px}}
main{{max-width:880px;margin:0 auto;padding:38px 22px 80px}}
h1{{font-size:26px;line-height:1.3;margin:0 0 6px}}
h2{{font-size:19px;margin:36px 0 8px;padding-top:18px;border-top:1px solid var(--grid)}}
p,li{{color:var(--ink2)}}strong{{color:var(--ink)}}
.eyebrow{{font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);font-weight:700;margin-bottom:7px}}
.lede{{font-size:16px;margin-bottom:22px}}
.rule{{border:1px solid var(--bd);border-left:4px solid var(--ai);background:var(--card);
 border-radius:0 11px 11px 0;padding:15px 18px;margin:16px 0 26px}}
.rule b{{display:block;color:var(--ink);margin-bottom:5px;font-size:14.5px}}
.rule p{{margin:0;font-size:13.8px}}
.fig{{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:18px 20px;margin:16px 0}}
.ft{{font-weight:650;font-size:14px;margin-bottom:2px;color:var(--ink)}}
.fs{{font-size:12.3px;color:var(--muted);margin-bottom:15px}}
.cap{{font-size:12.3px;color:var(--muted);margin:11px 0 0}}
.flow{{display:grid;gap:5px}}
.fr{{display:grid;grid-template-columns:30px 1fr;gap:11px;align-items:stretch}}
.fn{{display:grid;place-items:center;font-size:11.5px;font-weight:700;color:var(--ink2);
 background:var(--surf);border-radius:7px}}
.fb{{border:1.5px solid var(--grid);border-left-width:4px;border-radius:9px;background:var(--page);padding:9px 13px}}
.fb.ai{{border-left-color:var(--ai)}}.fb.sf{{border-left-color:var(--safe)}}
.fb.ex{{border-left-color:var(--go);background:color-mix(in srgb,var(--go) 8%,var(--page))}}
.fb b{{font-size:13.5px;color:var(--ink);display:block}}
.fb span{{font-size:12.3px;color:var(--ink2)}}
.ar{{grid-column:2;color:var(--muted);font-size:12px;line-height:1;padding:1px 0 1px 12px}}
.stack{{display:flex;height:30px;border-radius:6px;overflow:hidden;gap:2px;background:var(--surf)}}
.sg{{display:grid;place-items:center;min-width:28px}}
.sg span{{font-size:12px;font-weight:700;color:#fff;font-variant-numeric:tabular-nums}}
.lgd{{display:flex;flex-wrap:wrap;gap:14px;margin-top:12px;font-size:12.3px;color:var(--ink2)}}
.lgd i{{width:11px;height:11px;border-radius:3px;display:inline-block;margin-right:6px;vertical-align:-1px}}
.trig{{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:9px;margin:12px 0}}
.tg{{background:var(--card);border:1.5px solid var(--warn);border-radius:11px;padding:11px 12px;font-size:12.5px;color:var(--ink2)}}
.tg b{{display:block;color:var(--ink);font-size:13px;margin-bottom:2px}}
.fan{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:9px;margin:12px 0}}
.fan div{{border-radius:10px;border:1.5px solid var(--grid);background:var(--card);padding:10px 12px;font-size:12.3px;color:var(--ink2)}}
.fan b{{display:block;color:var(--ink);font-size:12.8px;margin-bottom:2px}}
.fan .g{{border-color:var(--go)}}.fan .b{{border-color:var(--warn)}}.fan .m{{opacity:.72;border-style:dashed}}
.sw{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:13.2px;margin:8px 0}}
th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid var(--grid);color:var(--ink2);vertical-align:top}}
th{{font-size:11px;letter-spacing:.04em;color:var(--muted);text-transform:uppercase;white-space:nowrap}}
td strong{{color:var(--ink)}}
.pill{{display:inline-block;font-size:10.5px;font-weight:700;padding:2px 8px;border-radius:999px;white-space:nowrap}}
.p-ai{{background:color-mix(in srgb,var(--ai) 15%,transparent);color:color-mix(in srgb,var(--ai) 62%,var(--ink));
 border:1px solid color-mix(in srgb,var(--ai) 42%,transparent)}}
.p-sf{{background:color-mix(in srgb,var(--safe) 15%,transparent);color:color-mix(in srgb,var(--safe) 62%,var(--ink));
 border:1px solid color-mix(in srgb,var(--safe) 42%,transparent)}}
.note{{border-left:3px solid var(--go);background:var(--card);border-radius:0 10px 10px 0;
 padding:11px 14px;margin:16px 0;font-size:13.2px;color:var(--ink2)}}
.note b{{color:var(--ink)}}
.mt{{margin-top:30px;padding-top:14px;border-top:1px solid var(--grid);font-size:11.5px;color:var(--muted)}}
@media (max-width:620px){{.fan{{grid-template-columns:1fr}}.fr{{grid-template-columns:26px 1fr;gap:8px}}}}
</style></head>
<body><main>

<div class="eyebrow">{eyebrow}</div>
<h1>{title}</h1>
<p class="lede">{lede}</p>

<div class="rule"><b>{rule_t}</b><p>{rule_b}</p></div>

<h2>{s1}</h2>
<p>{s1_p}</p>
<div class="fig">
  <div class="ft">{f1_t}</div><div class="fs">{f1_s}</div>
  <div class="flow">
    <div class="fr"><div class="fn">1</div><div class="fb ai"><b>{n1}</b><span>{d1}</span></div></div>
    <div class="ar">↓</div>
    <div class="fr"><div class="fn">2</div><div class="fb ai"><b>{n2}</b><span>{d2}</span></div></div>
    <div class="ar">↓</div>
    <div class="fr"><div class="fn">3</div><div class="fb ai"><b>{n3}</b><span>{d3}</span></div></div>
    <div class="ar">↓</div>
    <div class="fr"><div class="fn">4</div><div class="fb ai"><b>{n4}</b><span>{d4}</span></div></div>
    <div class="ar">↓</div>
    <div class="fr"><div class="fn">5</div><div class="fb sf"><b>{n5}</b><span>{d5}</span></div></div>
    <div class="ar">↓</div>
    <div class="fr"><div class="fn">6</div><div class="fb ex"><b>{n6}</b><span>{d6}</span></div></div>
  </div>
</div>

<h2>{s2}</h2>
<div class="fig">
  <div class="ft">{f2_t}</div><div class="fs">{f2_s}</div>
  <div class="stack">
    <div class="sg" style="width:28.6%;background:var(--ai)"><span>6</span></div>
    <div class="sg" style="width:66.6%;background:var(--safe)"><span>14</span></div>
    <div class="sg" style="width:4.8%;background:color-mix(in srgb,var(--go) 78%,#000)"><span>1</span></div>
  </div>
  <div class="lgd">
    <span><i style="background:var(--ai)"></i>{lg_ai}</span>
    <span><i style="background:var(--safe)"></i>{lg_code}</span>
    <span><i style="background:color-mix(in srgb,var(--go) 78%,#000)"></i>{lg_ex}</span>
  </div>
  <p class="cap">{f2_c}</p>
</div>
<div class="sw"><table>
<thead><tr><th>{t_dec}</th><th>{t_who}</th><th>{t_other}</th></tr></thead>
<tbody>
<tr><td><strong>{r1}</strong></td><td><span class="pill p-ai">AI</span></td><td>{r1o}</td></tr>
<tr><td><strong>{r2}</strong></td><td><span class="pill p-ai">AI</span></td><td>{r2o}</td></tr>
<tr><td><strong>{r3}</strong></td><td><span class="pill p-ai">AI</span></td><td>{r3o}</td></tr>
<tr><td><strong>{r4}</strong></td><td><span class="pill p-ai">AI</span></td><td>{r4o}</td></tr>
<tr><td><strong>{r5}</strong></td><td><span class="pill p-ai">AI</span></td><td>{r5o}</td></tr>
<tr><td>{r6}</td><td><span class="pill p-sf">SAFETY</span></td><td>{r6o}</td></tr>
<tr><td>{r7}</td><td><span class="pill p-sf">SAFETY</span></td><td>{r7o}</td></tr>
</tbody></table></div>

<h2>{s3}</h2>
<p>{s3_p}</p>
<div class="trig">
  <div class="tg"><b>📅 {g1}</b>{g1d}</div>
  <div class="tg"><b>⚡ {g2}</b>{g2d}</div>
  <div class="tg"><b>🎭 {g3}</b>{g3d}</div>
  <div class="tg"><b>🎯 {g4}</b>{g4d}</div>
</div>

<h2>{s4}</h2>
<p>{s4_p}</p>
<div class="fig"><div class="sw"><table>
<thead><tr><th>{th_sym}</th><th>{th_vol}</th><th>{th_stop}</th><th>{th_tgt}</th><th>{th_old}</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<p class="cap">{s4_c}</p></div>

<h2>{s5}</h2>
<p>{s5_p}</p>
<div class="sw"><table>
<thead><tr><th>{th_case}</th><th>{th_res}</th></tr></thead>
<tbody>
<tr><td>{c1}</td><td><strong>{c1r}</strong></td></tr>
<tr><td>{c2}</td><td>{c2r}</td></tr>
<tr><td>{c3}</td><td>{c3r}</td></tr>
<tr><td>{c4}</td><td>{c4r}</td></tr>
<tr><td>{c5}</td><td><strong>{c5r}</strong></td></tr>
</tbody></table></div>

<h2>{s6}</h2>
<p>{s6_p}</p>

<h2>{s7}</h2>
<p>{s7_p}</p>
<div class="fig">
  <div class="flow">
    <div class="fr"><div class="fn">1</div><div class="fb ai"><b>{a1}</b><span>{a1d}</span></div></div>
    <div class="ar">↓</div>
    <div class="fr"><div class="fn">2</div><div class="fb ai"><b>{a2}</b><span>{a2d}</span></div></div>
  </div>
  <div class="fan">
    <div class="g"><b>{a3a}</b>{a3ad}</div>
    <div class="b"><b>{a3b}</b>{a3bd}</div>
    <div class="m"><b>{a3c}</b>{a3cd}</div>
  </div>
  <p class="cap">{s7_c}</p>
</div>

<h2>{s8}</h2>
<div class="sw"><table>
<thead><tr><th>{th_see}</th><th>{th_why}</th></tr></thead>
<tbody>
<tr><td><strong>{w1}</strong></td><td>{w1d}</td></tr>
<tr><td><strong>{w2}</strong></td><td>{w2d}</td></tr>
<tr><td><strong>{w3}</strong></td><td>{w3d}</td></tr>
<tr><td><strong>{w4}</strong></td><td>{w4d}</td></tr>
<tr><td><strong>{w5}</strong></td><td>{w5d}</td></tr>
</tbody></table></div>

<div class="note"><b>{safe_t}</b> {safe_b}</div>
<p class="mt">{mt_note}</p>

</main></body></html>
"""


def build() -> None:
    for lang in LANGS:
        s = dict(S[lang])
        s["rows"] = "".join(
            f"<tr><td><strong>{sym}</strong></td><td>{vol}</td><td><strong>{st}</strong></td>"
            f"<td><strong>{tg}</strong></td><td>5% / 10%</td></tr>"
            for sym, vol, st, tg in ROWS)
        path = OUT / f"decisions-guide-{lang}.html"
        path.write_text(TPL.format(**s), encoding="utf-8")
        print(f"wrote {path.name} ({len(path.read_text(encoding='utf-8')):,} bytes)")


if __name__ == "__main__":
    build()
