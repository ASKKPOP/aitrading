# Translation review — Korean 한국어

Machine-generated notification strings for Sooppiy, pending your review. For each row, check the translation against the English. **To correct**: write the fixed text in the **Your correction** column (leave blank if the translation is fine).

Rules for the reviewer:
- Keep every `{placeholder}` exactly as-is (same name, curly braces) — they're filled with live data (symbols, numbers). You may move a placeholder for natural word order.
- ⚠️ rows are terms the translator flagged as uncertain — please pay extra attention.

## Alert messages (26)

| msg_id | Field | English | Current translation | Your correction |
|---|---|---|---|---|
| `breaker` | title | Circuit breaker HALT ({scope}) | 서킷 브레이커 발동 ({scope}) |  |
| `breaker` | body | Trading halted: {reason} | 거래 중단: {reason} |  |
| `position_closed` | title | {trigger_label} — {symbol} | {trigger_label} — {symbol} |  |
| `position_closed` | body | Watcher closed {symbol} ({market}) at ${price} | 워처가 {symbol}({market}) 포지션을 ${price}에 종료했습니다 |  |
| `watch` | title | Watch: {name} | 감시: {name} |  |
| `watch` | body | {metric}{where} is {value}{unit} ({comparator} your {threshold}{unit} threshold) | {metric}{where}이(가) {value}{unit}입니다 (설정하신 임계값 {threshold}{unit} {comparator}) |  |
| `run_report` | title | Run #{run_id} {symbol} P&L digest | 런 #{run_id} {symbol} 손익 요약 |  |
| `run_report` | body | Run #{run_id} {symbol} ({market}) — period {period_start} → {period_end}: P&L ${pnl}, {trades} trade(s). Status: {status}. | 런 #{run_id} {symbol}({market}) — 기간 {period_start} → {period_end}: 손익 ${pnl}, 거래 {trades}건. 상태: {status}. |  |
| `run_threshold_loss` | title | Run #{run_id} down {loss_pct}% | 런 #{run_id} {loss_pct}% 하락 |  |
| `run_threshold_loss` | body | {symbol} run P&L ${total} crossed -{loss_pct}% of ${base}. | {symbol} 런 손익 ${total}이(가) ${base} 대비 -{loss_pct}%를 넘어섰습니다. |  |
| `run_threshold_profit` | title | Run #{run_id} up {profit_pct}% | 런 #{run_id} {profit_pct}% 상승 |  |
| `run_threshold_profit` | body | {symbol} run P&L ${total} crossed +{profit_pct}% of ${base}. | {symbol} 런 손익 ${total}이(가) ${base} 대비 +{profit_pct}%를 넘어섰습니다. |  |
| `gateway_down_live_order_failed` | title | Live order did not reach your broker | 실거래 주문이 브로커에 전달되지 않았습니다 |  |
| `gateway_down_live_order_failed` | body | {symbol}: {reason} | {symbol}: {reason} |  |
| `automation_trade_executed` | title | {action_upper} {symbol} | {action_upper} {symbol} |  |
| `automation_trade_executed` | body | Automation executed {action} {qty} {symbol} @ ${entry} (confidence {confidence}) | 자동매매가 {action} {qty} {symbol}을(를) ${entry}에 실행했습니다 (신뢰도 {confidence}) |  |
| `order_drift_cancelled_rejected` | title | Broker fill differs from platform record | 브로커 체결이 플랫폼 기록과 다릅니다 |  |
| `order_drift_cancelled_rejected` | body | {symbol}: your {side} order was {final} by the broker AFTER submission — the platform recorded it at the requested size ({requested}). Review the position on your broker and correct manually if needed. | {symbol}: 제출 후 브로커에서 {side} 주문이 {final} 처리되었습니다 — 플랫폼에는 요청 수량({requested})으로 기록되었습니다. 브로커에서 포지션을 확인하고 필요시 직접 수정하세요. |  |
| `order_drift_partial_fill` | title | Broker fill differs from platform record | 브로커 체결이 플랫폼 기록과 다릅니다 |  |
| `order_drift_partial_fill` | body | {symbol}: broker confirmed {filled_txt} of the requested {requested} {side} — the platform ledger recorded the requested size. Review and correct manually. | {symbol}: 브로커는 요청한 {requested} {side} 중 {filled_txt}만 체결을 확인했습니다 — 플랫폼 장부에는 요청 수량이 기록되었습니다. 확인 후 직접 수정하세요. |  |
| `gateway_down_ibkr_session` | title | Your IBKR gateway session is down | IBKR 게이트웨이 세션이 끊겼습니다 |  |
| `gateway_down_ibkr_session` | body | {detail} — live and shadow IBKR orders will not fill until you log in to the Client Portal Gateway again. | {detail} — Client Portal Gateway에 다시 로그인할 때까지 실거래 및 섀도우 IBKR 주문이 체결되지 않습니다. |  |
| `run_dup_key` | title | Run #{run_id} halted: duplicate active run | 런 #{run_id} 중단: 활성 런 중복 |  |
| `run_dup_key` | body | Another run with the same settings already owns {symbol} ({market}) for this agent, so this one was halted before it could race the same signal. | 동일한 설정의 다른 런이 이미 이 에이전트의 {symbol}({market})을(를) 점유하고 있어, 동일 신호를 두고 경합하기 전에 이 런을 중단했습니다. |  |
| `run_armed_timeout` | title | Run #{run_id} timed out while armed | 런 #{run_id} 대기 중 시간 초과 |  |
| `run_armed_timeout` | body | Start condition for {symbol} never fired within {hours}h — the run was stopped. | {symbol}의 시작 조건이 {hours}시간 내에 발생하지 않아 런이 중지되었습니다. |  |
| `run_stop_eval_failed` | title | Run #{run_id} stopped: cannot evaluate stops | 런 #{run_id} 중지: 스탑 평가 불가 |  |
| `run_stop_eval_failed` | body | {failures} consecutive stop-evaluation failures ({exc}) — stopping for safety. | 스탑 평가가 {failures}회 연속 실패({exc})하여 안전을 위해 중지합니다. |  |
| `run_stop_eval_paused` | title | Run #{run_id} paused: stop check failed | 런 #{run_id} 일시중지: 스탑 확인 실패 |  |
| `run_stop_eval_paused` | body | Stop-condition evaluation failed ({exc}); entries are paused until evaluation recovers. | 스탑 조건 평가에 실패({exc})하여 평가가 정상화될 때까지 신규 진입이 일시중지됩니다. |  |
| `run_stop_event` | title | Run #{run_id} stop event: {reason} | 런 #{run_id} 스탑 이벤트: {reason} |  |
| `run_stop_event` | body | {symbol} ({market}) hit {reason} — {outcome} | {symbol}({market})이(가) {reason}에 도달 — {outcome} |  |
| `run_goal_restart` | title | Run #{run_id} reached its goal — restarted as #{new_run_id} | 런 #{run_id} 목표 달성 — #{new_run_id}(으)로 재시작 |  |
| `run_goal_restart` | body | {symbol} ({market}) hit {reason}; a new run with the same settings is live. | {symbol}({market})이(가) {reason}에 도달했습니다. 동일한 설정의 새 런이 시작되었습니다. |  |
| `run_positions_held` | title | Run #{run_id} stopped with positions held | 런 #{run_id} 중지(포지션 보유 상태) |  |
| `run_positions_held` | body | Flatten stayed blocked ({why}) past {minutes}min — the position remains open under the SL/TP watcher. | 청산이 {minutes}분 넘게 차단된 상태({why})입니다 — 포지션은 SL/TP 워처 하에 계속 열려 있습니다. |  |
| `run_infeasible` | title | Run #{run_id} paused: cannot fund trades | 런 #{run_id} 일시중지: 거래 자금 부족 |  |
| `run_infeasible` | body | {count} consecutive cycles with insufficient cash for the configured max bet — paused until funds or settings change. | 설정된 최대 베팅 금액에 필요한 현금이 {count}회 연속 부족하여 자금 또는 설정이 변경될 때까지 일시중지합니다. |  |
| `run_sub_lapsed` | title | Run #{run_id} paused: subscription expired | 런 #{run_id} 일시중지: 구독 만료 |  |
| `run_sub_lapsed` | body | Your plan lapsed, so the run was paused (positions and stops stay managed). Renew to resume. | 구독 플랜이 만료되어 런이 일시중지되었습니다(포지션과 스탑은 계속 관리됩니다). 재개하려면 구독을 갱신하세요. |  |
| `run_trade_executed` | title | {action_upper} {symbol} | {action_upper} {symbol} |  |
| `run_trade_executed` | body | Run #{run_id} executed {action} {qty} {symbol} @ ${entry} (confidence {confidence}) | 런 #{run_id}이(가) {action} {qty} {symbol}을(를) ${entry}에 실행했습니다 (신뢰도 {confidence}) |  |
| `fleet_watchdog_eval_failed` | title | Fleet #{fleet_id}: equity evaluation failing | 플릿 #{fleet_id}: 자산 평가 실패 |  |
| `fleet_watchdog_eval_failed` | body | Marked-equity evaluation has failed on stale prices for {fails} consecutive passes — new entries are paused. | 오래된 가격 데이터로 인해 자산 평가가 {fails}회 연속 실패했습니다 — 신규 진입이 일시중지됩니다. |  |
| `fleet_watchdog_stalled` | title | Fleet #{fleet_id}: supervision stalled | 플릿 #{fleet_id}: 감독 정지 |  |
| `fleet_watchdog_stalled` | body | The fleet supervisor has not run for 3+ ticks — drawdown rails may be dark. Check the worker. | 플릿 감독자가 3틱 이상 실행되지 않았습니다 — 드로우다운 레일이 작동하지 않을 수 있습니다. 워커를 확인하세요. |  |
| `fleet_breaker` | title | Fleet #{fleet_id} STOPPED at −{loss_pct}% | 플릿 #{fleet_id} −{loss_pct}%에서 중지됨 |  |
| `fleet_breaker` | body | Your Full Auto fleet crossed the −{stop_loss_pct}% stop rail. Every position is being closed. This stop fired at the first check observing the breach; the final loss may exceed the threshold. | Full Auto 플릿이 −{stop_loss_pct}% 스탑 레일을 넘었습니다. 모든 포지션을 청산하고 있습니다. 이 스탑은 임계값 이탈을 처음 감지한 시점에 발동한 것으로, 최종 손실은 임계값을 초과할 수 있습니다. |  |
| `fleet_drawdown_warning` | title | Fleet #{fleet_id} down {loss_pct}% — paused | 플릿 #{fleet_id} {loss_pct}% 하락 — 일시중지 |  |
| `fleet_drawdown_warning` | body | Your Full Auto fleet has lost {loss_pct}% of its budget. New entries are paused; open positions and their stop-losses remain active. If you resume trading from here, continuing is your responsibility. The fleet stops everything automatically at −{stop_loss_pct}%. | Full Auto 플릿이 예산의 {loss_pct}%를 잃었습니다. 신규 진입은 일시중지되며, 보유 포지션과 스탑로스는 계속 작동합니다. 여기서 거래를 재개할 경우 그 책임은 사용자에게 있습니다. 플릿은 −{stop_loss_pct}%에서 모든 것을 자동으로 중지합니다. |  |
| `fleet_churn` | title | Fleet #{fleet_id}: high replacement churn | 플릿 #{fleet_id}: 높은 교체 회전율 |  |
| `fleet_churn` | body | {n} member replacements today — the market may be chopping your strategies out. Consider pausing the fleet. | 오늘 멤버 교체가 {n}건 발생했습니다 — 시장 변동성이 전략을 자주 청산시키고 있을 수 있습니다. 플릿 일시중지를 고려하세요. |  |

