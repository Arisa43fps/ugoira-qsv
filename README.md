# Pixiv Ugoira Downloader → MP4 Lossless VFR

Unduh ugoira Pixiv dan convert otomatis menjadi **MP4 H.264 lossless** dengan
frame rate variabel (VFR) mengikuti delay asli tiap frame. Berbasis
[gallery-dl](https://github.com/mikf/gallery-dl) (download + metadata delay)
dan ffmpeg lokal (encode). Tanpa skrip API Pixiv manual.

## Format: kenapa MP4 H.264 lossless?

| Opsi | Kualitas | Kompatibilitas | Kesimpulan |
|---|---|---|---|
| **MP4 + H.264 `-crf 0` (default repo ini)** | Tak terlihat bedanya dari JPG asli | Terbaik: HP, TV, browser, editor | **Pilihan utama** |
| MP4 + H.264 `-crf 0` + `yuv444p` (`gallery-dl-444.conf`) | Lossless matematis penuh | Baik, tapi file lebih besar & HP tua lemah | Untuk arsip mutlak |
| MKV MJPEG `-c copy` | Bit-identik | Buruk di HP, seek lemah | Tidak disarankan |
| VP9 lossless / FFV1 | Lossless | Dukungan HP lemah | Tidak disarankan |
| GIF | Lossy, 256 warna | Universal tapi kualitas rendah | Tidak disarankan |

Catatan jujur: H.264 lossless mutlak mensyaratkan `yuv444p`. Default
`gallery-dl.conf` memakai `yuv420p -crf 0`: secara matematis ada konversi
chroma subsampling, tapi secara visual identik dengan frame asli dan jauh
lebih kompatibel. Butuh bit-identik? Pakai `gallery-dl-444.conf`.

VFR akurat dijamin oleh post-processor `ugoira` bawaan gallery-dl mode
`concat`: tiap frame diberi `duration = delay_ms / 1000`, jadi timing
campuran (mis. 100ms/50ms) tetap akurat, bukan dirata-rata.

## Prasyarat

- Python 3.10+ dan `pip install gallery-dl`
- ffmpeg dengan libx264: `winget install Gyan.FFmpeg`
- Akun Pixiv + login di browser (Chrome/Firefox/Edge)

## Cara pakai

1. Isi `urls.txt` dengan URL karya Pixiv (satu per baris).
2. Jalankan:
   - `run.bat` (CMD), atau
   - `powershell -ExecutionPolicy Bypass -File run.ps1`
3. Hasil: `downloads/<id>_<judul>.mp4` + file ZIP asli (karena `keep-files`).

Varian:

```bat
REM Lossless matematis penuh (yuv444p, file lebih besar)
run.bat gallery-dl-444.conf
```

```powershell
# Browser lain untuk cookies
.\run.ps1 -Browser chrome
.\run.ps1 -Config gallery-dl-444.conf -Browser edge
```

## Verifikasi hasil

```bat
ffprobe -v error -show_entries stream=codec_name,pix_fmt,r_frame_rate,avg_frame_rate downloads\<file>.mp4
```

Bandingkan durasi total video dengan jumlah delay di metadata JSON
(`downloads/*.json`): selisih harus < 0,1 detik. Putar di VLC dan HP
untuk memastikan kompatibilitas.

## Reverse-proxy sendiri (Cloudflare Workers)

Semua download file gambar otomatis lewat domain proxymu (`scripts/pximg_rewrite.py`
rewrite `i.pximg.net` → proxymu; URL asli tetap jadi fallback). API `pixiv.net`
tidak tersentuh.

1. Deploy worker reverse-proxy transparan (teruskan path + query apa adanya,
   set header `Referer: https://www.pixiv.net/` — wajib oleh Pixiv):

```js
const ORIGIN = "https://i.pximg.net";
export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const target = new URL(ORIGIN + url.pathname + url.search);
    const headers = new Headers(req.headers);
    headers.set("Referer", "https://www.pixiv.net/");
    headers.set("User-Agent", "PixivIOSApp/5.0");
    const res = await fetch(target, { headers });
    return new Response(res.body, res);
  }
};
```

2. Isi domain workermu — pilih salah satu:
   - Edit `PROXY_HOST` di `scripts/pximg_rewrite.py`, atau
   - Set env saat jalan: `PXIMG_PROXY_HOST=pximg.kamu.workers.dev .\run.ps1 -Urls <URL>`
   - CMD: `set PXIMG_PROXY_HOST=pximg.kamu.workers.dev && run.bat`
3. Kalau `PROXY_HOST` masih `pximg.example.com` (belum diisi), rewrite nonaktif
   otomatis dan download langsung dari `i.pximg.net` seperti biasa.

## File

- `gallery-dl.conf` — config utama (MP4 H.264 lossless yuv420p, VFR concat)
- `gallery-dl-444.conf` — varian lossless penuh (yuv444p)
- `gallery-dl-small.conf` — CPU, ukuran kecil kualitas mendekati asli (`-crf 20`)
- `gallery-dl-qsv-hq.conf` — Intel Quick Sync, kualitas tinggi (ICQ 18, encode 5-10x lebih cepat)
- `gallery-dl-qsv-small.conf` — Intel Quick Sync H.264, ukuran kecil (ICQ 23)
- `gallery-dl-h265-hq.conf` — CPU H.265, kualitas tinggi (`-crf 20`, ~setengah ukuran H.264 setara)
- `gallery-dl-h265-small.conf` — CPU H.265, ukuran kecil (`-crf 24`)
- `gallery-dl-qsv-h265-hq.conf` — Intel Quick Sync H.265, kualitas tinggi (ICQ 20)
- `gallery-dl-qsv-h265-small.conf` — Intel Quick Sync H.265, ukuran kecil (ICQ 25)
- `urls.txt` — daftar batch URL/ID
- `run.bat` / `run.ps1` — peluncur download + convert
