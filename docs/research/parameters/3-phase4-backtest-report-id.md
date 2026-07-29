<!-- machine-translated from research/parameters/3-phase4-backtest-report.md by docs/design/_gen_doc_translations.py — pending native review -->
# Backtest strategi Phase-4 — hasil go/no-go

**Tanggal:** 2026-07-16 · **Putusan: INSUFFICIENT_EVIDENCE → paket flip TIDAK dirilis. Semua execution gate tetap default-off.**
**Runner:** `service/server/run_phase4_backtest.py` · angka mentah: [phase4-backtest-result.json](phase4-backtest-result.json) · engine: `backtest_strategy.py` (sudah diuji unit; dua kali menjalankan independen menghasilkan byte yang identik).
**Rencana:** [docs/plan/04-ai-model-parameter-upgrade.md](../../plan/04-ai-model-parameter-upgrade.md) §Phase 4 — kriteria telah didaftarkan terlebih dahulu (pre-registered) sebelum jendela OOS dibuka.

## 0. Ringkasan Bahasa Korea

Berdasarkan hasil evaluasi dengan kriteria yang telah didaftarkan terlebih dahulu, **bukti tidak cukup (INSUFFICIENT_EVIDENCE)** — paket flip (execution gate diaktifkan secara default) tidak akan dirilis. Pada pengaturan deploy-faithful (≥4/6), jumlah transaksi OOS pada walk-forward 6 tahun hanya **38 transaksi** (kriteria 400 transaksi), dan baik batas bawah Wilson 90% (0.28) untuk win rate 36.8% maupun batas bawah bootstrap PF (0.64) sama-sama tidak memenuhi kriteria. Pada baris sensitivitas (≥3), jumlah transaksi meningkat menjadi 237, namun batas bawah PF sebesar 0.88 masih di bawah 1.0 — profitabilitas belum terbukti secara statistik.

**Temuan positif:** Risk stack bekerja seperti yang dijanjikan riset — maximum drawdown aset terburuk **2,6%** (B&H −38%~−47% pada periode yang sama), 53% dari likuidasi adalah trailing stop (membiarkan pemenang berjalan), sistem menjaga modal melalui pemblokiran kerugian, bukan prediksi. Prediksi dari lensa statistik panel validasi (jumlah trade tidak cukup) tepat sasaran.

**Langkah berikutnya:** Semua fitur sudah siap dideploy dalam mode tampilan/advisory/opt-in. Setelah telemetri live (confluence vector, factor snapshot) terkumpul, sistem 6-kondisi termasuk B4 akan dievaluasi ulang secara live-forward. Threshold kembali ke riset — bukan produksi.

## 1. Pre-registered setup (unchanged after seeing results)

- **Primary row:** deployment-faithful defaults (`confluence_min=4`, `volume_confirm_min=1.5`), never tuned — zero snooping by construction.
- **Walk-forward row:** anchored, 4 folds, 14-day purge, 6-config grid (reported), tuned on train by pooled profit factor (≥30 trades), frozen on test.
- **Sensitivity row:** `confluence_min=3` fixed (B4 is null historically → only 5 of 6 conditions achievable; the live gate is therefore *stricter* in backtest than in deployment).
- **Kriteria:** ≥400 trade OOS gabungan, jika tidak INSUFFICIENT_EVIDENCE · batas bawah Wilson 90% dari win rate > 0.50 · batas bawah bootstrap 90% dari profit factor > 1.0 · max DD aset terburuk ≤ 30%.
- **Kejujuran cakupan:** B4 null sepanjang; B3 diturunkan menjadi MA/RSI/volume; B5 = leg F&G saja (arsip penuh 2018+, tambahan lag satu hari); S5 null; events = kalender 2019–2025 yang telah diverifikasi ganda sumbernya. Aset: bar BTC/ETH sejak 2019-01 (sinyal ≈2020-02 setelah pemanasan 400-bar), SOL sejak 2020-04 (sinyal ≈2021-05). Fee 0.1%/leg + 0.05% slippage; sinyal close-t terisi pada open t+1.

## 2. Hasil

### Primer (sesuai deployment ≥4/6) — digabungkan atas 4 fold OOS × 3 aset

| Metrik | Nilai | Kriteria | Terpenuhi? |
|---|---|---|---|
| Trade OOS | **38** | ≥ 400 | ❌ (batas bukti minimum) |
| Win rate | 36.8% (14/38) | Wilson90 LB > 0.50 → LB = **0.276** | ❌ |
| Profit factor | 1.13 | bootstrap90 LB > 1.0 → LB = **0.644** | ❌ |
| Max DD aset terburuk | **2.63%** | ≤ 30% | ✅ |

