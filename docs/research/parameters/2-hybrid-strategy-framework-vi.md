<!-- machine-translated from research/parameters/2-hybrid-strategy-framework.md by docs/design/_gen_doc_translations.py — pending native review -->
# Khung Framework Kết Hợp: Mẫu Hình Biểu Đồ × Tâm Lý Con Người
## Khung Giao Dịch Kết Hợp Mẫu Hình Biểu Đồ × Tâm Lý Con Người

**Xây dựng từ hai vòng nghiên cứu chuyên sâu đã được kiểm chứng (200+ agent, kiểm tra thực tế từ nguồn gốc chính) · Tháng 7 năm 2026**
**⚠️ Đây là khung giáo dục, không phải lời khuyên đầu tư. Kỳ vọng thực tế: độ chính xác định hướng 50–55% — lợi thế đến từ sự hội tụ tín hiệu + quản lý rủi ro, không phải từ bất kỳ tín hiệu đơn lẻ nào.**

<div style="border-left:4px solid #2a78d6;background:rgba(42,120,214,.07);padding:12px 16px;border-radius:0 10px 10px 0;margin:14px 0;font-size:13px;line-height:1.6">
<b>Khung framework này áp dụng vào việc triển khai crypto như thế nào.</b> Danh sách kiểm tra này nêu ra chiến lược nghiên cứu; hệ thống đang vận hành sẽ điều chỉnh nó cho phù hợp với crypto.
<b>VIX → chỉ số Sợ hãi &amp; Tham lam của crypto (F&amp;G)</b>, một thang đo đảo ngược — hoảng loạn là khi <b>F&amp;G &lt; 20</b> (không phải VIX &gt; 30), bình ổn là khi <b>F&amp;G &gt; 30</b>; crypto không có chỉ số VIX (<code>regime.py</code>, <code>strategy_config.py</code>).
<b>Các mẫu hình biểu đồ có tên gọi (đáy đôi, H&amp;S) → một điểm số kỹ thuật tổng hợp</b> (RSI · MA · funding · basis · long/short) được xác nhận bởi khối lượng giao dịch — không tồn tại bộ phát hiện mẫu hình nến (<code>confluence.py</code> B3/S3).
<b>Tâm lý dựa trên lợi nhuận qua đêm → xu hướng đám đông trên StockTwits</b> (B4). Các nhãn B1–B6 / S1–S6 chính là các nhãn điều kiện thực tế của công cụ.
</div>

---

## 1. Nguyên tắc cốt lõi mà nghiên cứu đã chứng minh

Hai sự thật đã được kiểm chứng chi phối toàn bộ thiết kế:

1. **Các mẫu hình biểu đồ mang tính thông tin nhưng không sinh lời nếu đứng một mình** (Lo–Mamaysky–Wang 2000; Savin 2007). Chúng cho bạn biết *điều gì đó* đang diễn ra, với lợi thế tối đa 53–54% — không bao giờ sử dụng chúng như một tín hiệu kích hoạt độc lập.
2. **Tâm lý chi phối thị trường nhưng chỉ có thể giao dịch được ở những thời điểm cực đoan và những thời điểm cụ thể** (tâm lý qua đêm ~6bp/SD; độ chính xác của tâm lý 50–55%; hoảng loạn/hưng phấn là nơi các hiệu ứng hành vi tập trung nhiều nhất).

Vậy công thức kết hợp là: **tâm lý quyết định CHẾ ĐỘ (khi nào, và mức độ rủi ro bao nhiêu); biểu đồ quyết định ĐIỂM KÍCH HOẠT (cái gì và ở mức giá nào); khối lượng + tâm lý thị trường XÁC NHẬN; biến động quyết định QUY MÔ.**

Các tín hiệu mang tính cộng dồn, không phải tuyệt đối: mỗi điều kiện được thỏa mãn sẽ cộng thêm một điểm; bạn chỉ hành động khi có sự đồng thuận (4+ trong 6), bởi vì một tín hiệu 53% khi được xếp chồng với các tín hiệu 53% độc lập khác chính là cách các hệ thống thực tế vượt qua ngưỡng 55%.

---

## 2. Bốn tầng quyết định