## Inline enum terms (tokens)

| Family | Key | English | Current translation | Your correction |
|---|---|---|---|---|
| comparator | `above` | above | 위 |  |
| comparator | `below` | below | 아래 |  |
| outcome | `flatten` | flattening position. | 포지션을 청산합니다. |  |
| outcome | `hold` | holding position under the SL/TP watcher. | SL/TP 워처 하에 포지션을 유지합니다. |  |
| trigger_label | `stop_loss` | stop loss | 손절 |  |
| trigger_label | `take_profit` | take profit | 익절 |  |
| trigger_label | `time_stop` | time stop | 타임스탑 |  |
| action | `buy` | buy | 매수 |  |
| action | `sell` | sell | 매도 |  |
| action | `short` | short | 숏 |  |
| action | `cover` ⚠️ | cover | 커버 |  |
| action_upper | `BUY` | BUY | 매수 |  |
| action_upper | `SELL` | SELL | 매도 |  |
| action_upper | `SHORT` | SHORT | 숏 |  |
| action_upper | `COVER` | COVER | 커버 |  |
| side | `buy` | buy | 매수 |  |
| side | `sell` | sell | 매도 |  |
| side | `short` | short | 숏 |  |
| side | `cover` ⚠️ | cover | 커버 |  |
| final | `cancelled` | cancelled | 취소됨 |  |
| final | `rejected` | rejected | 거부됨 |  |
| status | `armed` ⚠️ | armed | 대기 |  |
| status | `running` | running | 실행 중 |  |
| status | `paused` | paused | 일시정지 |  |
| status | `stopping` | stopping | 중지 중 |  |
| status | `stopped` | stopped | 중지됨 |  |

## Verification email

| Part | English | Current translation | Your correction |
|---|---|---|---|
| subject | Your Sooppiy verification code | Sooppiy 인증 코드 |  |
| html | <p>Your verification code is: <strong>{code}</strong></p><p>It expires in 5 minutes. Do not share it.</p> | <p>인증 코드: <strong>{code}</strong></p><p>5분 후 만료됩니다. 타인과 공유하지 마세요.</p> |  |

_(Keep the `<p>`/`<strong>` tags and `{code}` in the html.)_