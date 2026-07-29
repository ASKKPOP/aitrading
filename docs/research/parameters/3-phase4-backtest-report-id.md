<!-- machine-translated from research/parameters/3-phase4-backtest-report.md by docs/design/_gen_doc_translations.py — pending native review -->
# Backtest strategi Fase-4 — hasil go/no-go

**Tanggal:** 2026-07-16 · **Putusan: INSUFFICIENT_EVIDENCE → paket flip TIDAK dirilis. Semua execution gate tetap default-off.**
**Runner:** `service/server/run_phase4_backtest.py` · angka mentah: [phase4-backtest-result.json](phase4-backtest-result.json) · engine: `backtest_strategy.py` (sudah diuji unit; dua kali menjalankan secara independen menghasilkan output identik byte demi byte).
**Rencana:** [docs/plan/04-ai-model-parameter-upgrade.md](../../plan/04-ai-model-parameter-upgrade.md) §Fase 4 — kriteria telah didaftarkan terlebih dahulu sebelum jendela OOS dibuka.

## 0. Ringkasan

<!-- Bagian ini ditulis dalam bahasa Korea dan dibiarkan tidak diterjemahkan dalam dokumen BAHASA
     INGGRIS hingga 2026-07-29, sehingga pembaca berbahasa Inggris disuguhi ~309 karakter Korea
     di sini. Teks bahasa Korea berada di tempat yang seharusnya, di
     3-phase4-backtest-report-ko.md; ini adalah versi bahasa Inggrisnya. -->

Dinilai berdasarkan kriteria yang telah didaftarkan sebelumnya, hasilnya adalah **INSUFFICIENT_EVIDENCE** — paket flip (execution gates aktif secara default) **tidak** dirilis. Konfigurasi yang setia pada deployment (≥4/6) hanya menghasilkan **38** transaksi OOS sepanjang walk-forward enam tahun terhadap ambang 400 transaksi, dan baik batas bawah Wilson 90% pada win rate 36.8% (0.28) maupun batas bawah profit-factor hasil bootstrap (0.64) tidak memenuhi syarat. Melonggarkan ke baris sensitivitas (≥3) menaikkan jumlah menjadi 237, tetapi batas bawah PF masih 0.88 — di bawah 1.0, sehingga profitabilitas belum terbukti secara statistik.

**Yang berhasil bertahan:** rangkaian manajemen risiko berperilaku sesuai dengan yang dijanjikan oleh riset — maximum drawdown aset terburuk **2.6%** dibandingkan dengan −38% hingga −47% untuk buy-and-hold pada periode yang sama, 53% dari exit diambil oleh trailing stop (membiarkan posisi untung berjalan), dan modal terjaga dengan cara memotong kerugian bukan dengan memprediksi. Lensa statistik pada panel verifikasi telah memperkirakan hasil ini sebelumnya: jumlah trade terlalu sedikit.

**Selanjutnya:** setiap fitur sudah dapat dikirimkan sebagai display / advisory / opt-in. Evaluasi ulang sistem enam kondisi termasuk B4 live-forward setelah telemetri live (confluence vectors, factor snapshots) terkumpul cukup banyak. Ambang batasnya kembali ke riset — bukan ke produksi.

## 1. Pengaturan pra-registrasi (tidak berubah setelah melihat hasil)

- **Baris utama:** default yang setia pada deployment (`confluence_min=4`, `volume_confirm_min=1.5`), tidak pernah disetel — nol snooping secara konstruksi.
- **Baris walk-forward:** anchored, 4 folds, 14-day purge, grid 6-konfigurasi (dilaporkan), disetel pada data train berdasarkan pooled profit factor (≥30 trades), dibekukan pada data test.
- **Baris sensitivitas:** `confluence_min=3` ditetapkan (B4 null secara historis → hanya 5 dari 6 kondisi yang dapat dicapai; gate live oleh karena itu *lebih ketat* dalam backtest dibandingkan dalam deployment).
- **Kriteria:** ≥400 pooled OOS trades, jika tidak maka INSUFFICIENT_EVIDENCE · batas bawah Wilson 90% dari win rate > 0.50 · batas bawah bootstrap 90% dari profit factor > 1.0 · max DD aset terburuk ≤ 30%.
- **Kejujuran cakupan:** B4 null sepanjang waktu; B3 diturunkan menjadi MA/RSI/volume; B5 = leg F&G saja (arsip lengkap 2018+, lag tambahan satu hari); S5 null; events = kalender 2019–2025 yang terverifikasi dari dua sumber. Aset: bar BTC/ETH dari 2019-01 (sinyal ≈2020-02 setelah 400-bar warmup), SOL dari 2020-04 (sinyal ≈2021-05). Fees 0.1%/leg + 0.05% slippage; sinyal close-t fill pada open t+1.

## 2. Hasil

### Primer (sesuai-deployment ≥4/6) — digabungkan dari 4 fold OOS × 3 aset

