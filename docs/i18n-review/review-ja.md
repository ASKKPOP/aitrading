# Translation review — Japanese 日本語

Machine-generated notification strings for Sooppiy, pending your review. For each row, check the translation against the English. **To correct**: write the fixed text in the **Your correction** column (leave blank if the translation is fine).

Rules for the reviewer:
- Keep every `{placeholder}` exactly as-is (same name, curly braces) — they're filled with live data (symbols, numbers). You may move a placeholder for natural word order.
- ⚠️ rows are terms the translator flagged as uncertain — please pay extra attention.

## Alert messages (26)

| msg_id | Field | English | Current translation | Your correction |
|---|---|---|---|---|
| `breaker` | title | Circuit breaker HALT ({scope}) | サーキットブレーカー発動（{scope}） |  |
| `breaker` | body | Trading halted: {reason} | 取引停止：{reason} |  |
| `position_closed` | title | {trigger_label} — {symbol} | {trigger_label} — {symbol} |  |
| `position_closed` | body | Watcher closed {symbol} ({market}) at ${price} | ウォッチャーが{symbol}（{market}）を${price}でクローズしました |  |
| `watch` | title | Watch: {name} | ウォッチ: {name} |  |
| `watch` | body | {metric}{where} is {value}{unit} ({comparator} your {threshold}{unit} threshold) | {metric}{where}は{value}{unit}です（しきい値{threshold}{unit}を{comparator}） |  |
| `run_report` | title | Run #{run_id} {symbol} P&L digest | Run #{run_id} {symbol} 損益レポート |  |
| `run_report` | body | Run #{run_id} {symbol} ({market}) — period {period_start} → {period_end}: P&L ${pnl}, {trades} trade(s). Status: {status}. | Run #{run_id} {symbol}（{market}）— 期間 {period_start} → {period_end}：損益 ${pnl}、取引{trades}件。ステータス：{status}。 |  |
| `run_threshold_loss` | title | Run #{run_id} down {loss_pct}% | Run #{run_id} が{loss_pct}%下落 |  |
| `run_threshold_loss` | body | {symbol} run P&L ${total} crossed -{loss_pct}% of ${base}. | {symbol}のRun損益${total}が${base}の−{loss_pct}%を下回りました。 |  |
| `run_threshold_profit` | title | Run #{run_id} up {profit_pct}% | Run #{run_id} が{profit_pct}%上昇 |  |
| `run_threshold_profit` | body | {symbol} run P&L ${total} crossed +{profit_pct}% of ${base}. | {symbol}のRun損益${total}が${base}の+{profit_pct}%を上回りました。 |  |
| `gateway_down_live_order_failed` | title | Live order did not reach your broker | 実売買注文がブローカーに届きませんでした |  |
| `gateway_down_live_order_failed` | body | {symbol}: {reason} | {symbol}：{reason} |  |
| `automation_trade_executed` | title | {action_upper} {symbol} | {action_upper} {symbol} |  |
| `automation_trade_executed` | body | Automation executed {action} {qty} {symbol} @ ${entry} (confidence {confidence}) | 自動売買が{action} {qty} {symbol}を${entry}で実行しました（信頼度 {confidence}） |  |
| `order_drift_cancelled_rejected` | title | Broker fill differs from platform record | ブローカーの約定内容がプラットフォームの記録と異なります |  |
| `order_drift_cancelled_rejected` | body | {symbol}: your {side} order was {final} by the broker AFTER submission — the platform recorded it at the requested size ({requested}). Review the position on your broker and correct manually if needed. | {symbol}：提出後、ブローカー側で{side}注文が{final}されました — プラットフォームには注文時の数量（{requested}）で記録されています。ブローカー側のポジションを確認し、必要に応じて手動で修正してください。 |  |
| `order_drift_partial_fill` | title | Broker fill differs from platform record | ブローカーの約定内容がプラットフォームの記録と異なります |  |
| `order_drift_partial_fill` | body | {symbol}: broker confirmed {filled_txt} of the requested {requested} {side} — the platform ledger recorded the requested size. Review and correct manually. | {symbol}：ブローカーは注文数量{requested} {side}のうち{filled_txt}の約定を確認しました — プラットフォームの台帳には注文時の数量が記録されています。内容を確認し、手動で修正してください。 |  |
| `gateway_down_ibkr_session` | title | Your IBKR gateway session is down | IBKRゲートウェイセッションが切断されています |  |
| `gateway_down_ibkr_session` | body | {detail} — live and shadow IBKR orders will not fill until you log in to the Client Portal Gateway again. | {detail} — Client Portal Gatewayに再ログインするまで、実売買およびシャドーのIBKR注文は約定しません。 |  |
| `run_dup_key` | title | Run #{run_id} halted: duplicate active run | Run #{run_id} 停止：アクティブなRunが重複 |  |
| `run_dup_key` | body | Another run with the same settings already owns {symbol} ({market}) for this agent, so this one was halted before it could race the same signal. | 同じ設定の別のRunがこのエージェントで既に{symbol}（{market}）を保有しているため、同一シグナルの競合を避けてこのRunは開始前に停止されました。 |  |
| `run_armed_timeout` | title | Run #{run_id} timed out while armed | Run #{run_id} 待機中にタイムアウト |  |
| `run_armed_timeout` | body | Start condition for {symbol} never fired within {hours}h — the run was stopped. | {symbol}の開始条件が{hours}時間以内に発生しなかったため、Runは停止されました。 |  |
| `run_stop_eval_failed` | title | Run #{run_id} stopped: cannot evaluate stops | Run #{run_id} 停止：ストップ条件を評価できません |  |
| `run_stop_eval_failed` | body | {failures} consecutive stop-evaluation failures ({exc}) — stopping for safety. | ストップ条件の評価が{failures}回連続で失敗しました（{exc}）— 安全のため停止します。 |  |
| `run_stop_eval_paused` | title | Run #{run_id} paused: stop check failed | Run #{run_id} 一時停止：ストップ確認に失敗 |  |
| `run_stop_eval_paused` | body | Stop-condition evaluation failed ({exc}); entries are paused until evaluation recovers. | ストップ条件の評価に失敗しました（{exc}）。評価が回復するまでエントリーを一時停止します。 |  |
| `run_stop_event` | title | Run #{run_id} stop event: {reason} | Run #{run_id} ストップイベント：{reason} |  |
| `run_stop_event` | body | {symbol} ({market}) hit {reason} — {outcome} | {symbol}（{market}）が{reason}に到達 — {outcome} |  |
| `run_goal_restart` | title | Run #{run_id} reached its goal — restarted as #{new_run_id} | Run #{run_id} が目標達成 — #{new_run_id}として再開 |  |
| `run_goal_restart` | body | {symbol} ({market}) hit {reason}; a new run with the same settings is live. | {symbol}（{market}）が{reason}に到達。同じ設定の新しいRunが稼働を開始しました。 |  |
| `run_positions_held` | title | Run #{run_id} stopped with positions held | Run #{run_id} 停止（ポジション保有中） |  |
| `run_positions_held` | body | Flatten stayed blocked ({why}) past {minutes}min — the position remains open under the SL/TP watcher. | 手仕舞いが{minutes}分を超えてブロックされたままです（{why}）— ポジションはSL/TPウォッチャー管理下で保有されたままです。 |  |
| `run_infeasible` | title | Run #{run_id} paused: cannot fund trades | Run #{run_id} 一時停止：取引資金を確保できません |  |
| `run_infeasible` | body | {count} consecutive cycles with insufficient cash for the configured max bet — paused until funds or settings change. | 設定された最大ベット額に対して資金が不足しているサイクルが{count}回連続しました — 資金または設定が変更されるまで一時停止します。 |  |
| `run_sub_lapsed` | title | Run #{run_id} paused: subscription expired | Run #{run_id} 一時停止：サブスクリプションが期限切れ |  |
| `run_sub_lapsed` | body | Your plan lapsed, so the run was paused (positions and stops stay managed). Renew to resume. | プランの期限が切れたため、Runは一時停止されました（ポジションとストップの管理は継続します）。再開するには更新してください。 |  |
| `run_trade_executed` | title | {action_upper} {symbol} | {action_upper} {symbol} |  |
| `run_trade_executed` | body | Run #{run_id} executed {action} {qty} {symbol} @ ${entry} (confidence {confidence}) | Run #{run_id}が{action} {qty} {symbol}を${entry}で実行しました（信頼度 {confidence}） |  |
| `fleet_watchdog_eval_failed` | title | Fleet #{fleet_id}: equity evaluation failing | フリート #{fleet_id}：資産評価が失敗しています |  |
| `fleet_watchdog_eval_failed` | body | Marked-equity evaluation has failed on stale prices for {fails} consecutive passes — new entries are paused. | 時価評価が古い価格データにより{fails}回連続で失敗しました — 新規エントリーを一時停止します。 |  |
| `fleet_watchdog_stalled` | title | Fleet #{fleet_id}: supervision stalled | フリート #{fleet_id}：監視が停止しています |  |
| `fleet_watchdog_stalled` | body | The fleet supervisor has not run for 3+ ticks — drawdown rails may be dark. Check the worker. | フリートスーパーバイザーが3ティック以上実行されていません — ドローダウンレールが機能していない可能性があります。ワーカーを確認してください。 |  |
| `fleet_breaker` | title | Fleet #{fleet_id} STOPPED at −{loss_pct}% | フリート #{fleet_id} が−{loss_pct}%で停止しました |  |
| `fleet_breaker` | body | Your Full Auto fleet crossed the −{stop_loss_pct}% stop rail. Every position is being closed. This stop fired at the first check observing the breach; the final loss may exceed the threshold. | Full Autoフリートが−{stop_loss_pct}%のストップレールを超えました。すべてのポジションをクローズしています。このストップは超過を検知した最初のチェックで発動したため、最終的な損失がしきい値を上回る場合があります。 |  |
| `fleet_drawdown_warning` | title | Fleet #{fleet_id} down {loss_pct}% — paused | フリート #{fleet_id} が{loss_pct}%下落 — 一時停止 |  |
| `fleet_drawdown_warning` | body | Your Full Auto fleet has lost {loss_pct}% of its budget. New entries are paused; open positions and their stop-losses remain active. If you resume trading from here, continuing is your responsibility. The fleet stops everything automatically at −{stop_loss_pct}%. | Full Autoフリートは予算の{loss_pct}%を失いました。新規エントリーは一時停止中です。保有中のポジションとストップロスは有効のままです。ここから取引を再開する場合、その継続はご自身の責任となります。フリートは−{stop_loss_pct}%で全ポジションを自動停止します。 |  |
| `fleet_churn` | title | Fleet #{fleet_id}: high replacement churn | フリート #{fleet_id}：入れ替えが頻発しています |  |
| `fleet_churn` | body | {n} member replacements today — the market may be chopping your strategies out. Consider pausing the fleet. | 本日{n}件のメンバー入れ替えが発生しました — 相場の乱高下で戦略が損切りされている可能性があります。フリートの一時停止をご検討ください。 |  |

