<!-- machine-translated from research/parameters/2-hybrid-strategy-framework.md by docs/design/_gen_doc_translations.py — pending native review -->
# Kerangka Hibrida: Memadukan Pola Chart × Psikologi Manusia
## Kerangka trading yang memadukan pola chart dengan psikologi manusia

**Disusun dari dua putaran riset mendalam yang terverifikasi (200+ agen, diperiksa faktanya dari sumber utama) · Juli 2026**
**⚠️ Kerangka edukasi, bukan saran investasi. Ekspektasi realistis: akurasi arah 50–55% — keunggulan berasal dari konfluensi + manajemen risiko, bukan dari satu sinyal tunggal.**

<div style="border-left:4px solid #2a78d6;background:rgba(42,120,214,.07);padding:12px 16px;border-radius:0 10px 10px 0;margin:14px 0;font-size:13px;line-height:1.6">
<b>Bagaimana kerangka ini dipetakan ke implementasi crypto.</b> Daftar periksa ini menyatakan strategi riset; sistem yang berjalan mengadaptasinya untuk crypto.
<b>VIX → indeks Fear &amp; Greed crypto (F&amp;G)</b>, sebuah skala terbalik — kepanikan adalah <b>F&amp;G &lt; 20</b> (bukan VIX &gt; 30), tenang adalah <b>F&amp;G &gt; 30</b>; tidak ada VIX untuk crypto (<code>regime.py</code>, <code>strategy_config.py</code>).
<b>Pola chart bernama (double bottom, H&amp;S) → skor teknikal komposit</b> (RSI · MA · funding · basis · long/short) yang dikonfirmasi oleh volume — tidak ada detektor pola candlestick (<code>confluence.py</code> B3/S3).
<b>Sentimen return semalam → kecenderungan crowd StockTwits</b> (B4). Nama B1–B6 / S1–S6 adalah label kondisi mesin yang sesungguhnya.
</div>

---

## 1. Prinsip inti yang dibuktikan oleh riset

Dua fakta terverifikasi mendorong keseluruhan desain ini:

1. **Pola chart bersifat informatif tetapi tidak menguntungkan jika berdiri sendiri** (Lo–Mamaysky–Wang 2000; Savin 2007). Pola ini memberi tahu bahwa *sesuatu* sedang terjadi, dengan keunggulan 53–54% paling baik — jangan pernah menggunakannya sebagai pemicu tunggal.
2. **Psikologi menggerakkan pasar tetapi hanya dapat diperdagangkan pada titik ekstrem dan pada waktu-waktu tertentu** (sentimen semalam ~6bp/SD; akurasi sentimen 50–55%; kepanikan/euforia adalah tempat efek perilaku terkonsentrasi).

Jadi campurannya adalah: **psikologi menentukan REZIM (kapan, dan seberapa besar risiko); grafik menentukan PEMICU (apa dan pada harga berapa); volume + sentimen MENGONFIRMASI; volatilitas menentukan UKURAN.**

Sinyal bersifat aditif, bukan absolut: setiap kondisi yang terpenuhi menambah satu poin; Anda hanya bertindak pada konfluensi (4+ dari 6), karena sinyal 53% yang ditumpuk dengan sinyal-sinyal 53% independen lainnya adalah cara sistem nyata melampaui 55%.

---

## 2. Empat lapisan tumpukan keputusan

### LAPISAN 1 — Filter rezim psikologi (psikologi manusia = penentu rezim) — *"Haruskah saya bertransaksi sama sekali, dan dalam mode apa?"*
| Input | Kondisi | Mode |
|---|---|---|
| VIX / tingkat ketakutan | < 20 tenang | **Mode Tren** — mengikuti grafik |
| | 20–30 gelisah | Kurangi ukuran 50%, perketat stop |
| | > 30 panik | **Mode Kontrarian** — abaikan pola grafik bearish, siapkan pembelian mean-reversion |
| Kalender peristiwa (FOMC, CPI, pemilu) | dalam ±1 hari | **Tidak ada entri baru**; tahan atau lindung nilai |
| Berita kejutan perang / kebijakan | 1–3 hari pertama | Jangan pernah membeli pantulan pertama; tunggu sinyal stabilisasi |
| Nada sentimen sosial/berita | euforia ekstrem | Peringatan jual kontrarian aktif |
| | ketakutan ekstrem | Peringatan beli kontrarian aktif |

### LAPISAN 2 — Mesin arah (grafik: APA) — prediktor terkuat yang telah terverifikasi
- Momentum 12 bulan (melewatkan bulan terakhir) positif → bias long / negatif → bias short
- Harga vs MA 200 hari (kondisi golden-cross) → arah tren
- Pembalikan jangka pendek 1 bulan → penentuan waktu counter-trend di dalam bias

### LAPISAN 3 — Pemicu & konfirmasi (grafik + psikologi bersama: KAPAN)
Suatu pola hanya dihitung jika **selesai DAN dikonfirmasi volume DAN sentimen tidak bertentangan**:
- Bullish trigger: double-bottom / H&S-inverse breakout **+ volume meningkat + sentimen overnight non-negatif**
- Bearish trigger: double-top / H&S completion **+ volume meningkat + tone berita memburuk**
- Tidak ada volume = tidak ada trade (fitur volume terverifikasi esensial; Dinh & Kwon 2018)

