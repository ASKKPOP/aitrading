<!-- machine-translated from research/parameters/2-hybrid-strategy-framework.md by docs/design/_gen_doc_translations.py — pending native review -->
# Khung Kết Hợp: Trộn Mẫu Hình Biểu Đồ × Tâm Lý Con Người
## Một khung giao dịch kết hợp mẫu hình biểu đồ với tâm lý con người

**Được xây dựng từ hai vòng nghiên cứu chuyên sâu đã được xác minh (hơn 200 agent, kiểm chứng thực tế từ nguồn gốc) · Tháng 7 năm 2026**
**⚠️ Khung giáo dục, không phải lời khuyên đầu tư. Kỳ vọng thực tế: độ chính xác định hướng 50–55% — lợi thế đến từ sự hội tụ + quản lý rủi ro, không phải từ bất kỳ tín hiệu đơn lẻ nào.**

<div style="border-left:4px solid #2a78d6;background:rgba(42,120,214,.07);padding:12px 16px;border-radius:0 10px 10px 0;margin:14px 0;font-size:13px;line-height:1.6">
<b>Khung này ánh xạ vào việc triển khai crypto như thế nào.</b> Danh sách kiểm tra này nêu chiến lược nghiên cứu; hệ thống đang vận hành sẽ thích ứng nó cho crypto.
<b>VIX → chỉ số Sợ hãi &amp; Tham lam (F&amp;G) của crypto</b>, một thang đo đảo ngược — hoảng loạn là <b>F&amp;G &lt; 20</b> (không phải VIX &gt; 30), bình tĩnh là <b>F&amp;G &gt; 30</b>; không có VIX cho crypto (<code>regime.py</code>, <code>strategy_config.py</code>).
<b>Các mẫu hình biểu đồ có tên (đáy đôi, H&amp;S) → điểm kỹ thuật tổng hợp</b> (RSI · MA · funding · basis · long/short) được xác nhận bởi khối lượng — không có bộ phát hiện mẫu hình nến nào tồn tại (<code>confluence.py</code> B3/S3).
<b>Tâm lý lợi nhuận qua đêm → xu hướng đám đông StockTwits</b> (B4). Các tên B1–B6 / S1–S6 là các nhãn điều kiện động cơ thực sự.
</div>

---

## 1. Nguyên tắc cốt lõi mà nghiên cứu đã chứng minh

Hai sự thật đã được xác minh chi phối toàn bộ thiết kế:

1. **Các mẫu hình biểu đồ mang tính thông tin nhưng không sinh lời khi đứng một mình** (Lo–Mamaysky–Wang 2000; Savin 2007). Chúng cho bạn biết *điều gì đó* đang xảy ra, với lợi thế tối đa 53–54% — không bao giờ sử dụng chúng như một tín hiệu kích hoạt độc lập.
2. **Tâm lý chi phối thị trường nhưng chỉ có thể giao dịch được ở các điểm cực trị và vào những thời điểm cụ thể** (tâm lý thị trường qua đêm ~6bp/SD; độ chính xác của tâm lý thị trường 50–55%; hoảng loạn/hưng phấn là nơi các hiệu ứng hành vi tập trung).

Vậy sự kết hợp là: **tâm lý quyết định CHẾ ĐỘ (khi nào, và mức độ rủi ro bao nhiêu); biểu đồ quyết định ĐIỂM KÍCH HOẠT (cái gì và ở mức giá nào); khối lượng + tâm lý XÁC NHẬN; biến động quyết định KÍCH THƯỚC.**

Các tín hiệu mang tính cộng dồn, không phải tuyệt đối: mỗi điều kiện được thỏa mãn sẽ cộng thêm một điểm; bạn chỉ hành động khi có sự đồng thuận (4+ trên 6), vì một tín hiệu 53% khi kết hợp với các tín hiệu độc lập 53% khác là cách các hệ thống thực tế vượt qua mức 55%.

---

## 2. Chồng quyết định bốn lớp

