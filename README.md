# ✂️ Clipping Studio

Aplikasi lokal untuk memotong video panjang jadi klip pendek (TikTok, Reels, Shorts).
AI **Gemini API** menonton video dan memilih momen terbaik, lalu klip dirender di komputer
sendiri dengan ffmpeg. Semua progres tampil **realtime** di browser lewat WebSocket.

## Menjalankan

```bash
./run.sh
```

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
| `app/main.py` | REST API, WebSocket `/ws`, penyajian file media |
| `app/pipeline.py` | Urutan proses: unduh → proxy → analisis AI → render |
| `app/gemini.py` | Koneksi Gemini: upload, prompt, skema respons |
| `app/facetrack.py` | Deteksi wajah (MediaPipe), pemilihan pembicara dari gerak bibir, jalur kamera |
| `app/transcribe.py` | Transkripsi lokal faster-whisper, pengelompokan kata jadi baris subtitle |
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

## Catatan

- Fitur unduh dari link hanya untuk video milik sendiri atau yang sudah mendapat izin untuk dipakai ulang.
- Waktu potong dari AI kadang meleset beberapa detik. Rapikan lewat kolom waktu di kartu klip lalu klik Render ulang.
- Video di atas 20 menit dianalisis dengan resolusi media rendah supaya muat di context window Gemini.
- `clip_video_starter.py` adalah skrip awal versi baris perintah dan tidak dipakai aplikasi ini.
