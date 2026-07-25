# Translation review — Thai ภาษาไทย

Machine-generated notification strings for Sooppiy, pending your review. For each row, check the translation against the English. **To correct**: write the fixed text in the **Your correction** column (leave blank if the translation is fine).

Rules for the reviewer:
- Keep every `{placeholder}` exactly as-is (same name, curly braces) — they're filled with live data (symbols, numbers). You may move a placeholder for natural word order.
- ⚠️ rows are terms the translator flagged as uncertain — please pay extra attention.

## Alert messages (26)

| msg_id | Field | English | Current translation | Your correction |
|---|---|---|---|---|
| `breaker` | title | Circuit breaker HALT ({scope}) | เซอร์กิตเบรกเกอร์: หยุดการเทรด ({scope}) |  |
| `breaker` | body | Trading halted: {reason} | การเทรดถูกระงับ: {reason} |  |
| `position_closed` | title | {trigger_label} — {symbol} | {trigger_label} — {symbol} |  |
| `position_closed` | body | Watcher closed {symbol} ({market}) at ${price} | ระบบเฝ้าระวังปิดสถานะ {symbol} ({market}) ที่ราคา ${price} |  |
| `watch` | title | Watch: {name} | เฝ้าระวัง: {name} |  |
| `watch` | body | {metric}{where} is {value}{unit} ({comparator} your {threshold}{unit} threshold) | {metric}{where} อยู่ที่ {value}{unit} ({comparator}เกณฑ์ {threshold}{unit} ของคุณ) |  |
| `run_report` | title | Run #{run_id} {symbol} P&L digest | รัน #{run_id} {symbol} สรุปกำไรขาดทุน |  |
| `run_report` | body | Run #{run_id} {symbol} ({market}) — period {period_start} → {period_end}: P&L ${pnl}, {trades} trade(s). Status: {status}. | รัน #{run_id} {symbol} ({market}) — ช่วงเวลา {period_start} → {period_end}: กำไรขาดทุน ${pnl}, {trades} รายการเทรด สถานะ: {status} |  |
| `run_threshold_loss` | title | Run #{run_id} down {loss_pct}% | รัน #{run_id} ขาดทุน {loss_pct}% |  |
| `run_threshold_loss` | body | {symbol} run P&L ${total} crossed -{loss_pct}% of ${base}. | กำไรขาดทุนของรัน {symbol} ${total} ทะลุ -{loss_pct}% ของ ${base} |  |
| `run_threshold_profit` | title | Run #{run_id} up {profit_pct}% | รัน #{run_id} กำไร {profit_pct}% |  |
| `run_threshold_profit` | body | {symbol} run P&L ${total} crossed +{profit_pct}% of ${base}. | กำไรขาดทุนของรัน {symbol} ${total} ทะลุ +{profit_pct}% ของ ${base} |  |
| `gateway_down_live_order_failed` | title | Live order did not reach your broker | คำสั่งซื้อขายจริงไม่ถึงโบรกเกอร์ของคุณ |  |
| `gateway_down_live_order_failed` | body | {symbol}: {reason} | {symbol}: {reason} |  |
| `automation_trade_executed` | title | {action_upper} {symbol} | {action_upper} {symbol} |  |
| `automation_trade_executed` | body | Automation executed {action} {qty} {symbol} @ ${entry} (confidence {confidence}) | ระบบอัตโนมัติดำเนินการ {action} {qty} {symbol} ที่ราคา ${entry} (ความเชื่อมั่น {confidence}) |  |
| `order_drift_cancelled_rejected` | title | Broker fill differs from platform record | ยอดที่โบรกเกอร์กรอกต่างจากบันทึกของแพลตฟอร์ม |  |
| `order_drift_cancelled_rejected` | body | {symbol}: your {side} order was {final} by the broker AFTER submission — the platform recorded it at the requested size ({requested}). Review the position on your broker and correct manually if needed. | {symbol}: คำสั่ง {side} ของคุณถูก{final}โดยโบรกเกอร์หลังจากส่งคำสั่งไปแล้ว — แพลตฟอร์มบันทึกไว้ที่ขนาดที่ร้องขอ ({requested}) กรุณาตรวจสอบสถานะที่โบรกเกอร์ของคุณและแก้ไขด้วยตนเองหากจำเป็น |  |
| `order_drift_partial_fill` | title | Broker fill differs from platform record | ยอดที่โบรกเกอร์กรอกต่างจากบันทึกของแพลตฟอร์ม |  |
| `order_drift_partial_fill` | body | {symbol}: broker confirmed {filled_txt} of the requested {requested} {side} — the platform ledger recorded the requested size. Review and correct manually. | {symbol}: โบรกเกอร์ยืนยันการเติมเต็ม {filled_txt} จากคำสั่ง {side} ที่ร้องขอ {requested} — บัญชีของแพลตฟอร์มบันทึกไว้ที่ขนาดที่ร้องขอ กรุณาตรวจสอบและแก้ไขด้วยตนเอง |  |
| `gateway_down_ibkr_session` | title | Your IBKR gateway session is down | เซสชันเกตเวย์ IBKR ของคุณขาดการเชื่อมต่อ |  |
| `gateway_down_ibkr_session` | body | {detail} — live and shadow IBKR orders will not fill until you log in to the Client Portal Gateway again. | {detail} — คำสั่งซื้อขาย IBKR ทั้งแบบจริงและแบบเงา (shadow) จะไม่ถูกดำเนินการจนกว่าคุณจะเข้าสู่ระบบ Client Portal Gateway อีกครั้ง |  |
| `run_dup_key` | title | Run #{run_id} halted: duplicate active run | รัน #{run_id} ถูกระงับ: มีรันที่ทำงานซ้ำกันอยู่ |  |
| `run_dup_key` | body | Another run with the same settings already owns {symbol} ({market}) for this agent, so this one was halted before it could race the same signal. | มีอีกรันหนึ่งที่ตั้งค่าเหมือนกันครอบครอง {symbol} ({market}) อยู่แล้วสำหรับเอเจนต์นี้ รันนี้จึงถูกระงับก่อนที่จะแย่งชิงสัญญาณเดียวกัน |  |
| `run_armed_timeout` | title | Run #{run_id} timed out while armed | รัน #{run_id} หมดเวลาขณะอยู่ในสถานะพร้อมทำงาน |  |
| `run_armed_timeout` | body | Start condition for {symbol} never fired within {hours}h — the run was stopped. | เงื่อนไขเริ่มต้นสำหรับ {symbol} ไม่ทำงานภายใน {hours} ชั่วโมง — รันถูกหยุด |  |
| `run_stop_eval_failed` | title | Run #{run_id} stopped: cannot evaluate stops | รัน #{run_id} ถูกหยุด: ไม่สามารถประเมินจุดหยุดขาดทุนได้ |  |
| `run_stop_eval_failed` | body | {failures} consecutive stop-evaluation failures ({exc}) — stopping for safety. | การประเมินจุดหยุดล้มเหลวติดต่อกัน {failures} ครั้ง ({exc}) — หยุดรันเพื่อความปลอดภัย |  |
| `run_stop_eval_paused` | title | Run #{run_id} paused: stop check failed | รัน #{run_id} ถูกหยุดชั่วคราว: การตรวจสอบจุดหยุดล้มเหลว |  |
| `run_stop_eval_paused` | body | Stop-condition evaluation failed ({exc}); entries are paused until evaluation recovers. | การประเมินเงื่อนไขจุดหยุดล้มเหลว ({exc}) การเข้าเทรดใหม่จะถูกหยุดชั่วคราวจนกว่าการประเมินจะกลับมาทำงานปกติ |  |
| `run_stop_event` | title | Run #{run_id} stop event: {reason} | รัน #{run_id} เกิดเหตุการณ์หยุด: {reason} |  |
| `run_stop_event` | body | {symbol} ({market}) hit {reason} — {outcome} | {symbol} ({market}) ถึง{reason} — {outcome} |  |
| `run_goal_restart` | title | Run #{run_id} reached its goal — restarted as #{new_run_id} | รัน #{run_id} บรรลุเป้าหมาย — เริ่มใหม่เป็น #{new_run_id} |  |
| `run_goal_restart` | body | {symbol} ({market}) hit {reason}; a new run with the same settings is live. | {symbol} ({market}) ถึง{reason} มีรันใหม่ที่ตั้งค่าเหมือนกันเริ่มทำงานแล้ว |  |
| `run_positions_held` | title | Run #{run_id} stopped with positions held | รัน #{run_id} หยุดโดยยังถือสถานะอยู่ |  |
| `run_positions_held` | body | Flatten stayed blocked ({why}) past {minutes}min — the position remains open under the SL/TP watcher. | การปิดสถานะทั้งหมดยังคงถูกบล็อก ({why}) เกิน {minutes} นาที — สถานะยังคงเปิดอยู่ภายใต้การเฝ้าระวังของ SL/TP |  |
| `run_infeasible` | title | Run #{run_id} paused: cannot fund trades | รัน #{run_id} ถูกหยุดชั่วคราว: ไม่สามารถจัดสรรเงินทุนสำหรับการเทรดได้ |  |
| `run_infeasible` | body | {count} consecutive cycles with insufficient cash for the configured max bet — paused until funds or settings change. | เงินสดไม่เพียงพอสำหรับวงเงินเดิมพันสูงสุดที่ตั้งไว้ติดต่อกัน {count} รอบ — หยุดชั่วคราวจนกว่าเงินทุนหรือการตั้งค่าจะเปลี่ยนแปลง |  |
| `run_sub_lapsed` | title | Run #{run_id} paused: subscription expired | รัน #{run_id} ถูกหยุดชั่วคราว: สมาชิกภาพหมดอายุ |  |
| `run_sub_lapsed` | body | Your plan lapsed, so the run was paused (positions and stops stay managed). Renew to resume. | แผนสมาชิกของคุณหมดอายุ รันจึงถูกหยุดชั่วคราว (สถานะและจุดหยุดยังคงถูกจัดการอยู่) ต่ออายุเพื่อเริ่มทำงานอีกครั้ง |  |
| `run_trade_executed` | title | {action_upper} {symbol} | {action_upper} {symbol} |  |
| `run_trade_executed` | body | Run #{run_id} executed {action} {qty} {symbol} @ ${entry} (confidence {confidence}) | รัน #{run_id} ดำเนินการ {action} {qty} {symbol} ที่ราคา ${entry} (ความเชื่อมั่น {confidence}) |  |
| `fleet_watchdog_eval_failed` | title | Fleet #{fleet_id}: equity evaluation failing | ฟลีท #{fleet_id}: การประเมินมูลค่าพอร์ตล้มเหลว |  |
| `fleet_watchdog_eval_failed` | body | Marked-equity evaluation has failed on stale prices for {fails} consecutive passes — new entries are paused. | การประเมินมูลค่าพอร์ต (marked-equity) ล้มเหลวเนื่องจากราคาไม่อัปเดตติดต่อกัน {fails} ครั้ง — การเข้าเทรดใหม่ถูกหยุดชั่วคราว |  |
| `fleet_watchdog_stalled` | title | Fleet #{fleet_id}: supervision stalled | ฟลีท #{fleet_id}: ระบบควบคุมดูแลหยุดทำงาน |  |
| `fleet_watchdog_stalled` | body | The fleet supervisor has not run for 3+ ticks — drawdown rails may be dark. Check the worker. | ตัวควบคุมดูแลฟลีทไม่ได้ทำงานมาแล้วเกิน 3 รอบ — ระบบป้องกันการขาดทุน (drawdown rail) อาจไม่ทำงาน กรุณาตรวจสอบ worker |  |
| `fleet_breaker` | title | Fleet #{fleet_id} STOPPED at −{loss_pct}% | ฟลีท #{fleet_id} หยุดทำงานที่ −{loss_pct}% |  |
| `fleet_breaker` | body | Your Full Auto fleet crossed the −{stop_loss_pct}% stop rail. Every position is being closed. This stop fired at the first check observing the breach; the final loss may exceed the threshold. | ฟลีท Full Auto ของคุณทะลุระดับหยุดที่ −{stop_loss_pct}% ทุกสถานะกำลังถูกปิด การหยุดนี้เกิดขึ้นทันทีที่ตรวจพบการทะลุระดับครั้งแรก ผลขาดทุนสุดท้ายอาจเกินเกณฑ์ที่กำหนด |  |
| `fleet_drawdown_warning` | title | Fleet #{fleet_id} down {loss_pct}% — paused | ฟลีท #{fleet_id} ขาดทุน {loss_pct}% — หยุดชั่วคราว |  |
| `fleet_drawdown_warning` | body | Your Full Auto fleet has lost {loss_pct}% of its budget. New entries are paused; open positions and their stop-losses remain active. If you resume trading from here, continuing is your responsibility. The fleet stops everything automatically at −{stop_loss_pct}%. | ฟลีท Full Auto ของคุณขาดทุนไปแล้ว {loss_pct}% ของงบประมาณ การเข้าเทรดใหม่ถูกหยุดชั่วคราว ส่วนสถานะที่เปิดอยู่และจุดตัดขาดทุนยังคงทำงานตามปกติ หากคุณเลือกกลับมาเทรดต่อจากจุดนี้ ความรับผิดชอบจะเป็นของคุณเอง ฟลีทจะหยุดทุกอย่างโดยอัตโนมัติที่ −{stop_loss_pct}% |  |
| `fleet_churn` | title | Fleet #{fleet_id}: high replacement churn | ฟลีท #{fleet_id}: มีการเปลี่ยนสมาชิกบ่อยผิดปกติ |  |
| `fleet_churn` | body | {n} member replacements today — the market may be chopping your strategies out. Consider pausing the fleet. | มีการเปลี่ยนสมาชิก {n} ครั้งในวันนี้ — ตลาดอาจกำลังทำให้กลยุทธ์ของคุณถูกเขี่ยออกบ่อยครั้ง ควรพิจารณาหยุดฟลีทชั่วคราว |  |

