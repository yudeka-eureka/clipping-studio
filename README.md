# ✂️ Clipping Studio

Aplikasi lokal untuk memotong video panjang jadi klip pendek (TikTok, Reels, Shorts).
AI (**Gemini**, **Claude**, atau **ChatGPT**) memilih momen terbaik, lalu klip dirender di komputer
sendiri dengan ffmpeg: crop mengikuti wajah, jeda diam dibuang, subtitle diselaraskan dengan suara,
judul di atas, logo, dan penutup. Hasilnya bisa langsung diposting ke media sosial lewat Buffer.
Semua progres tampil **realtime** di browser lewat WebSocket.

## Menjalankan

Antarmuka web:

```bash
./run.sh
```

Mode command line (untuk skrip atau AI agent, tanpa web):

```bash
./clip run podcast.mp4 --clips 3 --json
```

Referensi lengkap semua perintah beserta pilihannya ada di [docs/cli.md](docs/cli.md)
(ringkasan untuk AI agent: [AGENTS.md](AGENTS.md)).

Browser terbuka otomatis di http://localhost:8765. Saat pertama kali dijalankan, skrip
menyiapkan environment Python di `.venv` (butuh `uv` atau Python 3.10+).
ffmpeg sudah ikut terpasang lewat paket `imageio-ffmpeg`, jadi tidak perlu install terpisah.

Isi API key penyedia AI pilihan Anda di halaman **⚙ Pengaturan** (tombol di pojok kanan atas).
API key Gemini bisa dibuat gratis di https://aistudio.google.com/apikey. Key disimpan di file `.env` di komputer ini dan hanya dikirim
ke penyedia yang bersangkutan.

## Fitur

- Sumber video dari **file lokal** (drag & drop) atau **link** (via yt-dlp)
- Pemilih klip bisa **Gemini**, **Claude (Anthropic)**, atau **ChatGPT (OpenAI)** — ganti di Pengaturan
- AI memilih N klip + judul, hook, alasan, skor viral, hashtag, dan transkrip
- Render ke 9:16, 1:1, 4:5, 16:9, atau rasio asli, dengan tata letak:
  - **Fokus wajah** (default): crop mengikuti wajah; kalau ada beberapa orang, kamera pindah ke yang sedang bicara
  - **Crop tengah**, atau **video utuh + latar blur**
- **Hapus jeda diam** otomatis, supaya durasi klip terpakai untuk bicara
- **Judul di atas video** (kotak putih, teks membungkus otomatis) supaya penonton langsung paham konteksnya. Judul bisa diedit di kartu klip
- **Logo (watermark)** di sudut video dan **video/gambar penutup (outro)** di akhir tiap klip
- **Posting ke media sosial lewat Buffer**: Instagram/Facebook (Reel), TikTok, YouTube, LinkedIn, X, Threads, dan lainnya, langsung, masuk antrean, atau dijadwalkan
- **Pemakaian & biaya AI**: token per proyek (video/audio/teks, output, thinking), estimasi biaya dalam USD & Rupiah, perkiraan biaya sebelum proses, dan dashboard total per bulan/hari/model
- Ganti format proyek lama lalu **Render ulang semua** klip sekaligus
- **Subtitle otomatis** yang pas dengan gerak mulut (Whisper lokal, timestamp per kata), ditempel ke video plus file `.srt`
- Editor manual: putar video sumber, set awal/akhir (tombol `I` / `O`), buat klip sendiri
- Ubah waktu klip lalu **Render ulang**; klip lama langsung diganti tanpa reload halaman
- Proyek tersimpan di `data/jobs/` dan tetap ada setelah server dimatikan

## Alur kerja

```
                    ┌─ Gemini    : proxy 360p → Files API → model menonton video
video → probe ──────┤
                    └─ Claude /  : transkrip Whisper lokal + ~20 frame
                       ChatGPT

   → daftar klip (JSON terstruktur)
   → render per klip: crop wajah → buang jeda → subtitle + judul → logo → penutup
   → browser (WebSocket)  →  posting ke Buffer (opsional)
```

| File | Isi |
|---|---|
| `app/cli.py` | Mode command line (`./clip`), semua fitur tanpa web |
| `app/main.py` | REST API, WebSocket `/ws`, penyajian file media |
| `app/pipeline.py` | Urutan proses: unduh → proxy → analisis AI → render |
| `app/analysis.py` | Skema & prompt bersama, pemilihan penyedia AI, sampel frame |
| `app/gemini.py` | Koneksi Gemini: upload video, prompt, skema respons |
| `app/provider_anthropic.py` | Koneksi Claude (transkrip + frame, structured output) |
| `app/provider_openai.py` | Koneksi ChatGPT (transkrip + frame, structured output) |
| `app/facetrack.py` | Deteksi wajah (MediaPipe), pemilihan pembicara dari gerak bibir, jalur kamera |
| `app/transcribe.py` | Transkripsi lokal faster-whisper, pengelompokan kata jadi baris subtitle |
| `app/silence.py` | Deteksi jeda (dari celah antar kata atau energi audio) dan pemetaan waktu |
| `app/buffer.py` | Buffer GraphQL API: daftar channel, buat post video, cek status |
| `app/mediahost.py` | Upload klip ke Cloudinary / Cloudflare R2 untuk mendapat URL publik |
| `app/pricing.py` | Tabel harga Gemini, pencatatan token, estimasi & perhitungan biaya |
| `app/branding.py` | Pengaturan logo & penutup klip |
| `app/media.py` | Perintah ffmpeg: probe, proxy, crop/blur, subtitle, logo, penutup |
| `app/jobs.py` | Penyimpanan job di disk dan siaran event realtime |
| `static/` | Antarmuka web (HTML/CSS/JS tanpa build) |