### TẦNG 1 — Bộ lọc chế độ tâm lý (인간 심리 = 국면 판단) — *"Tôi có nên giao dịch hay không, và ở chế độ nào?"*
| Đầu vào | Trạng thái | Chế độ |
|---|---|---|
| VIX / mức độ sợ hãi | < 20 bình lặng | **Chế độ xu hướng** — theo biểu đồ |
| | 20–30 lo lắng | Giảm quy mô 50%, siết chặt điểm dừng lỗ |
| | > 30 hoảng loạn | **Chế độ ngược dòng** — bỏ qua các mẫu hình biểu đồ giảm giá, chuẩn bị mua theo hồi quy về trung bình |
| Lịch sự kiện (FOMC, CPI, bầu cử) | trong vòng ±1 ngày | **Không vào lệnh mới**; giữ nguyên hoặc phòng hộ |
| Tin tức sốc chiến tranh / chính sách | 1–3 ngày đầu | Không bao giờ mua nhịp bật tăng đầu tiên; chờ tín hiệu ổn định |
| Tông cảm xúc mạng xã hội/tin tức | hưng phấn tột độ | Bật cảnh báo bán ngược dòng |
| | sợ hãi tột độ | Bật cảnh báo mua ngược dòng |

### TẦNG 2 — Bộ máy xác định hướng (biểu đồ: CÁI GÌ) — các yếu tố dự báo mạnh nhất đã được kiểm chứng
- Động lượng 12 tháng (bỏ qua tháng gần nhất) dương → thiên hướng mua / âm → thiên hướng bán
- Giá so với MA 200 ngày (trạng thái golden-cross) → hướng xu hướng
- Đảo chiều ngắn hạn 1 tháng → thời điểm giao dịch ngược xu hướng trong khuôn khổ thiên hướng chính

### TẦNG 3 — Kích hoạt & xác nhận (biểu đồ + tâm lý kết hợp: KHI NÀO)
Một mẫu hình chỉ được tính khi **đã hoàn tất VÀ được khối lượng xác nhận VÀ tâm lý thị trường không mâu thuẫn**:
- Kích hoạt tăng giá: đáy đôi / phá vỡ H&S-đảo ngược **+ khối lượng tăng + tâm lý qua đêm không tiêu cực**
- Kích hoạt giảm giá: đỉnh đôi / hoàn tất mẫu hình H&S **+ khối lượng tăng + tông tin tức xấu đi**
- Không có khối lượng = không giao dịch (các đặc trưng khối lượng được xác minh là thiết yếu; Dinh & Kwon 2018)

### LỚP 4 — Kích thước & thoát lệnh (rủi ro: BAO NHIÊU)
- Kích thước vị thế = ngân sách rủi ro ÷ biến động (đã xác minh: biến động là một trong 4 yếu tố dự báo hàng đầu và là đầu vào cho việc tính kích thước)
- Đặt stop cứng dưới điểm phá vỡ mô hình; kéo theo MA
- Stop theo thời gian: nếu luận điểm không hiệu quả trong N ngày → thoát lệnh (độ chính xác của bạn ~55%, nên các lệnh thua phải được cắt nhanh)

---

## 3. Danh sách kiểm tra MUA (hội tụ ≥ 4 trên 6 → mua)

| # | Tín hiệu | Phía nguồn | Cơ sở đã xác minh |
|---|---|---|---|
| B1 | Giá trên MA 200 ngày / trạng thái golden-cross | Biểu đồ | Brock 1992: các ngày có tín hiệu mua tăng +12% hàng năm |
| B2 | Động lượng 12-1 dương | Biểu đồ | GKX 2020: yếu tố dự báo ML #1 |
| B3 | Mô hình tăng giá hoàn thành CÙNG với khối lượng | Biểu đồ | LMW 2000 mang tính thông tin + khối lượng thiết yếu |
| B4 | Tâm lý qua đêm/tin tức tích cực hoặc đang hồi phục | Tâm lý | Fed: ~6bp/SD ngày kế tiếp |
| B5 | Đỉnh sợ hãi đang giảm dần (VIX giảm từ đỉnh >30) | Tâm lý | Tài liệu về phản ứng thái quá/hồi quy về giá trị trung bình |
| B6 | Không có FOMC/CPI/sự kiện lớn nào trong vòng 24 giờ | Tâm lý | Thời điểm rủi ro sự kiện |

