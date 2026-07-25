# Translation review — Vietnamese Tiếng Việt

Machine-generated notification strings for Sooppiy, pending your review. For each row, check the translation against the English. **To correct**: write the fixed text in the **Your correction** column (leave blank if the translation is fine).

Rules for the reviewer:
- Keep every `{placeholder}` exactly as-is (same name, curly braces) — they're filled with live data (symbols, numbers). You may move a placeholder for natural word order.
- ⚠️ rows are terms the translator flagged as uncertain — please pay extra attention.

## Alert messages (26)

| msg_id | Field | English | Current translation | Your correction |
|---|---|---|---|---|
| `breaker` | title | Circuit breaker HALT ({scope}) | Ngắt mạch giao dịch — DỪNG ({scope}) |  |
| `breaker` | body | Trading halted: {reason} | Đã dừng giao dịch: {reason} |  |
| `position_closed` | title | {trigger_label} — {symbol} | {trigger_label} — {symbol} |  |
| `position_closed` | body | Watcher closed {symbol} ({market}) at ${price} | Bộ theo dõi đã đóng {symbol} ({market}) tại ${price} |  |
| `watch` | title | Watch: {name} | Theo dõi: {name} |  |
| `watch` | body | {metric}{where} is {value}{unit} ({comparator} your {threshold}{unit} threshold) | {metric}{where} hiện là {value}{unit} ({comparator} ngưỡng {threshold}{unit} của bạn) |  |
| `run_report` | title | Run #{run_id} {symbol} P&L digest | Tóm tắt lãi/lỗ Run #{run_id} {symbol} |  |
| `run_report` | body | Run #{run_id} {symbol} ({market}) — period {period_start} → {period_end}: P&L ${pnl}, {trades} trade(s). Status: {status}. | Run #{run_id} {symbol} ({market}) — kỳ {period_start} → {period_end}: Lãi/lỗ ${pnl}, {trades} lệnh. Trạng thái: {status}. |  |
| `run_threshold_loss` | title | Run #{run_id} down {loss_pct}% | Run #{run_id} giảm {loss_pct}% |  |
| `run_threshold_loss` | body | {symbol} run P&L ${total} crossed -{loss_pct}% of ${base}. | Lãi/lỗ run {symbol} ${total} đã vượt ngưỡng −{loss_pct}% của ${base}. |  |
| `run_threshold_profit` | title | Run #{run_id} up {profit_pct}% | Run #{run_id} tăng {profit_pct}% |  |
| `run_threshold_profit` | body | {symbol} run P&L ${total} crossed +{profit_pct}% of ${base}. | Lãi/lỗ run {symbol} ${total} đã vượt ngưỡng +{profit_pct}% của ${base}. |  |
| `gateway_down_live_order_failed` | title | Live order did not reach your broker | Lệnh live chưa đến được sàn môi giới của bạn |  |
| `gateway_down_live_order_failed` | body | {symbol}: {reason} | {symbol}: {reason} |  |
| `automation_trade_executed` | title | {action_upper} {symbol} | {action_upper} {symbol} |  |
| `automation_trade_executed` | body | Automation executed {action} {qty} {symbol} @ ${entry} (confidence {confidence}) | Tự động hóa đã thực hiện {action} {qty} {symbol} @ ${entry} (độ tin cậy {confidence}) |  |
| `order_drift_cancelled_rejected` | title | Broker fill differs from platform record | Khớp lệnh của sàn khác với ghi nhận trên nền tảng |  |
| `order_drift_cancelled_rejected` | body | {symbol}: your {side} order was {final} by the broker AFTER submission — the platform recorded it at the requested size ({requested}). Review the position on your broker and correct manually if needed. | {symbol}: lệnh {side} của bạn đã bị {final} bởi sàn môi giới SAU KHI gửi — nền tảng vẫn ghi nhận theo khối lượng yêu cầu ({requested}). Vui lòng kiểm tra vị thế trên sàn môi giới và tự điều chỉnh nếu cần. |  |
| `order_drift_partial_fill` | title | Broker fill differs from platform record | Khớp lệnh của sàn khác với ghi nhận trên nền tảng |  |
| `order_drift_partial_fill` | body | {symbol}: broker confirmed {filled_txt} of the requested {requested} {side} — the platform ledger recorded the requested size. Review and correct manually. | {symbol}: sàn môi giới xác nhận khớp {filled_txt} trên tổng {requested} {side} yêu cầu — sổ lệnh của nền tảng vẫn ghi nhận theo khối lượng yêu cầu. Vui lòng kiểm tra và tự điều chỉnh. |  |
| `gateway_down_ibkr_session` | title | Your IBKR gateway session is down | Phiên gateway IBKR của bạn đã ngắt kết nối |  |
| `gateway_down_ibkr_session` | body | {detail} — live and shadow IBKR orders will not fill until you log in to the Client Portal Gateway again. | {detail} — các lệnh IBKR live và shadow sẽ không được khớp cho đến khi bạn đăng nhập lại vào Client Portal Gateway. |  |
| `run_dup_key` | title | Run #{run_id} halted: duplicate active run | Run #{run_id} đã dừng: trùng run đang hoạt động |  |
| `run_dup_key` | body | Another run with the same settings already owns {symbol} ({market}) for this agent, so this one was halted before it could race the same signal. | Một run khác với cùng cấu hình đã đang quản lý {symbol} ({market}) cho agent này, nên run này bị dừng trước khi có thể tranh chấp cùng tín hiệu. |  |
| `run_armed_timeout` | title | Run #{run_id} timed out while armed | Run #{run_id} hết hạn khi đang chờ kích hoạt |  |
| `run_armed_timeout` | body | Start condition for {symbol} never fired within {hours}h — the run was stopped. | Điều kiện khởi động cho {symbol} không được kích hoạt trong vòng {hours}h — run đã bị dừng. |  |
| `run_stop_eval_failed` | title | Run #{run_id} stopped: cannot evaluate stops | Run #{run_id} đã dừng: không thể đánh giá điểm dừng |  |
| `run_stop_eval_failed` | body | {failures} consecutive stop-evaluation failures ({exc}) — stopping for safety. | {failures} lần đánh giá điểm dừng thất bại liên tiếp ({exc}) — dừng lại để đảm bảo an toàn. |  |
| `run_stop_eval_paused` | title | Run #{run_id} paused: stop check failed | Run #{run_id} tạm dừng: kiểm tra điểm dừng thất bại |  |
| `run_stop_eval_paused` | body | Stop-condition evaluation failed ({exc}); entries are paused until evaluation recovers. | Đánh giá điều kiện dừng thất bại ({exc}); các lệnh vào mới bị tạm dừng cho đến khi việc đánh giá hoạt động trở lại. |  |
| `run_stop_event` | title | Run #{run_id} stop event: {reason} | Run #{run_id} sự kiện dừng: {reason} |  |
| `run_stop_event` | body | {symbol} ({market}) hit {reason} — {outcome} | {symbol} ({market}) đã chạm {reason} — {outcome} |  |
| `run_goal_restart` | title | Run #{run_id} reached its goal — restarted as #{new_run_id} | Run #{run_id} đã đạt mục tiêu — khởi động lại thành #{new_run_id} |  |
| `run_goal_restart` | body | {symbol} ({market}) hit {reason}; a new run with the same settings is live. | {symbol} ({market}) đã chạm {reason}; một run mới với cùng cấu hình đã được kích hoạt. |  |
| `run_positions_held` | title | Run #{run_id} stopped with positions held | Run #{run_id} đã dừng nhưng vẫn còn giữ vị thế |  |
| `run_positions_held` | body | Flatten stayed blocked ({why}) past {minutes}min — the position remains open under the SL/TP watcher. | Việc đóng vị thế vẫn bị chặn ({why}) quá {minutes} phút — vị thế vẫn mở dưới sự theo dõi của SL/TP watcher. |  |
| `run_infeasible` | title | Run #{run_id} paused: cannot fund trades | Run #{run_id} tạm dừng: không đủ vốn để giao dịch |  |
| `run_infeasible` | body | {count} consecutive cycles with insufficient cash for the configured max bet — paused until funds or settings change. | {count} chu kỳ liên tiếp không đủ tiền mặt cho mức đặt cược tối đa đã cấu hình — tạm dừng cho đến khi có thêm vốn hoặc thay đổi cài đặt. |  |
| `run_sub_lapsed` | title | Run #{run_id} paused: subscription expired | Run #{run_id} tạm dừng: gói đăng ký đã hết hạn |  |
| `run_sub_lapsed` | body | Your plan lapsed, so the run was paused (positions and stops stay managed). Renew to resume. | Gói của bạn đã hết hạn nên run bị tạm dừng (vị thế và điểm dừng vẫn được quản lý). Gia hạn để tiếp tục. |  |
| `run_trade_executed` | title | {action_upper} {symbol} | {action_upper} {symbol} |  |
| `run_trade_executed` | body | Run #{run_id} executed {action} {qty} {symbol} @ ${entry} (confidence {confidence}) | Run #{run_id} đã thực hiện {action} {qty} {symbol} @ ${entry} (độ tin cậy {confidence}) |  |
| `fleet_watchdog_eval_failed` | title | Fleet #{fleet_id}: equity evaluation failing | Fleet #{fleet_id}: đánh giá vốn chủ sở hữu thất bại |  |
| `fleet_watchdog_eval_failed` | body | Marked-equity evaluation has failed on stale prices for {fails} consecutive passes — new entries are paused. | Đánh giá vốn theo giá thị trường thất bại do giá dữ liệu cũ trong {fails} lần liên tiếp — các lệnh vào mới bị tạm dừng. |  |
| `fleet_watchdog_stalled` | title | Fleet #{fleet_id}: supervision stalled | Fleet #{fleet_id}: giám sát bị gián đoạn |  |
| `fleet_watchdog_stalled` | body | The fleet supervisor has not run for 3+ ticks — drawdown rails may be dark. Check the worker. | Bộ giám sát fleet đã không chạy trong 3+ chu kỳ — các giới hạn drawdown có thể không hoạt động. Vui lòng kiểm tra worker. |  |
| `fleet_breaker` | title | Fleet #{fleet_id} STOPPED at −{loss_pct}% | Fleet #{fleet_id} ĐÃ DỪNG tại −{loss_pct}% |  |
| `fleet_breaker` | body | Your Full Auto fleet crossed the −{stop_loss_pct}% stop rail. Every position is being closed. This stop fired at the first check observing the breach; the final loss may exceed the threshold. | Fleet Full Auto của bạn đã vượt ngưỡng dừng −{stop_loss_pct}%. Mọi vị thế đang được đóng. Lệnh dừng này được kích hoạt ngay tại lần kiểm tra đầu tiên phát hiện vi phạm; khoản lỗ cuối cùng có thể vượt ngưỡng này. |  |
| `fleet_drawdown_warning` | title | Fleet #{fleet_id} down {loss_pct}% — paused | Fleet #{fleet_id} giảm {loss_pct}% — đã tạm dừng |  |
| `fleet_drawdown_warning` | body | Your Full Auto fleet has lost {loss_pct}% of its budget. New entries are paused; open positions and their stop-losses remain active. If you resume trading from here, continuing is your responsibility. The fleet stops everything automatically at −{stop_loss_pct}%. | Fleet Full Auto của bạn đã lỗ {loss_pct}% ngân sách. Các lệnh vào mới bị tạm dừng; vị thế đang mở và điểm dừng lỗ của chúng vẫn hoạt động. Nếu bạn tiếp tục giao dịch từ đây, trách nhiệm thuộc về bạn. Fleet sẽ tự động dừng toàn bộ tại −{stop_loss_pct}%. |  |
| `fleet_churn` | title | Fleet #{fleet_id}: high replacement churn | Fleet #{fleet_id}: tỷ lệ thay thế thành viên cao |  |
| `fleet_churn` | body | {n} member replacements today — the market may be chopping your strategies out. Consider pausing the fleet. | {n} lượt thay thế thành viên hôm nay — thị trường có thể đang loại bỏ các chiến lược của bạn. Cân nhắc tạm dừng fleet. |  |

