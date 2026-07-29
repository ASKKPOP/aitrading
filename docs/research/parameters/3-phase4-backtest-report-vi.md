<!-- machine-translated from research/parameters/3-phase4-backtest-report.md by docs/design/_gen_doc_translations.py — pending native review -->
# Backtest chiến lược Phase-4 — kết quả go/no-go

**Ngày:** 2026-07-16 · **Kết luận: INSUFFICIENT_EVIDENCE → gói flip KHÔNG được triển khai. Tất cả các execution gate vẫn giữ mặc định tắt.**
**Trình chạy:** `service/server/run_phase4_backtest.py` · số liệu thô: [phase4-backtest-result.json](phase4-backtest-result.json) · engine: `backtest_strategy.py` (đã unit-test; hai lần chạy độc lập giống hệt nhau từng byte).
**Kế hoạch:** [docs/plan/04-ai-model-parameter-upgrade.md](../../plan/04-ai-model-parameter-upgrade.md) §Phase 4 — các tiêu chí đã được đăng ký trước khi các cửa sổ OOS được mở.

## 0. 한국어 요약

사전 등록 기준으로 평가한 결과 **증거 불충분(INSUFFICIENT_EVIDENCE)** — 플립 패키지(실행 게이트 기본 활성화)는 배포하지 않습니다. 배포-충실 설정(≥4/6)은 6년 워크포워드에서 OOS 거래가 **38건**뿐(기준 400건)이고, 승률 36.8%의 Wilson 90% 하한(0.28)과 PF 부트스트랩 하한(0.64) 모두 기준 미달. 민감도 행(≥3)은 237건으로 늘지만 PF 하한 0.88로 여전히 1.0 미만 — 수익성이 통계적으로 입증되지 않음.

**Phát hiện tích cực:** Risk stack hoạt động đúng như nghiên cứu đã hứa hẹn — mức sụt giảm tối đa tệ nhất của tài sản là **2.6%** (B&H là −38%~−47% trong cùng giai đoạn), 53% số lần thoát lệnh là trailing stop (để lệnh thắng chạy), hệ thống bảo toàn vốn bằng cách chặn lỗ chứ không phải bằng dự đoán. Dự đoán của lăng kính thống kê trong bảng xác thực (thiếu số lượng giao dịch) đã đúng chính xác.

**Bước tiếp theo:** Tất cả các tính năng đã sẵn sàng triển khai ở chế độ hiển thị/tư vấn/opt-in. Khi dữ liệu telemetry trực tiếp (vector confluence, factor snapshot) được tích lũy, hệ thống 6 điều kiện bao gồm B4 sẽ được đánh giá lại theo live-forward. Ngưỡng giá trị quay về nghiên cứu — không phải production.

## 1. Thiết lập đăng ký trước (không thay đổi sau khi thấy kết quả)

- **Hàng chính:** các giá trị mặc định trung thực với triển khai (`confluence_min=4`, `volume_confirm_min=1.5`), không bao giờ được tinh chỉnh — không có snooping theo thiết kế.
- **Hàng walk-forward:** có neo (anchored), 4 folds, purge 14 ngày, lưới 6 cấu hình (được báo cáo), được tinh chỉnh trên tập train theo profit factor gộp (≥30 giao dịch), cố định trên tập test.
- **Hàng độ nhạy:** `confluence_min=3` cố định (B4 về mặt lịch sử là null → chỉ có thể đạt 5 trên 6 điều kiện; do đó cổng live *nghiêm ngặt hơn* trong backtest so với khi triển khai).
- **Tiêu chí:** ≥400 giao dịch OOS gộp, nếu không thì INSUFFICIENT_EVIDENCE · cận dưới Wilson 90% của tỷ lệ thắng > 0.50 · cận dưới bootstrap 90% của hệ số lợi nhuận > 1.0 · DD tối đa của tài sản tệ nhất ≤ 30%.
- **Tính trung thực về phạm vi:** B4 null trong suốt; B3 giảm cấp xuống MA/RSI/volume; B5 = chỉ nhánh F&G (kho lưu trữ đầy đủ từ 2018+, thêm một ngày độ trễ); S5 null; sự kiện = lịch 2019–2025 đã được xác minh từ hai nguồn. Tài sản: các nến BTC/ETH từ 2019-01 (tín hiệu ≈2020-02 sau 400 nến khởi động), SOL từ 2020-04 (tín hiệu ≈2021-05). Phí 0.1%/lệnh + 0.05% trượt giá; tín hiệu tại đóng nến t được khớp lệnh tại mở nến t+1.

## 2. Kết quả

### Chính (đúng-với-triển khai thực tế ≥4/6) — gộp trên 4 kỳ OOS × 3 tài sản

| Chỉ số | Giá trị | Tiêu chí | Đạt? |
|---|---|---|---|
| Giao dịch OOS | **38** | ≥ 400 | ❌ (ngưỡng bằng chứng) |
| Tỷ lệ thắng | 36.8% (14/38) | Wilson90 LB > 0.50 → LB = **0.276** | ❌ |
| Hệ số lợi nhuận | 1.13 | bootstrap90 LB > 1.0 → LB = **0.644** | ❌ |
| DD tối đa của tài sản tệ nhất | **2.63%** | ≤ 30% | ✅ |

