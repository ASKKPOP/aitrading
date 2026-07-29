<!-- machine-translated from research/parameters/3-phase4-backtest-report.md by docs/design/_gen_doc_translations.py — pending native review -->
# Backtest chiến lược Phase-4 — kết quả go/no-go

**Ngày:** 2026-07-16 · **Kết luận: INSUFFICIENT_EVIDENCE → gói flip KHÔNG được triển khai. Tất cả các execution gate vẫn mặc định tắt.**
**Trình chạy:** `service/server/run_phase4_backtest.py` · số liệu thô: [phase4-backtest-result.json](phase4-backtest-result.json) · engine: `backtest_strategy.py` (đã unit-tested; hai lần chạy độc lập giống hệt nhau từng byte).
**Kế hoạch:** [docs/plan/04-ai-model-parameter-upgrade.md](../../plan/04-ai-model-parameter-upgrade.md) §Phase 4 — các tiêu chí đã được đăng ký trước khi các cửa sổ OOS được mở.

## 0. Tóm tắt

<!-- Phần này được viết bằng tiếng Hàn và chưa được dịch trong tài liệu ENGLISH
     cho đến 2026-07-29, nên độc giả tiếng Anh đã phải xem khoảng 309 ký tự
     tiếng Hàn ở đây. Văn bản tiếng Hàn nằm đúng chỗ của nó, trong
     3-phase4-backtest-report-ko.md; đây là phiên bản tiếng Anh tương ứng. -->

Xét theo các tiêu chí đã đăng ký trước, kết quả là **INSUFFICIENT_EVIDENCE** — gói flip (các execution gate bật theo mặc định) **không** được triển khai. Cấu hình deployment-faithful (≥4/6) chỉ tạo ra **38** giao dịch OOS trong suốt sáu năm walk-forward so với ngưỡng 400 giao dịch, và cả cận dưới Wilson 90% của tỷ lệ thắng 36.8% (0.28) lẫn cận dưới profit-factor theo bootstrap (0.64) đều không đạt. Khi nới lỏng xuống hàng sensitivity (≥3), số lượng tăng lên 237, nhưng cận dưới PF vẫn là 0.88 — dưới 1.0, nên khả năng sinh lời chưa được xác lập về mặt thống kê.

**Điều đã phát huy hiệu quả:** bộ khung quản trị rủi ro hoạt động đúng như nghiên cứu đã hứa hẹn — mức sụt giảm tối đa (drawdown) của tài sản tệ nhất là **2.6%** so với mức -38% đến -47% của chiến lược mua-và-giữ trong cùng khoảng thời gian, 53% số lệnh thoát được thực hiện bởi lệnh trailing stop (để lệnh thắng chạy tiếp), và vốn được bảo toàn bằng cách cắt lỗ chứ không phải bằng cách dự đoán. Lăng kính thống kê của bảng xác minh đã dự báo trước kết quả này: quá ít giao dịch.

**Tiếp theo:** mọi tính năng đều đã sẵn sàng triển khai ở chế độ hiển thị / tư vấn / tùy chọn tham gia. Đánh giá lại hệ thống sáu điều kiện bao gồm B4 live-forward khi dữ liệu viễn trắc thực (confluence vectors, factor snapshots) đã tích lũy đủ. Các ngưỡng này thuộc về nghiên cứu — không thuộc về sản xuất.

## 1. Thiết lập đã đăng ký trước (không thay đổi sau khi thấy kết quả)

- **Hàng chính:** các giá trị mặc định trung thực với triển khai (`confluence_min=4`, `volume_confirm_min=1.5`), không bao giờ được tinh chỉnh — không có việc dò xét dữ liệu (snooping) do cấu trúc.
- **Hàng walk-forward:** cố định, 4 folds, thanh lọc (purge) 14 ngày, lưới 6 cấu hình (đã báo cáo), được tinh chỉnh trên tập huấn luyện theo hệ số lợi nhuận gộp (pooled profit factor) (≥30 giao dịch), cố định trên tập kiểm tra.
- **Hàng độ nhạy:** `confluence_min=3` cố định (B4 vô hiệu về mặt lịch sử → chỉ 5 trong 6 điều kiện có thể đạt được; do đó cổng live *nghiêm ngặt hơn* trong backtest so với khi triển khai).
- **Tiêu chí:** ≥400 giao dịch OOS gộp, nếu không thì INSUFFICIENT_EVIDENCE · cận dưới Wilson 90% của tỷ lệ thắng > 0.50 · cận dưới bootstrap 90% của hệ số lợi nhuận > 1.0 · mức sụt giảm tối đa (DD) của tài sản tệ nhất ≤ 30%.
- **Tính trung thực về phạm vi:** B4 vô hiệu trong suốt; B3 suy giảm thành MA/RSI/volume; B5 = chỉ nhánh F&G (kho lưu trữ đầy đủ từ 2018+, thêm một ngày độ trễ); S5 vô hiệu; sự kiện = lịch 2019–2025 đã được xác minh hai nguồn. Tài sản: các thanh BTC/ETH từ 2019-01 (tín hiệu ≈2020-02 sau 400 thanh khởi động), SOL từ 2020-04 (tín hiệu ≈2021-05). Phí 0.1%/lệnh + 0.05% trượt giá; tín hiệu đóng-t được khớp lệnh tại mở t+1.

## 2. Kết quả

### Chính (trung thực với triển khai ≥4/6) — gộp trên 4 fold OOS × 3 tài sản