| Metrik | Nilai | Kriteria | Terpenuhi? |
|---|---|---|---|
| Transaksi OOS | **38** | ≥ 400 | ❌ (batas bukti minimum) |
| Win rate | 36.8% (14/38) | Wilson90 LB > 0.50 → LB = **0.276** | ❌ |
| Profit factor | 1,13 | bootstrap90 LB > 1,0 → LB = **0,644** | ❌ |
| Maks. DD aset terburuk | **2.63%** | ≤ 30% | ✅ |

Per fold: F1 (2021-07→2022-12, bear): 19 transaksi, PF 1.82 · F2: 6 transaksi, PF 0.69 · F3: 7 transaksi, PF 6.53 · F4 (2025-07→2026-07, bear): 6 transaksi, PF 0.0.
Bauran exit: trail_stop 20 (53%) · stop_loss 15 · time_stop 3 — profil trend-following yang disyaratkan riset (menang pada sebagian kecil transaksi, biarkan yang untung terus berjalan: mean winner ≫ mean loser inilah yang mendorong PF di atas 1 pada win rate 37%).

### Sensitivitas (≥3 dari 5 yang tersedia)

237 transaksi · win 37.1% (Wilson LB 0.332) · PF 1.15 (bootstrap LB **0.884**) · worst DD 8.97%. Lebih banyak bukti, kesimpulan sama: profitabilitas point-estimate, tidak dapat dibedakan secara statistik dari titik impas.

### Walk-forward (disetel per fold, 6 konfigurasi — snooping diperhitungkan)

Setiap fold disetel ke `confluence_min=3`; test PF: F1 1.46, F2 1.82, F3 0.69, F4 0.79. Edge bersifat tergantung-regime dan tidak bertahan lintas fold — konsisten dengan peringatan riset bahwa "edge yang telah dipublikasikan akan meluruh".

### Korelasi kondisi (lensa statistik telah memprediksi ini)

Kesepakatan harian B1↔B2 **0.709** (kedua ukuran tren), B1↔B3 0.52, B2↔B3 0.40. Keenam kondisi tidak independen; perhitungan "menumpuk edge independen 53%" tidak berlaku secara harfiah.

### Apa yang BERHASIL

Pada jendela bear F4, strategi kehilangan ≈1,1–1,7% per aset sementara buy-and-hold kehilangan **−21% (ETH), −38% (BTC), −47% (SOL)**. Max drawdown 2–9% dibandingkan drawdown historis B&H yang 60%+. Eksposur 3–6% dari hari. **Nilai yang terverifikasi dari sistem ini adalah pelestarian modal melalui penyaringan regime dan exit stack — persis seperti klaim riset bahwa "edge berasal dari manajemen risiko, bukan prediksi." Yang TIDAK terverifikasi adalah profitabilitas yang berdiri sendiri.**

## 3. Keputusan (sesuai aturan yang telah diregistrasi sebelumnya)

1. **Tidak ada flip.** `CONFLUENCE_GATE_ENABLED`, `REGIME_FILTER_ENABLED`, `VOL_SIZING_ENABLED` tetap **default-off**. Tidak ada migrasi preset/`min_confidence` yang dirilis. Kalimat dari rencana itu sendiri yang berlaku: *"Jika di bawah [kriteria], ambang confluence kembali ke riset, bukan produksi."*
2. **Yang tetap dirilis (sudah di-merge, tanpa perubahan perilaku eksekusi):** tampilan confluence + agent API, advisory regime + tile, telemetry (vektor confluence per keputusan, snapshot faktor), perbaikan keamanan (breaker tripped_by/expires_at, never-loosen SL/TP, first_opened_at, risk-direction gating, perbaikan put_risk_limits), metrik backtester yang telah diperbaiki, dan toolkit exit opt-in per-agent (trailing/time stops — masing-masing agent dapat mengaktifkannya; ini adalah alat manajemen risiko posisi, bukan klaim profitabilitas).
3. **Jalur evaluasi ulang:** live-forward. Telemetry Fase-1 mengakumulasi vektor 6-kondisi secara lengkap (termasuk B4) pada setiap keputusan; snapshot faktor mencatat funding/OI/L-S/StockTwits. Ketika terdapat ≥400 keputusan live berkualitas gated (atau backtest di masa depan dapat mencakup kondisi yang belum ada), jalankan ulang kriteria tersebut. Tabel kalibrasi (hit rate per jumlah confluence, Wilson CIs) terbentuk dengan sendirinya dari telemetry.
4. **Kerja threshold kembali ke riset:** pertanyaan terbuka yang menarik dari data ini adalah apakah *exit stack saja* (trail + time stop + regime veto) pada sinyal entry yang lebih sederhana yang membawa nilai — confluence entry gate di ≥4/5 begitu ketat sehingga hanya trading 6×/tahun di 3 aset.

*Bukan saran investasi. Platform simulator. Edge historis mengalami penurunan; angka-angka ini menggambarkan satu backtest di bawah batasan cakupan yang didokumentasikan.*