Theo từng kỳ: F1 (2021-07→2022-12, giá xuống): 19 giao dịch, PF 1.82 · F2: 6 giao dịch, PF 0.69 · F3: 7 giao dịch, PF 6.53 · F4 (2025-07→2026-07, giá xuống): 6 giao dịch, PF 0.0.
Cơ cấu thoát lệnh: trail_stop 20 (53%) · stop_loss 15 · time_stop 3 — đúng hồ sơ theo xu hướng mà nghiên cứu đề ra (thắng một tỷ lệ nhỏ giao dịch, để các lệnh thắng chạy dài: mức thắng trung bình ≫ mức thua trung bình chính là yếu tố đẩy PF vượt trên 1 ở tỷ lệ thắng 37%).

### Độ nhạy (≥3 trong số 5 có sẵn)

237 giao dịch · thắng 37.1% (Wilson LB 0.332) · PF 1.15 (bootstrap LB **0.884**) · DD tệ nhất 8.97%. Nhiều bằng chứng hơn, kết luận vẫn vậy: khả năng sinh lời theo ước tính điểm, không thể phân biệt về mặt thống kê so với hòa vốn.

### Walk-forward (tinh chỉnh theo từng kỳ, 6 cấu hình — đã tính đến snooping)

Mỗi fold được tinh chỉnh với `confluence_min=3`; PF kiểm thử: F1 1.46, F2 1.82, F3 0.69, F4 0.79. Edge phụ thuộc vào regime và không duy trì ổn định qua các fold — nhất quán với cảnh báo "published edges decay" của nghiên cứu.

### Tương quan điều kiện (thấu kính thống kê đã dự đoán điều này)

Mức đồng thuận hàng ngày B1↔B2 **0.709** (cả hai đều là chỉ số xu hướng), B1↔B3 0.52, B2↔B3 0.40. Sáu điều kiện này không độc lập; phép tính số học "stack independent 53% edges" không áp dụng đúng theo nghĩa đen.

### Điều GÌ đã thực sự hiệu quả

Trong giai đoạn thị trường giảm F4, chiến lược lỗ ≈1.1–1.7% mỗi tài sản trong khi buy-and-hold lỗ **−21% (ETH), −38% (BTC), −47% (SOL)**. Drawdown tối đa 2–9% so với drawdown lịch sử hơn 60% của B&H. Mức độ tiếp xúc 3–6% số ngày. **Giá trị đã được xác thực của hệ thống là bảo toàn vốn thông qua bộ lọc regime và chuỗi thoát lệnh — đúng như tuyên bố của nghiên cứu rằng "edge đến từ quản lý rủi ro, không phải dự đoán." Điều KHÔNG được xác thực là khả năng sinh lời độc lập.**

## 3. Quyết định (theo quy tắc đã đăng ký trước)

1. **Không đảo chiều.** `CONFLUENCE_GATE_ENABLED`, `REGIME_FILTER_ENABLED`, `VOL_SIZING_ENABLED` vẫn **mặc định tắt**. Không triển khai việc di chuyển preset/`min_confidence`. Câu văn của chính kế hoạch này chi phối: *"Nếu dưới [tiêu chí], các ngưỡng confluence sẽ quay trở lại nghiên cứu, không phải sản xuất."*
2. **Những gì vẫn được triển khai (đã hợp nhất, không thay đổi hành vi thực thi):** hiển thị confluence + agent API, tư vấn regime + tile, telemetry (vector confluence theo từng quyết định, ảnh chụp nhanh yếu tố), các bản sửa lỗi an toàn (breaker tripped_by/expires_at, never-loosen SL/TP, first_opened_at, kiểm soát hướng rủi ro, sửa lỗi put_risk_limits), các chỉ số backtester đã được sửa, và bộ công cụ thoát lệnh tùy chọn theo từng agent (trailing/time stops — từng agent riêng lẻ có thể bật chúng; đây là công cụ quản lý rủi ro theo vị thế, không phải tuyên bố về khả năng sinh lời).
3. **Đường hướng đánh giá lại:** live-forward. Telemetry Giai đoạn 1 tích lũy đầy đủ vector 6 điều kiện (bao gồm B4) với mỗi quyết định; các factor snapshot ghi lại funding/OI/L-S/StockTwits. Khi có ≥400 quyết định live đạt gated-quality (hoặc một backtest trong tương lai có thể bao gồm các điều kiện còn thiếu), chạy lại các tiêu chí. Bảng hiệu chỉnh (hit rate theo confluence count, Wilson CIs) tự xây dựng từ telemetry.
4. **Công việc về ngưỡng quay trở lại nghiên cứu:** câu hỏi mở thú vị từ dữ liệu là liệu *chỉ riêng exit stack* (trail + time stop + regime veto) trên một tín hiệu entry đơn giản hơn có mang lại giá trị hay không — confluence entry gate ở ≥4/5 quá nghiêm ngặt đến mức chỉ giao dịch 6 lần/năm trên 3 tài sản.

*Không phải lời khuyên đầu tư. Nền tảng mô phỏng. Các edge lịch sử sẽ suy giảm; các con số này mô tả một backtest trong giới hạn phạm vi đã ghi nhận.*
