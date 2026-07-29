<!-- machine-translated from research/parameters/2-hybrid-strategy-framework.md by docs/design/_gen_doc_translations.py — pending native review -->
# Kerangka Hibrida: Memadukan Pola Grafik × Psikologi Manusia
## Kerangka Trading Gabungan Pola Grafik × Psikologi Manusia

**Dibangun dari dua putaran riset mendalam yang terverifikasi (200+ agen, diperiksa faktanya dari sumber utama) · Juli 2026**
**⚠️ Kerangka edukasi, bukan saran investasi. Ekspektasi realistis: akurasi arah 50–55% — keunggulan berasal dari konfluensi + manajemen risiko, bukan dari satu sinyal tunggal.**

<div style="border-left:4px solid #2a78d6;background:rgba(42,120,214,.07);padding:12px 16px;border-radius:0 10px 10px 0;margin:14px 0;font-size:13px;line-height:1.6">
<b>Bagaimana kerangka ini dipetakan ke implementasi crypto.</b> Daftar periksa ini menyatakan strategi riset; sistem yang berjalan menyesuaikannya untuk crypto.
<b>VIX → indeks Fear &amp; Greed crypto (F&amp;G)</b>, sebuah skala terbalik — kepanikan adalah <b>F&amp;G &lt; 20</b> (bukan VIX &gt; 30), ketenangan adalah <b>F&amp;G &gt; 30</b>; tidak ada VIX untuk crypto (<code>regime.py</code>, <code>strategy_config.py</code>).
<b>Pola grafik bernama (double bottom, H&amp;S) → skor teknikal komposit</b> (RSI · MA · funding · basis · long/short) yang dikonfirmasi oleh volume — tidak ada detektor pola candlestick (<code>confluence.py</code> B3/S3).
<b>Sentimen return semalam → kecenderungan kerumunan StockTwits</b> (B4). Nama B1–B6 / S1–S6 adalah label kondisi mesin yang sebenarnya.
</div>

---

## 1. Prinsip inti yang dibuktikan oleh riset

Dua fakta terverifikasi mendorong seluruh desain ini:

1. **Pola grafik bersifat informatif tetapi tidak menguntungkan dengan sendirinya** (Lo–Mamaysky–Wang 2000; Savin 2007). Pola-pola tersebut memberi tahu bahwa *sesuatu* sedang terjadi, dengan keunggulan 53–54% paling banter — jangan pernah menggunakannya sebagai pemicu tunggal.
2. **Psikologi menggerakkan pasar tetapi hanya dapat diperdagangkan pada titik ekstrem dan waktu tertentu** (sentimen semalam ~6bp/SD; akurasi sentimen 50–55%; kepanikan/euforia adalah titik di mana efek perilaku terkonsentrasi).

Jadi campurannya adalah: **psikologi menentukan REGIME (kapan, dan seberapa besar risiko); chart menentukan TRIGGER (apa dan pada harga berapa); volume + sentimen MENGKONFIRMASI; volatilitas menentukan SIZE.**

Sinyal bersifat aditif, bukan absolut: setiap kondisi yang terpenuhi menambah satu poin; Anda baru bertindak jika terjadi confluence (4+ dari 6), karena sinyal 53% yang ditumpuk dengan sinyal-sinyal independen 53% lainnya adalah cara sistem nyata bisa melampaui 55%.

---

## 2. Empat lapis tumpukan keputusan

### LAYER 1 — Filter regime psikologi (인간 심리 = 국면 판단) — *"Apakah saya harus trading sama sekali, dan mode apa?"*
| Input | State | Mode |
|---|---|---|
| VIX / tingkat ketakutan | < 20 tenang | **Trend mode** — mengikuti chart |
| | 20–30 gelisah | Kurangi size 50%, perketat stop |
| | > 30 panik | **Contrarian mode** — abaikan pola chart bearish, siapkan pembelian mean-reversion |
| Kalender event (FOMC, CPI, pemilu) | dalam ±1 hari | **Tidak ada entry baru**; tahan atau hedge |
| Headline guncangan perang / kebijakan | 1–3 hari pertama | Jangan pernah membeli pantulan pertama; tunggu sinyal stabilisasi |
| Nada sentimen sosial/berita | euforia ekstrem | Contrarian sell-alert aktif |
| | ketakutan ekstrem | Contrarian buy-alert aktif |

### LAYER 2 — Mesin arah (chart: APA) — prediktor terkuat yang terverifikasi
- Momentum 12 bulan (lewati bulan terakhir) positif → bias long / negatif → bias short
- Harga vs MA 200-hari (state golden-cross) → arah tren
- Reversal jangka pendek 1 bulan → timing counter-trend di dalam bias

### LAYER 3 — Trigger & konfirmasi (chart + psikologi bersama: KAPAN)
Sebuah pola hanya dihitung jika **selesai DAN terkonfirmasi volume DAN sentimen tidak bertentangan**:
- Trigger bullish: breakout double-bottom / H&S-inverse **+ volume naik + sentimen overnight tidak negatif**
- Trigger bearish: penyelesaian double-top / H&S **+ volume naik + nada berita memburuk**
- Tidak ada volume = tidak ada transaksi (fitur volume terverifikasi esensial; Dinh & Kwon 2018)