### LAYER 4 — Size & exit (risk: BERAPA BANYAK)
- Ukuran posisi = risk budget ÷ volatilitas (terverifikasi: volatilitas adalah top-4 predictor dan input untuk sizing)
- Hard stop di bawah titik invalidasi pattern; trail dengan MA
- Time stop: thesis tidak berjalan dalam N hari → exit (akurasi Anda ~55%, jadi losers harus dipotong dengan cepat)

---

## 3. Checklist BUY (confluence ≥ 4 dari 6 → buy)

| # | Signal | Source side | Basis terverifikasi |
|---|---|---|---|
| B1 | Harga di atas 200-day MA / golden-cross state | Chart | Brock 1992: buy-signal days +12% annualized |
| B2 | Momentum 12-1 positif | Chart | GKX 2020: #1 ML predictor |
| B3 | Pattern bullish completed WITH volume | Chart | LMW 2000 informative + volume esensial |
| B4 | Sentimen overnight/news positif atau recovering | Psychology | Fed: ~6bp/SD next-day |
| B5 | Fear spike memudar (VIX turun dari peak >30) | Psychology | Overreaction/mean-reversion literature |
| B6 | Tidak ada FOMC/CPI/major event dalam 24 jam | Psychology | Event-risk timing |

**Contrarian special (panic buy):** VIX > 30 + sentimen di extreme fear + harga stabil di atas short MA + volume climax terlewati → mean-reversion buy dengan half size. (Ini adalah kasus "be greedy when others are fearful" yang disistematisasi.)

## 4. Checklist SELL (confluence ≥ 4 dari 6 → sell/avoid)

| # | Sinyal | Sisi sumber |
|---|---|---|
| S1 | Harga di bawah 200-day MA / death-cross state | Chart |
| S2 | Momentum berbalik negatif | Chart |
| S3 | Pattern bearish (double top / H&S) completed dengan volume | Chart |
| S4 | Euforia sentimen ekstrem (semua orang bullish, nuansa mania meme-stock) | Psikologi — kontrarian |
| S5 | Guncangan kebijakan/geopolitik negatif yang belum terselesaikan | Psikologi |
| S6 | Stop-loss / target volatilitas tercapai | Risiko (selalu mengesampingkan segalanya) |

## 5. Matriks skenario KAPAN × APA

| Skenario (kondisi psikologi pasar) | Sisi dominan | Tindakan |
|---|---|---|
| Uptrend tenang, sentimen positif | Chart | Ikuti tren: beli pullback ke MA dengan volume; tahan |
| Downtrend tenang | Chart | Tetap di luar atau bias short; jangan menangkap pisau jatuh tanpa sinyal panik Layer-1 |
| Panik (headline perang, VIX >30, ketakutan ekstrem) | Psikologi | Hari 1–3: jangan lakukan apa pun. Lalu beli kontrarian saat trigger stabilisasi (B5) |
| Euforia (harga parabolik + semua orang bullish) | Psikologi | Ambil untung saat penguatan; trigger jual S4; jangan pernah menambah posisi |
| Jendela FOMC/CPI/pemilu | Psikologi | Flat/tidak ada entry baru; lanjutkan keesokan harinya |
| Breakout pola tanpa volume | Tidak keduanya | Risiko jebakan — lewati (sebagian besar breakout palsu ada di sini) |
| Chart bullish TAPI sentimen runtuh akibat berita nyata | Psikologi memveto | Lewati trade — rezim berita mengalahkan chart yang basi |
| Sentimen berisik, tidak ekstrem, chart jelas | Chart | Tradingkan chart-nya; sentimen hanya sebagai pemutus seri |

## 6. Manajemen ekspektasi (angka terverifikasi)

- Akurasi arah yang diharapkan: **50–55%**, bukan 80%.
- Edge tipe golden-cross: ~4–5 poin win-rate di atas lempar koin, sebelum biaya.
- Edge sentimen: basis poin per hari, nyata hanya pada kondisi ekstrem dan semalam.
- Edge yang bertumbuh berasal dari: konfluensi (menumpuk edge lemah yang independen), memotong posisi rugi dengan cepat, menentukan ukuran posisi berdasarkan volatilitas, dan melewati jendela event — bukan dari kejeniusan prediksi.
- Setiap edge yang dipublikasikan akan meluruh. Backtest, paper-trade, dan validasi ulang out-of-sample sebelum mempertaruhkan uang.

## 7. Sumber utama
Gu–Kelly–Xiu (2020) RFS · Lo–Mamaysky–Wang (2000) JF · Brock et al. (1992) JF · Savin et al. (2007) JFEc · Park & Irwin (2007) JES · Sullivan et al. (1999) JF · Bollen et al. (2011) + replikasi Lachanski & Pav (2017) · Greyling & Rossouw (2025) CEPR · Fed FEDS 2023-034 · Dinh & Kwon (2018) · Prata et al. (2024).
