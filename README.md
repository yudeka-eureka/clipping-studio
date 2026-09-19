# ✂️ Clipping Studio

Aplikasi lokal untuk memotong video panjang jadi klip pendek (TikTok, Reels, Shorts).
AI **Gemini API** menonton video dan memilih momen terbaik, lalu klip dirender di komputer
sendiri dengan ffmpeg. Semua progres tampil **realtime** di browser lewat WebSocket.

## Menjalankan

Antarmuka web:

```bash
./run.sh
```

Mode command line (untuk skrip atau AI agent, tanpa web):

```bash
./clip run podcast.mp4 --clips 3 --json
```

Daftar perintah lengkap ada di [AGENTS.md](AGENTS.md) atau `./clip --help`.

Browser terbuka otomatis di http://localhost:8765. Saat pertama kali dijalankan, skrip
menyiapkan environment Python di `.venv` (butuh `uv` atau Python 3.10+).
ffmpeg sudah ikut terpasang lewat paket `imageio-ffmpeg`, jadi tidak perlu install terpisah.

Isi API key Gemini di menu **⚙ Pengaturan** (buat gratis di https://aistudio.google.com/apikey).
Key disimpan di file `.env` dan tidak pernah dikirim ke mana pun selain ke Google.

## Fitur

- Sumber video dari **file lokal** (drag & drop) atau **link** (via yt-dlp)
- Gemini memilih N klip + judul, hook, alasan, skor viral, hashtag, dan transkrip
- Render ke 9:16, 1:1, 4:5, 16:9, atau rasio asli, dengan tata letak:
  - **Fokus wajah** (default): crop mengikuti wajah; kalau ada beberapa orang, kamera pindah ke yang sedang bicara
  - **Crop tengah**, atau **video utuh + latar blur**
- **Hapus jeda diam** otomatis, supaya durasi klip terpakai untuk bicara
- **Judul di atas video** (kotak putih, teks membungkus otomatis) supaya penonton langsung paham konteksnya. Judul bisa diedit di kartu klip
- **Posting ke media sosial lewat Buffer**: Instagram/Facebook (Reel), TikTok, YouTube, LinkedIn, X, Threads, dan lainnya, langsung, masuk antrean, atau dijadwalkan
- **Pemakaian & biaya AI**: token Gemini per proyek (video/audio/teks, output, thinking), estimasi biaya dalam USD & Rupiah, perkiraan biaya sebelum proses, dan dashboard total per bulan/hari/model
- Ganti format proyek lama lalu **Render ulang semua** klip sekaligus
- **Subtitle otomatis** yang pas dengan gerak mulut (Whisper lokal, timestamp per kata), ditempel ke video plus file `.srt`
- Editor manual: putar video sumber, set awal/akhir (tombol `I` / `O`), buat klip sendiri
- Ubah waktu klip lalu **Render ulang**; klip lama langsung diganti tanpa reload halaman
- Proyek tersimpan di `data/jobs/` dan tetap ada setelah server dimatikan

## Alur kerja

```
video → probe → proxy 360p (hemat upload & token) → Gemini Files API
      → generate_content (JSON terstruktur) → render ffmpeg per klip → browser (WebSocket)
```

| File | Isi |
|---|---|
| `app/cli.py` | Mode command line (`./clip`), semua fitur tanpa web |
| `app/main.py` | REST API, WebSocket `/ws`, penyajian file media |
| `app/pipeline.py` | Urutan proses: unduh → proxy → analisis AI → render |
| `app/gemini.py` | Koneksi Gemini: upload, prompt, skema respons |
| `app/facetrack.py` | Deteksi wajah (MediaPipe), pemilihan pembicara dari gerak bibir, jalur kamera |
| `app/transcribe.py` | Transkripsi lokal faster-whisper, pengelompokan kata jadi baris subtitle |
| `app/silence.py` | Deteksi jeda (dari celah antar kata atau energi audio) dan pemetaan waktu |
| `app/buffer.py` | Buffer GraphQL API: daftar channel, buat post video, cek status |
| `app/mediahost.py` | Upload klip ke Cloudinary / Cloudflare R2 untuk mendapat URL publik |
| `app/pricing.py` | Tabel harga Gemini, pencatatan token, estimasi & perhitungan biaya |
| `app/media.py` | Perintah ffmpeg: probe, proxy, crop/blur, subtitle, SRT |
| `app/jobs.py` | Penyimpanan job di disk dan siaran event realtime |
| `static/` | Antarmuka web (HTML/CSS/JS tanpa build) |

## Pengaturan lewat `.env`

```
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash
```

Opsional: `WHISPER_MODEL` (`small` / `medium` / `large-v3-turbo`) dan `WHISPER_LANGUAGE` (`auto` / `id` / `en`).

Model bisa diganti dari menu Pengaturan → **↻ Muat daftar** (mengambil model yang tersedia untuk key Anda).
Port bisa diubah: `PORT=9000 ./run.sh`.

## Cara kerja "Fokus wajah"

1. Frame klip diambil 5x per detik. Wajah dideteksi dengan MediaPipe BlazeFace, di frame penuh dan di dua potongan frame supaya wajah kecil di shot lebar tetap terdeteksi.
2. Wajah dihubungkan antar frame jadi satu jalur per orang.
3. Kalau semua orang muat dalam satu crop, crop membingkai mereka bersama. Kalau tidak, gerak bibir (MediaPipe FaceMesh) dipakai untuk menentukan siapa yang sedang bicara.
4. Kamera bekerja seperti operator: satu shot minimal 1,2 detik, pindah orang dengan potongan langsung, diam saat subjek hanya bergoyang, dan mengikuti saat subjek berpindah.
5. Posisi crop per frame dikirim ke ffmpeg lewat file `sendcmd` (`clips/clip_<id>.cmd`).

Semua proses ini berjalan lokal dan tidak memakai kuota API.

## Subtitle yang pas dengan suara

Gemini hanya memperkirakan waktu ucapan (dibulatkan ~0,5 detik dari video 5 fps), jadi subtitle bisa telat atau duluan.
Saat render, audio klip ditranskripsi ulang di komputer ini dengan faster-whisper (timestamp per kata),
lalu kata dikelompokkan jadi baris pendek (maks ~30 karakter / 2,2 detik, pecah di jeda dan tanda baca).
Teks dari Gemini dipakai sebagai petunjuk ejaan. Hasil per klip disimpan di `clips/clip_<id>.words.json`,
jadi render ulang dengan rentang yang sama tidak mentranskripsi lagi.

Model Whisper diunduh sekali dari Hugging Face saat pertama dipakai (`small` ~480 MB). Kalau gagal (misalnya offline),
aplikasi kembali memakai waktu perkiraan dari Gemini dan menulis peringatan di log.

## Hapus jeda diam

Jeda lebih dari 0,5 detik dibuang, dengan sisa napas 0,12 detik sebelum dan sesudah bicara.
Kalau subtitle aktif, jeda dihitung dari celah antar kata Whisper (tahan musik latar). Kalau tidak, dari energi audio.
Batas potongan dibulatkan ke grid frame supaya audio dan video tetap sinkron walau ada puluhan potongan.
Crop wajah dihitung di timeline asli, sedangkan subtitle dan judul dipetakan ke timeline hasil potong.

## Pemakaian & biaya AI

Setiap analisis Gemini mencatat `usage_metadata` dari respons: token input per jenis (video, audio, teks),
token output, dan token *thinking* (ditagih sebagai output). Biaya dihitung saat itu juga memakai harga
resmi dari [halaman harga Gemini API](https://ai.google.dev/gemini-api/docs/pricing) (tier Paid Standard,
diperbarui 16 Sep 2026), termasuk kenaikan harga seri 3.x Flash mulai 1 Jan 2027.

- Menu **📊 Pemakaian AI**: total bulan ini & keseluruhan, grafik per hari, tabel per proyek & per model.
- Kartu **🤖 Pemakaian AI** di tiap proyek, termasuk biaya rata-rata per klip.
- Perkiraan biaya muncul di form proyek baru setelah memilih file (~300 token/detik video, ~100 untuk video > 20 menit).
- Atur di menu tersebut: tier (Paid/Free), kurs USD→Rupiah, dan harga manual untuk model yang belum ada di tabel.
  Pengaturan disimpan di `data/pricing.json`. **Hitung ulang riwayat** menerapkan pengaturan baru ke catatan lama.

Proyek yang dianalisis sebelum fitur ini ada ditandai "tidak tercatat". Whisper, deteksi wajah, dan render
berjalan lokal sehingga tidak dihitung.

## Posting ke media sosial (Buffer)

1. Buat API key di https://publish.buffer.com/settings/api dan hubungkan akun sosial media di Buffer.
2. Buffer API **tidak menerima upload file**, jadi klip harus punya URL HTTPS publik. Isi salah satu hosting di Pengaturan:
   - **Cloudinary**: cloud name, API key, API secret (Dashboard → API Keys).
   - **Cloudflare R2**: account ID, bucket, access key, secret, dan URL publik bucket (r2.dev atau domain sendiri).
3. Klik **📤 Posting** di kartu klip, pilih channel, edit caption, lalu pilih waktu: antrean Buffer, posting berikutnya, sekarang, atau jadwal tertentu.

Klip diunggah sekali per versi dan dipakai untuk semua channel. Instagram & Facebook dikirim sebagai Reel,
YouTube sebagai video publik (kategori People & Blogs) dengan judul klip. Status tiap channel tampil di kartu klip;
klik **↻ Cek status** untuk memperbarui (terjadwal → terkirim, plus link post).
Paket Free Buffer dibatasi 250 request/hari; daftar channel di-cache 10 menit supaya hemat.

```
BUFFER_API_KEY=...
MEDIA_HOST=cloudinary            # atau r2
CLOUDINARY_CLOUD_NAME=... CLOUDINARY_API_KEY=... CLOUDINARY_API_SECRET=...
R2_ACCOUNT_ID=... R2_BUCKET=... R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=... R2_PUBLIC_URL=https://...
```

## Catatan

- Fitur unduh dari link hanya untuk video milik sendiri atau yang sudah mendapat izin untuk dipakai ulang.
- Waktu potong dari AI kadang meleset beberapa detik. Rapikan lewat kolom waktu di kartu klip lalu klik Render ulang.
- Video di atas 20 menit dianalisis dengan resolusi media rendah supaya muat di context window Gemini.
- `clip_video_starter.py` adalah skrip awal versi baris perintah dan tidak dipakai aplikasi ini.