### LAPISAN 4 — Ukuran & keluar (risiko: BERAPA BANYAK)
- Ukuran posisi = anggaran risiko ÷ volatilitas (terverifikasi: volatilitas adalah prediktor top-4 dan input untuk sizing)
- Stop loss ketat di bawah titik invalidasi pola; trailing dengan MA
- Time stop: jika tesis tidak berjalan dalam N hari → keluar (akurasi Anda ~55%, jadi posisi rugi harus dipotong cepat)

---

## 3. Checklist BELI (confluence ≥ 4 dari 6 → beli)

| # | Sinyal | Sisi sumber | Dasar terverifikasi |
|---|---|---|---|
| B1 | Harga di atas MA 200 hari / kondisi golden-cross | Chart | Brock 1992: hari sinyal-beli +12% tahunan |
| B2 | Momentum 12-1 positif | Chart | GKX 2020: prediktor ML #1 |
| B3 | Pola bullish selesai DENGAN volume | Chart | LMW 2000 informatif + volume esensial |
| B4 | Sentimen semalam/berita positif atau pulih | Psikologi | Fed: ~6bp/SD hari berikutnya |
| B5 | Lonjakan ketakutan memudar (VIX turun dari puncak >30) | Psikologi | Literatur overreaction/mean-reversion |
| B6 | Tidak ada FOMC/CPI/peristiwa besar dalam 24 jam | Psikologi | Waktu risiko peristiwa |

**Kontrarian khusus (panic buy):** VIX > 30 + sentimen pada ketakutan ekstrem + harga stabil di atas MA pendek + volume klimaks terlewati → beli mean-reversion dengan setengah ukuran. (Ini adalah kasus "jadilah serakah saat orang lain takut", yang disistematisasi.)

## 4. Checklist JUAL (confluence ≥ 4 dari 6 → jual/hindari)

| # | Sinyal | Sisi sumber |
|---|---|---|
| S1 | Harga di bawah MA 200 hari / kondisi death-cross | Chart |
| S2 | Momentum berbalik negatif | Chart |
| S3 | Pola bearish (double top / H&S) selesai dengan volume | Chart |
| S4 | Euforia sentimen ekstrem (semua orang bullish, nada mania meme-stock) | Psikologi — kontrarian |
| S5 | Guncangan kebijakan/geopolitik negatif belum terselesaikan | Psikologi |
| S6 | Stop-loss / target volatilitas tercapai | Risiko (selalu mengesampingkan segalanya) |

## 5. Matriks skenario WHEN × WHAT

| Skenario (kondisi psikologi pasar) | Sisi dominan | Aksi |
|---|---|---|
| Uptrend tenang, sentimen positif | Charts | Ikuti tren: beli saat pullback ke MA dengan volume; hold |
| Downtrend tenang | Charts | Diam saja atau condong short; jangan menangkap pisau jatuh tanpa sinyal panik Layer-1 |
| Panik (headline perang, VIX >30, fear ekstrem) | Psychology | Hari 1–3: jangan lakukan apa-apa. Lalu beli kontrarian saat trigger stabilisasi (B5) |
| Euforia (harga parabolik + semua orang bullish) | Psychology | Ambil untung saat kekuatan masih ada; sell trigger S4; jangan pernah menambah posisi |
| Jendela FOMC/CPI/pemilu | Psychology | Flat/tidak ada entry baru; lanjutkan keesokan harinya |
| Breakout pola tanpa volume | Neither | Risiko jebakan — lewati (kebanyakan breakout palsu terjadi di sini) |
| Chart bullish TAPI sentimen runtuh karena berita nyata | Psychology vetoes | Lewati trade — rezim berita mengalahkan chart yang basi |
| Sentimen berisik, tidak ekstrem, chart jelas | Charts | Trading berdasarkan chart; sentimen hanya sebagai pemutus seri |

## 6. Manajemen ekspektasi (angka terverifikasi)

- Akurasi arah yang diharapkan: **50–55%**, bukan 80%.
- Edge tipe golden-cross: ~4–5 poin win-rate di atas lempar koin, sebelum biaya.
- Edge sentimen: basis poin per hari, nyata hanya pada titik ekstrem dan semalaman.
- Edge yang bertumbuh berasal dari: konfluensi (menumpuk edge-edge lemah yang independen), memotong kerugian dengan cepat, sizing berdasarkan volatilitas, dan melewati jendela event — bukan dari kejeniusan prediksi.
- Setiap edge yang dipublikasikan akan meluruh. Backtest, paper-trade, dan validasi ulang out-of-sample sebelum mempertaruhkan uang.

## 7. Sumber utama
Gu–Kelly–Xiu (2020) RFS · Lo–Mamaysky–Wang (2000) JF · Brock et al. (1992) JF · Savin et al. (2007) JFEc · Park & Irwin (2007) JES · Sullivan et al. (1999) JF · Bollen et al. (2011) + Lachanski & Pav (2017) replication · Greyling & Rossouw (2025) CEPR · Fed FEDS 2023-034 · Dinh & Kwon (2018) · Prata et al. (2024).