**Trường hợp đặc biệt ngược dòng (mua khi hoảng loạn):** VIX > 30 + tâm lý ở mức sợ hãi cực độ + giá đang ổn định trên MA ngắn hạn + đỉnh điểm khối lượng đã qua → mua theo hồi quy về giá trị trung bình với nửa kích thước vị thế. (Đây là trường hợp "tham lam khi người khác sợ hãi" được hệ thống hóa.)

## 4. Danh sách kiểm tra BÁN (hội tụ ≥ 4 trên 6 → bán/tránh)

| # | Tín hiệu | Phía nguồn |
|---|---|---|
| S1 | Giá dưới MA 200 ngày / trạng thái death-cross | Biểu đồ |
| S2 | Động lượng chuyển sang âm | Biểu đồ |
| S3 | Mô hình giảm giá (double top / H&S) hoàn thành cùng khối lượng | Biểu đồ |
| S4 | Tâm lý hưng phấn cực độ (mọi người đều lạc quan, không khí cuồng nhiệt kiểu meme-stock) | Tâm lý — ngược dòng |
| S5 | Cú sốc chính sách/địa chính trị tiêu cực chưa được giải quyết | Tâm lý |
| S6 | Đạt mức stop-loss / mục tiêu biến động | Rủi ro (luôn được ưu tiên hơn tất cả) |

## 5. Ma trận kịch bản WHEN × WHAT

| Kịch bản (trạng thái tâm lý thị trường) | Bên chiếm ưu thế | Hành động |
|---|---|---|
| Xu hướng tăng ổn định, tâm lý tích cực | Charts | Theo xu hướng: mua khi giá điều chỉnh về MA kèm khối lượng; nắm giữ |
| Xu hướng giảm ổn định | Charts | Đứng ngoài hoặc thiên về short; không bắt đáy khi chưa có tín hiệu hoảng loạn Layer-1 |
| Hoảng loạn (tin tức chiến tranh, VIX >30, sợ hãi cực độ) | Psychology | Ngày 1–3: không làm gì. Sau đó mua ngược dòng khi có trigger ổn định (B5) |
| Hưng phấn tột độ (giá tăng parabol + ai cũng lạc quan) | Psychology | Chốt lời khi giá còn mạnh; trigger bán S4; không bao giờ mua thêm |
| Khung thời gian FOMC/CPI/bầu cử | Psychology | Đứng ngoài/không vào lệnh mới; tiếp tục vào ngày hôm sau |
| Breakout theo pattern nhưng không có khối lượng | Neither | Rủi ro bẫy giá — bỏ qua (hầu hết breakout giả nằm ở đây) |
| Chart tăng giá NHƯNG tâm lý sụp đổ do tin tức thực | Psychology vetoes | Bỏ qua giao dịch — chế độ tin tức thắng chart đã cũ |
| Tâm lý nhiễu, không cực đoan, chart rõ ràng | Charts | Giao dịch theo chart; tâm lý chỉ là yếu tố phân định |

## 6. Quản lý kỳ vọng (số liệu đã kiểm chứng)

- Độ chính xác định hướng nên kỳ vọng: **50–55%**, không phải 80%.
- Lợi thế kiểu golden-cross: khoảng 4–5 điểm phần trăm tỷ lệ thắng so với tung đồng xu, trước khi trừ chi phí.
- Lợi thế từ tâm lý: vài điểm cơ bản mỗi ngày, chỉ thực sự có ý nghĩa ở mức cực đoan và qua đêm.
- Lợi thế cộng dồn đến từ: sự hội tụ (xếp chồng nhiều lợi thế yếu độc lập), cắt lỗ nhanh, định cỡ theo biến động, và bỏ qua các khung thời gian có sự kiện — không phải từ thiên tài dự đoán.
- Mọi lợi thế đã công bố đều suy giảm theo thời gian. Hãy backtest, paper-trade, và xác thực lại out-of-sample trước khi mạo hiểm tiền thật.

## 7. Nguồn tham khảo chính
Gu–Kelly–Xiu (2020) RFS · Lo–Mamaysky–Wang (2000) JF · Brock et al. (1992) JF · Savin et al. (2007) JFEc · Park & Irwin (2007) JES · Sullivan et al. (1999) JF · Bollen et al. (2011) + Lachanski & Pav (2017) replication · Greyling & Rossouw (2025) CEPR · Fed FEDS 2023-034 · Dinh & Kwon (2018) · Prata et al. (2024).