## Inline enum terms (tokens)

| Family | Key | English | Current translation | Your correction |
|---|---|---|---|---|
| comparator | `above` | above | 上回っています |  |
| comparator | `below` | below | 下回っています |  |
| outcome | `flatten` | flattening position. | ポジションを手仕舞いします。 |  |
| outcome | `hold` | holding position under the SL/TP watcher. | SL/TPウォッチャー管理下でポジションを保持します。 |  |
| trigger_label | `stop_loss` | stop loss | ストップロス |  |
| trigger_label | `take_profit` | take profit | テイクプロフィット |  |
| trigger_label | `time_stop` | time stop | タイムストップ |  |
| action | `buy` | buy | 買い |  |
| action | `sell` | sell | 売り |  |
| action | `short` | short | ショート |  |
| action | `cover` ⚠️ | cover | カバー |  |
| action_upper | `BUY` | BUY | 買い |  |
| action_upper | `SELL` | SELL | 売り |  |
| action_upper | `SHORT` | SHORT | ショート |  |
| action_upper | `COVER` | COVER | カバー |  |
| side | `buy` | buy | 買い |  |
| side | `sell` | sell | 売り |  |
| side | `short` | short | ショート |  |
| side | `cover` ⚠️ | cover | カバー |  |
| final | `cancelled` | cancelled | キャンセル済み |  |
| final | `rejected` | rejected | 拒否済み |  |
| status | `armed` ⚠️ | armed | 待機中 |  |
| status | `running` | running | 実行中 |  |
| status | `paused` | paused | 一時停止中 |  |
| status | `stopping` | stopping | 停止中 |  |
| status | `stopped` | stopped | 停止済み |  |

## Verification email

| Part | English | Current translation | Your correction |
|---|---|---|---|
| subject | Your Sooppiy verification code | Sooppiy認証コードのお知らせ |  |
| html | <p>Your verification code is: <strong>{code}</strong></p><p>It expires in 5 minutes. Do not share it.</p> | <p>認証コードは次のとおりです：<strong>{code}</strong></p><p>このコードの有効期限は5分間です。他人と共有しないでください。</p> |  |

_(Keep the `<p>`/`<strong>` tags and `{code}` in the html.)_