## Inline enum terms (tokens)

| Family | Key | English | Current translation | Your correction |
|---|---|---|---|---|
| comparator | `above` | above | trên |  |
| comparator | `below` | below | dưới |  |
| outcome | `flatten` | flattening position. | đang đóng vị thế. |  |
| outcome | `hold` | holding position under the SL/TP watcher. | đang giữ vị thế dưới sự theo dõi của SL/TP watcher. |  |
| trigger_label | `stop_loss` | stop loss | Cắt lỗ |  |
| trigger_label | `take_profit` | take profit | Chốt lời |  |
| trigger_label | `time_stop` | time stop | Dừng theo thời gian |  |
| action | `buy` | buy | mua |  |
| action | `sell` | sell | bán |  |
| action | `short` | short | bán khống |  |
| action | `cover` ⚠️ | cover | mua bù |  |
| action_upper | `BUY` | BUY | MUA |  |
| action_upper | `SELL` | SELL | BÁN |  |
| action_upper | `SHORT` | SHORT | BÁN KHỐNG |  |
| action_upper | `COVER` | COVER | MUA BÙ |  |
| side | `buy` | buy | mua |  |
| side | `sell` | sell | bán |  |
| side | `short` | short | bán khống |  |
| side | `cover` ⚠️ | cover | mua bù |  |
| final | `cancelled` | cancelled | đã hủy |  |
| final | `rejected` | rejected | bị từ chối |  |
| status | `armed` ⚠️ | armed | chờ kích hoạt |  |
| status | `running` | running | đang chạy |  |
| status | `paused` | paused | tạm dừng |  |
| status | `stopping` | stopping | đang dừng |  |
| status | `stopped` | stopped | đã dừng |  |

## Verification email

| Part | English | Current translation | Your correction |
|---|---|---|---|
| subject | Your Sooppiy verification code | Mã xác minh Sooppiy của bạn |  |
| html | <p>Your verification code is: <strong>{code}</strong></p><p>It expires in 5 minutes. Do not share it.</p> | <p>Mã xác minh của bạn là: <strong>{code}</strong></p><p>Mã sẽ hết hạn sau 5 phút. Vui lòng không chia sẻ mã này.</p> |  |

_(Keep the `<p>`/`<strong>` tags and `{code}` in the html.)_