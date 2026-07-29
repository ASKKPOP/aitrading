<!-- machine-translated from research/parameters/2-chart-vs-human-psychology-report-en.md by docs/design/_gen_doc_translations.py — pending native review -->
# Analisis Chart vs Psikologi Manusia: Apa Kata Angka yang Terverifikasi

**Laporan riset mendalam — tingkat keberhasilan per parameter, prediksi buy/sell · Juli 2026**
**Metode:** setiap persentase di bawah ini telah diperiksa faktanya secara adversarial terhadap sumber utama oleh 3 verifikator independen. Klaim yang gagal verifikasi ditandai, bukan dilaporkan sebagai fakta.

---

## Jawaban utama atas pertanyaan Anda

Insting Anda separuh benar — dan riset ini menunjukkan bahwa separuh *lainnya* juga lebih lemah dari yang diperkirakan orang.

Anda menulis bahwa kebanyakan orang percaya pada chart, tetapi **"pola mental orang yang dibentuk oleh kebijakan pemerintah, tren pasar, perang, isu sosial, berita, media sosial, indikator ekonomi, dan headline besar"** lebih penting. Bukti yang terverifikasi menunjukkan:

1. **Angka pola chart yang terkenal itu hanyalah mitos.** "Tingkat keberhasilan 80%+" untuk Head & Shoulders dan Double Bottom yang beredar di situs-situs trading **tidak memiliki dukungan peer-review**. Angka ini bersumber dari catatan praktisi (Bulkowski's *Encyclopedia of Chart Patterns*) — hitungan in-sample, tidak pernah direplikasi secara independen, dan penelusuran riset ini tidak dapat memverifikasinya.
2. **Namun angka psikologi yang terkenal itu juga mendekati mitos.** Bukti yang paling sering dikutip untuk pandangan Anda — "Suasana hati Twitter memprediksi pasar dengan akurasi 87,6%" (Bollen et al. 2011) — hanya didasarkan pada sekitar **~15 hari trading out-of-sample**, menggunakan leksikon eksklusif yang tidak bisa diperiksa siapa pun, **gagal direplikasi secara independen** (nol kekuatan prediktif out-of-sample), dan hedge fund yang dibangun berdasarkan itu tutup dalam waktu setahun.
3. **Apa yang sebenarnya diberikan kedua belah pihak, setelah diverifikasi: kira-kira 50–55% akurasi arah, atau beberapa persen per tahun keunggulan yang disesuaikan risiko.** Pasar itu sulit. Keunggulan yang terdeteksi secara statistik ada di kedua sisi; yang secara ekonomi besar tidak bertahan terhadap pemeriksaan ketat.
4. **Di mana Anda paling benar:** konsensus akademis menyatakan bahwa pola grafik *informatif tetapi tidak menguntungkan secara berdiri sendiri* — sementara data perilaku manusia (sentimen, waktu berita) secara terukur *menambah* informasi pada model. Sistem AI modern memperlakukan psikologi sebagai input nyata; mereka memperlakukan pola grafik klasik sebagian besar sebagai fitur lemah, bukan aturan keputusan.

---

## Bagian A — Analisis grafik: tingkat keberhasilan yang terverifikasi

### A1. Pola grafik secara umum (10 pola klasik)
**Lo, Mamaysky & Wang (2000), *Journal of Finance*** — uji akademis kanonis, saham AS 1962–1996, termasuk Head & Shoulders, Double Top/Bottom, Triangles.

| Hasil | Jumlah |
|---|---|
| Pola yang informatif secara statistik (NYSE/AMEX) | **7 dari 10** (double bottoms TIDAK termasuk di antaranya) |
| Pola yang informatif secara statistik (Nasdaq) | **10 dari 10** |
| Berdasarkan uji Kolmogorov–Smirnov yang lebih ketat | hanya 5 dari 10 |
| Bukti bahwa ini menghasilkan uang | **Tidak ada** — para penulis menyatakan hal ini "tidak selalu berarti bahwa analisis teknikal dapat digunakan untuk menghasilkan keuntungan trading yang berlebih" |

**Kesimpulan mengenai klaim "kesuksesan 80%+":** informatif ≠ tingkat kemenangan. Tidak ada sumber peer-review yang mendukung kesuksesan 80%+ untuk pola klasik mana pun.

### A2. Head & Shoulders secara khusus
**Savin, Weller & Zvingelis (2007), *Journal of Financial Econometrics*** — saham S&P 500 & Russell 2000, 1990–1999.

| Hasil | Jumlah |
|---|---|
| Kelebihan return yang disesuaikan risiko, strategi market-hedged | **5–7% per tahun** |
| Trading H&S secara berdiri sendiri pada saham S&P 500 | **tidak ada bukti profitabilitas** |
| Berdiri sendiri pada Russell 2000 (small caps) | bukti lemah; ~4.2%/tahun setelah biaya institusional |

Pola ini mengandung informasi nyata — tetapi bukan tingkat kemenangan mentah yang tinggi seperti yang diklaim trader.

### A3. Aturan moving-average / golden-cross
**Brock, Lakonishok & LeBaron (1992), *Journal of Finance*** — DJIA, 1897–1986. "Win rate" kanonis yang diukur dalam literatur akademik:

| Hasil | Angka |
|---|---|
| Hari positif setelah sinyal BUY | **53–54%** |
| Hari positif setelah sinyal SELL | **~49%** |
| Hari sinyal beli disetahunkan | ~+12% vs +4% tanpa syarat |
| Hari sinyal jual disetahunkan | ~−7% |
| Setelah koreksi data-snooping + biaya transaksi (Sullivan et al. 1999; Bajgrowicz & Scaillet 2012) | **profit pada dasarnya menghilang**, terutama dalam beberapa dekade terakhir |

Jadi keunggulan sebenarnya yang terukur dari aturan teknikal paling terkenal adalah **~4–5 poin persentase win rate di atas lempar koin, sebelum biaya** — bukan 70–80%.

### A4. MACD dan RSI
**Backtest arXiv Chio (2022)** pada DJIA/Nasdaq/S&P 500, 2015–2021 (⚠️ preprint, belum ditinjau sejawat, tanpa biaya transaksi, periode bullish, tanpa benchmark buy-and-hold):

| Aturan | Win rate |
|---|---|
| MACD saja | **37–68%** tergantung varian/indeks; Sharpe hanya 0,28–0,50 — "bukan alat prediktif yang kuat" |
| MACD + RSI digabung | **78–86%** — tetapi tidak pernah dibandingkan dengan sekadar menahan indeks, jadi ini BUKAN bukti mengalahkan pasar |

Ini sesuai dengan pandangan komunitas yang Anda kutip: indikator yang digabungkan (dengan volume, support/resistance) berkinerja lebih baik daripada pola tunggal mana pun — tetapi "win rate" di sini masih bukan profit.

### A5. Apakah analisis teknikal menguntungkan sama sekali?
**Park & Irwin (2007), *Journal of Economic Surveys*** — tinjauan atas 95 studi modern (1988–2004):

| Hasil | Angka |
|---|---|
| Studi yang menemukan hasil positif | **56 dari 95 (~59%)** |
| Negatif | 20 · Campuran: 19 |
| Kesimpulan keseluruhan | **tidak konklusif** — hasil positif dilemahkan oleh data snooping, pemilihan aturan ex-post, dan biaya yang dilaporkan terlalu rendah |
| Pasar saham secara khusus (literatur awal) | aturan teknikal berhasil di FX/futures, **tidak di saham** |

---

## Bagian B — Psikologi manusia: tingkat keberhasilan yang terverifikasi

### B1. Angka terkenal — dan keruntuhannya
**Bollen, Mao & Zeng (2011):** mood "tenang" Twitter → arah DJIA, klaim **akurasi 87,6%**.

| Fakta | Detail terverifikasi |
|---|---|
| Jendela pelatihan | hanya ~8 bulan pada 2008 |
| Jendela pengujian untuk 87,6% | **~15 hari perdagangan** (1–19 Des 2008) |
| Leksikon mood | milik pribadi (proprietary), tidak pernah dirilis |
| Replikasi independen (Lachanski & Pav 2017) | efek hanya ada pada subsampel asli; **hilang ketika sampel diperluas** ("konsisten dengan data snooping"); **tidak ada kekuatan prediktif out-of-sample** |
| Uji dunia nyata | Hedge fund Derwent Capital Markets, dibangun berdasarkan strategi ini, **tutup pada awal 2012** |

### B2. Apa yang sebenarnya diberikan oleh sentimen
**Greyling & Rossouw (2025, CEPR/VoxEU; ~3 juta tweet, 8 pasar):**

| Hasil | Angka |
|---|---|
| Akurasi arah, semua 8 pasar (FR, DE, JP, ES, UK, US, IN, PL) | **>50% di semua** — hampir tidak lebih baik dari peluang acak |
| S&P 500 AS | akurasi **>55%** (recall hingga 92%, kemungkinan terinflasi oleh ketidakseimbangan kelas) |

**Dari putaran riset pertama (terverifikasi 3-0):** sentimen Twitter di luar jam pasar/semalam memprediksi return S&P 500 keesokan harinya sebesar **~6 basis poin per standar deviasi** (riset Federal Reserve) — nyata, cukup dapat diperdagangkan, tetapi kecil.

### B3. Apa yang TIDAK dapat diverifikasi pada putaran ini (bagian kejujuran)
Untuk saluran psikologi manusia berikut, **tidak ada klaim terkuantifikasi yang bertahan dari verifikasi adversarial** pada tahap ini — bukan karena tidak penting, tetapi karena persentase bersih yang telah ditinjau sejawat (peer-reviewed) tidak terkonfirmasi:

- Indeks sentimen investor VIX / AAII sebagai prediktor arah
- Indeks Economic Policy Uncertainty (kebijakan pemerintah) → efek terhadap return
- Persentase studi peristiwa perang / geopolitik
- Efek hari pengumuman FOMC / CPI
- Herding, loss aversion, overreaction — efek return yang terkuantifikasi
- **Studi ML head-to-head langsung mana pun tentang fitur sentimen vs fitur teknikal** — perbandingan tepat yang dibutuhkan hipotesis Anda masih menjadi pertanyaan penelitian terbuka

Jadi pernyataan paling jujur yang bisa dibuat adalah: input berbasis psikologi adalah hal yang standar dalam sistem AI dan menambah akurasi yang terukur namun sederhana; literatur **belum** membuktikan bahwa input tersebut mengungguli input teknikal sebesar X%.

---

## Tabel perbandingan

| Parameter | Angka folklore | Angka terverifikasi | Mengalahkan lempar koin? | Menguntungkan setelah biaya? |
|---|---|---|---|---|
| Head & Shoulders | "tingkat keberhasilan 80%+" | Kelebihan hasil hedged 5–7%/tahun; tidak menguntungkan jika berdiri sendiri | Informatif | Tidak (S&P 500) |
| Double Bottom | "tingkat keberhasilan 80%+" | TIDAK signifikan di NYSE/AMEX (LMW 2000) | Lemah | Belum terbukti |
| Pennants/Flags | "~50% gagal" | Tidak dicakup oleh uji peer-reviewed | Tidak diketahui | Belum terbukti |
| Golden cross / MA | tingkat kemenangan tinggi | tingkat kemenangan **53–54% vs 49%** | Nyaris tidak | Menghilang setelah koreksi |
| MACD saja | populer | tingkat kemenangan **37–68%**, Sharpe lemah | Kadang-kadang | Tidak ada benchmark |
| MACD + RSI | — | tingkat kemenangan 78–86% (preprint, tanpa biaya, tanpa benchmark) | Ya dalam sampel | Belum terbukti |
| Sentimen Twitter (Bollen) | **87,6%** | replikasi gagal; 0 di luar sampel | Tidak | Dana ditutup |
| Sentimen sosial (realistis) | — | akurasi arah **50–55%** | Nyaris tidak | Marjinal |
| Sentimen berita/sosial semalam | — | ~6bp per SD keesokan hari | Ya, kecil | Marjinal |
| Efek kebijakan/perang/FOMC/VIX | banyak klaim | belum diverifikasi pada putaran ini | — | — |

## Apa artinya ini bagi sistem trading AI

Sintesis praktis — konsisten dengan kedua putaran penelitian:

1. Gunakan sinyal chart/teknikal sebagai **fitur, bukan aturan** — sinyal tersebut membawa informasi statistik (LMW 2000) meskipun tidak satu pun berfungsi sebagai strategi yang berdiri sendiri.
2. Gunakan data psikologi manusia (sentimen berita, media sosial, pengumuman makro) sebagai **fitur tambahan** — data ini menambah informasi nyata, terutama sentimen semalam, tetapi harapkan poin persentase, bukan 87.6%.
3. Harapkan **akurasi arah 50–55%** dari model yang baik. Tolok ukur Gu–Kelly–Xiu menunjukkan bahwa keunggulan berasal dari *menggabungkan* banyak sinyal lemah secara nonlinear (Sharpe 1.35 vs 0.61) — bukan dari satu parameter, grafik, atau faktor psikologis tunggal.
4. Jangan percaya angka tunggal di atas ~60% akurasi tanpa bukti out-of-sample, disesuaikan biaya, dan replikasi. Angka-angka terkenal dari kedua kubu gagal dalam uji tersebut.

*Bukan saran investasi. Saya bukan penasihat keuangan — ini adalah deskripsi dari pengukuran yang telah dipublikasikan, dan keunggulan historis menurun setelah dipublikasikan.*

## Sumber utama

1. Lo, Mamaysky & Wang (2000), *Journal of Finance* — https://web.mit.edu/wangj/www/pap/LoMamayskyWang00.pdf
2. Savin, Weller & Zvingelis (2007), *Journal of Financial Econometrics* — https://academic.oup.com/jfec/article-abstract/5/2/243/785044
3. Park & Irwin (2007), *Journal of Economic Surveys* — https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1467-6419.2007.00519.x
4. Brock, Lakonishok & LeBaron (1992), *Journal of Finance* — https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1992.tb04681.x
5. Sullivan, Timmermann & White (1999), *Journal of Finance* — https://ideas.repec.org/a/bla/jfinan/v54y1999i5p1647-1691.html
6. Chio (2022), backtest MACD/RSI, arXiv — https://arxiv.org/pdf/2206.12282
7. Bollen, Mao & Zeng (2011) — https://arxiv.org/abs/1010.3003
8. Lachanski & Pav (2017), *Econ Journal Watch* (replikasi gagal) — https://econjwatch.org/articles/shy-of-the-character-limit-twitter-mood-predicts-the-stock-market-revisited
9. Greyling & Rossouw (2025), CEPR/VoxEU — https://cepr.org/voxeu/columns/twitter-sentiment-and-stock-market-movements-predictive-power-social-media