### LỚP 1 — Bộ lọc chế độ tâm lý (tâm lý con người = quyết định chế độ) — *"Tôi có nên giao dịch không, và ở chế độ nào?"*
| Đầu vào | Trạng thái | Chế độ |
|---|---|---|
| VIX / mức độ sợ hãi | < 20 bình lặng | **Chế độ xu hướng** — theo biểu đồ |
| | 20–30 lo lắng | Giảm 50% kích thước, siết chặt điểm dừng lỗ |
| | > 30 hoảng loạn | **Chế độ ngược dòng** — bỏ qua các mẫu hình biểu đồ giảm giá, chuẩn bị mua theo hồi quy về trung bình |
| Lịch sự kiện (FOMC, CPI, bầu cử) | trong khoảng ±1 ngày | **Không vào lệnh mới**; giữ hoặc phòng ngừa |
| Tin tức chiến tranh / chính sách gây chấn động | 1–3 ngày đầu | Không bao giờ mua ở lần bật giá đầu tiên; chờ tín hiệu ổn định |
| Sắc thái tâm lý mạng xã hội/tin tức | hưng phấn cực độ | Bật cảnh báo bán ngược dòng |
| | sợ hãi cực độ | Bật cảnh báo mua ngược dòng |

### LỚP 2 — Bộ máy xác định hướng (biểu đồ: CÁI GÌ) — các yếu tố dự báo mạnh nhất đã được kiểm chứng
- Động lượng 12 tháng (bỏ qua tháng gần nhất) dương → xu hướng mua / âm → xu hướng bán
- Giá so với MA 200 ngày (trạng thái golden-cross) → hướng xu hướng
- Đảo chiều ngắn hạn 1 tháng → thời điểm giao dịch ngược xu hướng trong phạm vi xu hướng chính

### LỚP 3 — Điểm kích hoạt & xác nhận (biểu đồ + tâm lý cùng nhau: KHI NÀO)
Một mẫu hình chỉ được tính khi **đã hoàn thành VÀ được xác nhận bởi khối lượng VÀ tâm lý không mâu thuẫn**:
- Tín hiệu tăng: breakout từ mô hình đáy đôi / H&S ngược **+ khối lượng tăng + tâm lý qua đêm không âm**
- Tín hiệu giảm: hoàn thành mô hình hai đỉnh / H&S **+ khối lượng tăng + xu hướng tin tức xấu đi**
- Không có khối lượng = không giao dịch (volume features đã được xác minh là thiết yếu; Dinh & Kwon 2018)

### LỚP 4 — Kích thước & thoát lệnh (rủi ro: BAO NHIÊU)
- Kích thước vị thế = ngân sách rủi ro ÷ độ biến động (đã xác minh: volatility là một trong 4 yếu tố dự báo hàng đầu và là đầu vào cho việc định cỡ)
- Đặt stop cứng dưới điểm phá vỡ mô hình; theo sát bằng MA
- Time stop: nếu luận điểm không đúng sau N ngày → thoát lệnh (độ chính xác của bạn là ~55%, nên các lệnh thua phải được cắt nhanh)

---

## 3. Danh sách kiểm tra MUA (đồng thuận ≥ 4/6 → mua)

| # | Tín hiệu | Nguồn | Cơ sở đã xác minh |
|---|---|---|---|
| B1 | Giá trên MA 200 ngày / trạng thái golden-cross | Chart | Brock 1992: các ngày có tín hiệu mua +12% hàng năm |
| B2 | Động lượng 12-1 dương | Chart | GKX 2020: yếu tố dự báo ML #1 |
| B3 | Mô hình tăng giá hoàn thành CÙNG VỚI khối lượng | Chart | LMW 2000 có tính thông tin + khối lượng thiết yếu |
| B4 | Tâm lý qua đêm/tin tức tích cực hoặc đang hồi phục | Psychology | Fed: ~6bp/SD ngày kế tiếp |
| B5 | Đỉnh sợ hãi đang giảm (VIX giảm từ đỉnh >30) | Psychology | Tài liệu về phản ứng thái quá/hồi quy về trung bình |
| B6 | Không có sự kiện FOMC/CPI/sự kiện lớn trong vòng 24h | Psychology | Thời điểm rủi ro sự kiện |

**Trường hợp đặc biệt ngược dòng (mua khi hoảng loạn):** VIX > 30 + tâm lý ở mức sợ hãi cực độ + giá ổn định trên MA ngắn hạn + đỉnh điểm khối lượng đã qua → mua theo hồi quy về trung bình với nửa kích thước. (Đây là trường hợp "tham lam khi người khác sợ hãi", được hệ thống hóa.)