Per fold: F1 (2021-07→2022-12, bear): 19 trade, PF 1.82 · F2: 6 trade, PF 0.69 · F3: 7 trade, PF 6.53 · F4 (2025-07→2026-07, bear): 6 trade, PF 0.0.
Kombinasi exit: trail_stop 20 (53%) · stop_loss 15 · time_stop 3 — profil trend-following yang disarankan riset (memenangkan sebagian kecil trade, biarkan winner berjalan: rata-rata winner ≫ rata-rata loser itulah yang mendorong PF di atas 1 pada win rate 37%).

### Sensitivitas (≥3 dari 5 yang tersedia)

237 trade · win 37.1% (Wilson LB 0.332) · PF 1.15 (bootstrap LB **0.884**) · DD terburuk 8.97%. Lebih banyak bukti, kesimpulan sama: profitabilitas point-estimate, tidak dapat dibedakan secara statistik dari titik impas.

### Walk-forward (disetel per fold, 6 konfigurasi — snooping diperhitungkan)

Setiap fold disetel ke `confluence_min=3`; PF pengujian: F1 1.46, F2 1.82, F3 0.69, F4 0.79. Edge bergantung pada regime dan tidak bertahan lintas fold — konsisten dengan peringatan riset bahwa "published edges decay".

### Korelasi kondisi (lensa statistik memprediksi ini)

Kesepakatan harian B1↔B2 **0.709** (kedua ukuran tren), B1↔B3 0.52, B2↔B3 0.40. Keenam kondisi tidak independen; aritmetika "stack independent 53% edges" tidak berlaku secara harfiah.

### Apa yang BERHASIL

Pada jendela bear F4, strategi merugi ≈1.1–1.7% per aset sementara buy-and-hold merugi **−21% (ETH), −38% (BTC), −47% (SOL)**. Max drawdown 2–9% dibandingkan drawdown historis B&H yang 60%+. Eksposur 3–6% dari hari. **Nilai sistem yang terverifikasi adalah pelestarian modal melalui penyaringan regime dan exit stack — persis seperti klaim riset bahwa "the edge comes from risk management, not prediction." Yang TIDAK terverifikasi adalah profitabilitas mandiri.**

## 3. Keputusan (sesuai aturan yang telah didaftarkan sebelumnya)

1. **Tidak ada flip.** `CONFLUENCE_GATE_ENABLED`, `REGIME_FILTER_ENABLED`, `VOL_SIZING_ENABLED` tetap **default-off**. Tidak ada migrasi preset/`min_confidence` yang dirilis. Kalimat rencana itu sendiri yang berlaku: *"If below [criteria], the confluence thresholds go back to research, not production."*
2. **Apa yang tetap dirilis (sudah digabungkan, tanpa perubahan perilaku eksekusi):** tampilan confluence + agent API, advisory regime + tile, telemetri (vektor confluence per keputusan, snapshot faktor), perbaikan keamanan (breaker tripped_by/expires_at, never-loosen SL/TP, first_opened_at, risk-direction gating, perbaikan put_risk_limits), metrik backtester yang telah diperbaiki, dan toolkit exit opt-in per-agent (trailing/time stops — masing-masing agent dapat mengaktifkannya; ini adalah alat manajemen risiko posisi, bukan klaim profitabilitas).
3. **Jalur evaluasi ulang:** live-forward. Telemetri Phase-1 mengakumulasi vektor 6-kondisi penuh (termasuk B4) pada setiap keputusan; snapshot faktor mencatat funding/OI/L-S/StockTwits. Ketika ≥400 keputusan live gated-quality sudah ada (atau backtest di masa depan dapat menyertakan kondisi yang hilang), jalankan ulang kriteria tersebut. Tabel kalibrasi (hit rate per jumlah confluence, Wilson CIs) terbentuk sendiri dari telemetri.
4. **Pekerjaan threshold kembali ke riset:** pertanyaan terbuka yang menarik dari data ini adalah apakah *exit stack saja* (trail + time stop + regime veto) pada sinyal entry yang lebih sederhana membawa nilai tersebut — confluence entry gate di ≥4/5 begitu ketat sehingga hanya trading 6×/tahun di 3 aset.

*Bukan saran investasi. Platform simulator. Edge historis meluruh; angka-angka ini menggambarkan satu backtest dalam batasan cakupan yang telah didokumentasikan.*