## Pengaturan lewat `.env`

Semua ini bisa diisi dari halaman Pengaturan, jadi biasanya tidak perlu mengedit file ini langsung.
Contoh lengkap ada di [.env.example](.env.example).

```
AI_PROVIDER=gemini               # gemini | anthropic | openai
GEMINI_API_KEY=...               GEMINI_MODEL=gemini-2.5-flash
ANTHROPIC_API_KEY=...            ANTHROPIC_MODEL=claude-opus-5
OPENAI_API_KEY=...               OPENAI_MODEL=gpt-5.6-terra
WHISPER_MODEL=small              # small | medium | large-v3-turbo
WHISPER_LANGUAGE=auto            # auto | id | en
MEDIA_HOST=cloudinary            # atau r2; kredensialnya lihat bagian Buffer
```

Model bisa diganti dari halaman Pengaturan → **↻ Muat daftar** (mengambil model yang tersedia untuk key Anda).
Port bisa diubah: `PORT=9000 ./run.sh`.

### File yang dibuat aplikasi

| Lokasi | Isi |
|---|---|
| `data/jobs/<id>/` | Video sumber, `job.json`, transkrip, dan klip di `clips/` |
| `data/branding/` | Logo dan file penutup |
| `data/buffer_accounts.json` | Akun Buffer beserta API key-nya (izin file 600) |
| `data/pricing.json` | Tier, kurs, dan harga manual untuk perhitungan biaya |
| `.env` | API key dan pengaturan lain |

Semuanya ada di komputer Anda dan tidak ikut ke git.

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
Kalau penyedianya Gemini, teks perkiraan dari Gemini dipakai sebagai petunjuk ejaan. Hasilnya disimpan
(`clips/clip_<id>.words.json`, atau `source.words.json` kalau transkrip seluruh video sudah dibuat untuk
Claude/ChatGPT), jadi render ulang dengan rentang yang sama tidak mentranskripsi lagi.

Model Whisper diunduh sekali dari Hugging Face saat pertama dipakai (`small` ~480 MB). Kalau gagal (misalnya offline),
aplikasi kembali memakai waktu perkiraan dari AI dan menulis peringatan di log.

## Hapus jeda diam

Jeda lebih dari 0,5 detik dibuang, dengan sisa napas 0,12 detik sebelum dan sesudah bicara.
Kalau subtitle aktif, jeda dihitung dari celah antar kata Whisper (tahan musik latar). Kalau tidak, dari energi audio.
Batas potongan dibulatkan ke grid frame supaya audio dan video tetap sinkron walau ada puluhan potongan.
Crop wajah dihitung di timeline asli, sedangkan subtitle dan judul dipetakan ke timeline hasil potong.

## Logo & penutup klip

Di halaman **⚙ Pengaturan → Logo & penutup klip**:

- **Logo (watermark):** unggah PNG/JPG/WEBP, atur sudut (4 pilihan), lebar (persen dari lebar video),
  transparansi, dan jarak dari tepi. Logo ditempel di atas video, setelah subtitle dan judul.
- **Penutup (outro):** unggah video atau gambar yang disambung di akhir tiap klip. Ukurannya otomatis
  disamakan dengan klip (dengan bar hitam kalau rasionya beda), begitu juga frame rate dan audionya.
  Untuk gambar, durasinya bisa diatur; untuk video, audionya bisa dimatikan.

Dari command line:

```bash
./clip branding --logo logo.png --position bottom-right --size 12 --opacity 0.85
./clip branding --outro outro.mp4        # atau gambar: --outro penutup.png --outro-duration 3
./clip branding --logo-off               # matikan sementara tanpa menghapus filenya
```

File disimpan di `data/branding/`. Keduanya dipasang saat render, jadi klip lama perlu **Render ulang**.
Logo tidak ditempel di bagian outro, karena outro biasanya sudah punya branding sendiri.

## Memilih penyedia AI

| Penyedia | Cara kerja | Catatan |
|---|---|---|
| **Gemini** (default) | Menonton video langsung (gambar + suara) | Paling cepat; token input besar karena video |
| **Claude** | Transkrip Whisper lokal + ~20 frame sebagai gambar | Perlu transkripsi dulu (lama untuk video panjang), token input jauh lebih sedikit |
| **ChatGPT** | Sama seperti Claude | Sama seperti Claude |

Ganti lewat halaman **⚙ Pengaturan → AI pemilih klip**, atau dari command line:

```bash
./clip provider anthropic --model claude-opus-5
./clip config ANTHROPIC_API_KEY        # nilai dibaca dari stdin
```

Transkrip seluruh video disimpan di `source.words.json` dan dipakai ulang untuk subtitle,
jadi Claude/ChatGPT tidak mentranskripsi dua kali. Untuk video tanpa suara, hanya Gemini yang bisa dipakai.

## Pemakaian & biaya AI

Setiap analisis mencatat token dari respons penyedianya: token input per jenis (video, audio, teks),
token output, dan token *thinking*/reasoning. Biaya dihitung saat itu juga memakai harga resmi masing-masing
penyedia — [Gemini](https://ai.google.dev/gemini-api/docs/pricing) (termasuk kenaikan harga seri 3.x Flash
mulai 1 Jan 2027), [Claude](https://docs.claude.com/en/docs/about-claude/pricing), dan
[OpenAI](https://developers.openai.com/api/docs/pricing), tier Paid Standard.

Karena Claude dan ChatGPT hanya membaca transkrip, token inputnya jauh lebih sedikit daripada Gemini
yang menonton video. Bandingkan dulu dengan `./clip estimate video.mp4` sebelum memproses video panjang.

- Menu **📊 Pemakaian AI**: total bulan ini & keseluruhan, grafik per hari, tabel per proyek & per model.
- Kartu **🤖 Pemakaian AI** di tiap proyek, termasuk biaya rata-rata per klip.
- Perkiraan biaya muncul di form proyek baru setelah memilih file (Gemini ~300 token/detik video, ~100 untuk video > 20 menit; Claude/ChatGPT dihitung dari panjang transkrip + frame).
- Atur di menu tersebut: tier (Paid/Free), kurs USD→Rupiah, dan harga manual untuk model yang belum ada di tabel.
  Pengaturan disimpan di `data/pricing.json`. **Hitung ulang riwayat** menerapkan pengaturan baru ke catatan lama.

Proyek yang dianalisis sebelum fitur ini ada ditandai "tidak tercatat". Whisper, deteksi wajah, dan render
berjalan lokal sehingga tidak dihitung.

## Posting ke media sosial (Buffer)

1. Buat API key di https://publish.buffer.com/settings/api dan hubungkan akun sosial media di Buffer.
   Bisa menambahkan **beberapa akun Buffer** (mis. akun sendiri + akun klien): tiap akun punya API key sendiri,
   daftar channelnya digabung, dan satu klip bisa dikirim ke channel milik akun berbeda sekaligus.
   Akun disimpan di `data/buffer_accounts.json` (hanya bisa dibaca pemilik file, tidak ikut ke git).
2. Buffer API **tidak menerima upload file**, jadi klip harus punya URL HTTPS publik. Isi salah satu hosting di Pengaturan:
   - **Cloudinary**: cloud name, API key, API secret (Dashboard → API Keys).
   - **Cloudflare R2**: account ID, bucket, access key, secret, dan URL publik bucket (r2.dev atau domain sendiri).
3. Klik **📤 Posting** di kartu klip, pilih channel, edit caption, lalu pilih waktu: antrean Buffer, posting berikutnya, sekarang, atau jadwal tertentu.

Channel dirujuk sebagai `idAkun:idChannel`, jadi akun berbeda yang punya id channel sama tidak tertukar.
Kalau satu akun bermasalah (key dicabut, kuota habis), akun lain tetap tampil dan hanya muncul peringatan.
Klip diunggah sekali per versi dan dipakai untuk semua channel. Instagram & Facebook dikirim sebagai Reel,
YouTube sebagai video publik (kategori People & Blogs) dengan judul klip. Status tiap channel tampil di kartu klip;
klik **↻ Cek status** untuk memperbarui (terjadwal → terkirim, plus link post).
Paket Free Buffer dibatasi 250 request/hari; daftar channel di-cache 10 menit supaya hemat.

Akun Buffer dikelola dari Pengaturan (atau `./clip accounts`), bukan dari `.env`. Kredensial hosting video:

```
MEDIA_HOST=cloudinary            # atau r2
CLOUDINARY_CLOUD_NAME=... CLOUDINARY_API_KEY=... CLOUDINARY_API_SECRET=...
R2_ACCOUNT_ID=... R2_BUCKET=... R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=... R2_PUBLIC_URL=https://...
```

`BUFFER_API_KEY` di `.env` masih dikenali dan otomatis menjadi akun pertama.

## Catatan

- Fitur unduh dari link hanya untuk video milik sendiri atau yang sudah mendapat izin untuk dipakai ulang.
- Waktu potong dari AI kadang meleset beberapa detik. Rapikan lewat kolom waktu di kartu klip lalu klik Render ulang.
- Untuk Gemini, video di atas 20 menit dianalisis dengan resolusi media rendah supaya muat di context window.
- Claude dan ChatGPT butuh suara: video tanpa audio hanya bisa diproses Gemini atau dipotong manual.
- `clip_video_starter.py` adalah skrip awal versi baris perintah dan tidak dipakai aplikasi ini.