## 4. Danh sách kiểm tra BÁN (đồng thuận ≥ 4/6 → bán/tránh)

| # | Tín hiệu | Nguồn |
|---|---|---|
| S1 | Giá dưới MA 200 ngày / trạng thái death-cross | Chart |
| S2 | Động lượng chuyển sang âm | Chart |
| S3 | Mô hình giảm giá (double top / H&S) hoàn thành cùng khối lượng | Chart |
| S4 | Cảm xúc hưng phấn cực độ (mọi người đều lạc quan, xu hướng cuồng nhiệt cổ phiếu meme) | Tâm lý — trái chiều |
| S5 | Cú sốc chính sách/địa chính trị tiêu cực chưa được giải quyết | Tâm lý |
| S6 | Chạm mức cắt lỗ / mục tiêu biến động | Rủi ro (luôn ghi đè lên mọi thứ) |

## 5. Ma trận kịch bản WHEN × WHAT

| Kịch bản (trạng thái tâm lý thị trường) | Bên chi phối | Hành động |
|---|---|---|
| Xu hướng tăng ổn định, tâm lý tích cực | Biểu đồ | Theo xu hướng: mua khi giá điều chỉnh về MA kèm khối lượng; giữ vị thế |
| Xu hướng giảm ổn định | Biểu đồ | Đứng ngoài hoặc thiên về bán khống; không bắt đáy khi chưa có tín hiệu hoảng loạn Layer-1 |
| Hoảng loạn (tin chiến tranh, VIX >30, sợ hãi cực độ) | Tâm lý | Ngày 1–3: không làm gì. Sau đó mua trái chiều khi có tín hiệu ổn định (B5) |
| Hưng phấn (giá tăng parabol + mọi người đều lạc quan) | Tâm lý | Chốt lời khi giá mạnh; tín hiệu S4 kích hoạt bán; không bao giờ mua thêm |
| Khung thời gian FOMC/CPI/bầu cử | Tâm lý | Không vào lệnh mới; tiếp tục vào ngày hôm sau |
| Đột phá mô hình không có khối lượng | Không bên nào | Rủi ro bẫy — bỏ qua (hầu hết các đột phá giả xảy ra ở đây) |
| Biểu đồ tăng NHƯNG tâm lý sụp đổ do tin tức thực | Tâm lý phủ quyết | Bỏ qua giao dịch — chế độ tin tức thắng biểu đồ cũ |
| Tâm lý nhiễu, không cực đoan, biểu đồ rõ ràng | Biểu đồ | Giao dịch theo biểu đồ; tâm lý chỉ là yếu tố phân định |

## 6. Quản lý kỳ vọng (số liệu đã kiểm chứng)

- Độ chính xác định hướng kỳ vọng: **50–55%**, không phải 80%.
- Loại lợi thế golden-cross: khoảng 4–5 điểm phần trăm tỷ lệ thắng so với tung đồng xu, trước khi trừ chi phí.
- Lợi thế tâm lý: vài điểm cơ bản mỗi ngày, chỉ thực sự có giá trị ở các điểm cực đoan và qua đêm.
- Lợi thế cộng dồn đến từ: sự hội tụ (xếp chồng các lợi thế yếu độc lập), cắt lỗ nhanh, định cỡ vị thế theo biến động, và bỏ qua các khung thời gian sự kiện — không phải từ thiên tài dự đoán.
- Mọi lợi thế đã công bố đều suy giảm. Hãy kiểm tra lại bằng dữ liệu quá khứ, giao dịch thử, và xác thực lại ngoài mẫu trước khi mạo hiểm tiền thật.

## 7. Nguồn tham khảo chính
Gu–Kelly–Xiu (2020) RFS · Lo–Mamaysky–Wang (2000) JF · Brock et al. (1992) JF · Savin et al. (2007) JFEc · Park & Irwin (2007) JES · Sullivan et al. (1999) JF · Bollen et al. (2011) + Lachanski & Pav (2017) replication · Greyling & Rossouw (2025) CEPR · Fed FEDS 2023-034 · Dinh & Kwon (2018) · Prata et al. (2024).