## Inline enum terms (tokens)

| Family | Key | English | Current translation | Your correction |
|---|---|---|---|---|
| comparator | `above` | above | สูงกว่า |  |
| comparator | `below` | below | ต่ำกว่า |  |
| outcome | `flatten` | flattening position. | ปิดสถานะทั้งหมด |  |
| outcome | `hold` | holding position under the SL/TP watcher. | ถือสถานะไว้ภายใต้การเฝ้าระวังของ SL/TP |  |
| trigger_label | `stop_loss` | stop loss | จุดตัดขาดทุน |  |
| trigger_label | `take_profit` | take profit | จุดทำกำไร |  |
| trigger_label | `time_stop` | time stop | หยุดตามเวลา |  |
| action | `buy` | buy | ซื้อ |  |
| action | `sell` | sell | ขาย |  |
| action | `short` | short | ชอร์ต |  |
| action | `cover` ⚠️ | cover | ปิดชอร์ต |  |
| action_upper | `BUY` | BUY | ซื้อ |  |
| action_upper | `SELL` | SELL | ขาย |  |
| action_upper | `SHORT` | SHORT | ชอร์ต |  |
| action_upper | `COVER` | COVER | ปิดชอร์ต |  |
| side | `buy` | buy | ซื้อ |  |
| side | `sell` | sell | ขาย |  |
| side | `short` | short | ชอร์ต |  |
| side | `cover` ⚠️ | cover | ปิดชอร์ต |  |
| final | `cancelled` | cancelled | ยกเลิกแล้ว |  |
| final | `rejected` | rejected | ถูกปฏิเสธ |  |
| status | `armed` ⚠️ | armed | รอเริ่ม |  |
| status | `running` | running | กำลังทำงาน |  |
| status | `paused` | paused | หยุดชั่วคราว |  |
| status | `stopping` | stopping | กำลังหยุด |  |
| status | `stopped` | stopped | หยุดแล้ว |  |

## Verification email

| Part | English | Current translation | Your correction |
|---|---|---|---|
| subject | Your Sooppiy verification code | รหัสยืนยันตัวตน Sooppiy ของคุณ |  |
| html | <p>Your verification code is: <strong>{code}</strong></p><p>It expires in 5 minutes. Do not share it.</p> | <p>รหัสยืนยันตัวตนของคุณคือ: <strong>{code}</strong></p><p>รหัสนี้จะหมดอายุใน 5 นาที กรุณาอย่าเปิดเผยรหัสนี้ให้ผู้อื่นทราบ</p> |  |

_(Keep the `<p>`/`<strong>` tags and `{code}` in the html.)_