| Chỉ số | Giá trị | Tiêu chí | Đạt? |
|---|---|---|---|
| Giao dịch OOS | **38** | ≥ 400 | ❌ (ngưỡng bằng chứng tối thiểu) |
| Tỷ lệ thắng | 36.8% (14/38) | Wilson90 LB > 0.50 → LB = **0.276** | ❌ |
| Hệ số lợi nhuận | 1.13 | bootstrap90 LB > 1.0 → LB = **0.644** | ❌ |
| DD tối đa của tài sản xấu nhất | **2.63%** | ≤ 30% | ✅ |

Theo từng fold: F1 (2021-07→2022-12, gấu): 19 giao dịch, PF 1.82 · F2: 6 giao dịch, PF 0.69 · F3: 7 giao dịch, PF 6.53 · F4 (2025-07→2026-07, gấu): 6 giao dịch, PF 0.0.
Kết hợp thoát lệnh: trail_stop 20 (53%) · stop_loss 15 · time_stop 3 — đúng với hồ sơ theo xu hướng (trend-following) mà nghiên cứu đề xuất (thắng một phần nhỏ giao dịch, để các lệnh thắng chạy dài: mức thắng trung bình ≫ mức thua trung bình chính là yếu tố đẩy PF vượt trên 1 ở tỷ lệ thắng 37%).

### Độ nhạy (≥3 trong số 5 có sẵn)

237 giao dịch · thắng 37.1% (Wilson LB 0.332) · PF 1.15 (bootstrap LB **0.884**) · DD xấu nhất 8.97%. Nhiều bằng chứng hơn, cùng một kết luận: lợi nhuận theo ước lượng điểm, không phân biệt được về mặt thống kê so với hòa vốn.

### Walk-forward (điều chỉnh theo từng fold, 6 cấu hình — đã tính đến snooping)

Mọi fold đều được điều chỉnh về `confluence_min=3`; PF kiểm tra: F1 1.46, F2 1.82, F3 0.69, F4 0.79. Lợi thế phụ thuộc vào chế độ thị trường (regime) và không duy trì qua các fold — phù hợp với cảnh báo "lợi thế đã công bố sẽ suy giảm" của nghiên cứu.

### Tương quan điều kiện (góc nhìn thống kê đã dự đoán điều này)

Mức đồng thuận hàng ngày B1↔B2 **0.709** (cả hai đều là thước đo xu hướng), B1↔B3 0.52, B2↔B3 0.40. Sáu điều kiện không độc lập với nhau; phép tính "chồng các lợi thế 53% độc lập" không áp dụng đúng như bề ngoài.

### Điều gì THỰC SỰ hiệu quả

Trong giai đoạn thị trường giảm F4, chiến lược lỗ ≈1.1–1.7% mỗi tài sản, trong khi mua-và-giữ lỗ **−21% (ETH), −38% (BTC), −47% (SOL)**. Mức sụt giảm tối đa 2–9% so với mức sụt giảm lịch sử 60%+ của B&H. Mức độ tiếp xúc thị trường 3–6% số ngày. **Giá trị đã được xác minh của hệ thống là bảo toàn vốn thông qua lọc chế độ thị trường (regime filtering) và chuỗi thoát lệnh (exit stack) — đúng như tuyên bố của nghiên cứu rằng "lợi thế đến từ quản lý rủi ro, không phải dự đoán." Điều CHƯA được xác minh là khả năng sinh lời độc lập.**

## 3. Quyết định (theo quy tắc đã đăng ký trước)

1. **Không thay đổi.** `CONFLUENCE_GATE_ENABLED`, `REGIME_FILTER_ENABLED`, `VOL_SIZING_ENABLED` vẫn **mặc định tắt**. Không triển khai việc di chuyển preset/`min_confidence`. Câu văn của chính kế hoạch chi phối điều này: *"Nếu dưới [tiêu chí], các ngưỡng confluence sẽ trở về nghiên cứu, không phải sản xuất."*
2. **Những gì vẫn được triển khai (đã được gộp, không thay đổi hành vi thực thi):** hiển thị confluence + API agent, khuyến nghị chế độ thị trường (regime advisory) + tile, telemetry (vector confluence theo từng quyết định, factor snapshots), các bản sửa lỗi an toàn (breaker tripped_by/expires_at, never-loosen SL/TP, first_opened_at, risk-direction gating, sửa lỗi put_risk_limits), các chỉ số backtester đã được sửa, và bộ công cụ thoát lệnh tùy chọn theo từng agent (trailing/time stops — từng agent riêng lẻ có thể bật chúng; đây là công cụ quản lý rủi ro vị thế, không phải tuyên bố về khả năng sinh lời).
3. **Lộ trình đánh giá lại:** live-forward. Telemetry Giai đoạn 1 tích lũy đầy đủ vector 6 điều kiện (bao gồm B4) với mỗi quyết định; factor snapshots ghi lại funding/OI/L-S/StockTwits. Khi có ≥400 quyết định trực tiếp đạt chất lượng gated (hoặc một backtest trong tương lai có thể bao gồm các điều kiện còn thiếu), chạy lại các tiêu chí. Bảng calibration (tỷ lệ trúng theo số lượng confluence, Wilson CIs) sẽ tự xây dựng từ telemetry.
4. **Công việc ngưỡng quay trở lại nghiên cứu:** câu hỏi mở thú vị từ dữ liệu là liệu *chỉ riêng chuỗi thoát lệnh* (trailing stop + time stop + veto theo chế độ thị trường) trên một tín hiệu vào lệnh đơn giản hơn có mang lại giá trị hay không — cổng vào lệnh hội tụ ở mức ≥4/5 nghiêm ngặt đến mức chỉ giao dịch 6×/năm trên 3 tài sản.

*Không phải lời khuyên đầu tư. Nền tảng mô phỏng. Các lợi thế lịch sử suy giảm theo thời gian; những con số này mô tả một lần kiểm thử ngược (backtest) trong giới hạn phạm vi đã được ghi lại.*
