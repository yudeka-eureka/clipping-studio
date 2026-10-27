# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Content Creator & Podcaster — pembuat konten mandiri, podcaster, dan video producer yang memproduksi video format panjang (podcast, interview, webinar, rekaman streaming) dan ingin memotong serta mengemas momen-momen terbaik menjadi klip vertikal pendek (TikTok, Reels, YouTube Shorts) secara efisien dan berkualitas tanpa biaya langganan bulanan SaaS pihak ketiga.

## Product Purpose

Clipping Studio adalah aplikasi pemotong dan pengolah klip video otomatis berbasis AI dan pemrosesan lokal. Tujuannya adalah mengotomatisasi rantai kerja produksi video pendek dari video panjang: mendeteksi momen bernilai tinggi dengan AI (Gemini, Claude, atau ChatGPT), melacak wajah pembicara (MediaPipe) agar pas di rasio vertikal (9:16), memotong jeda diam agar ritme berbicara padat, menambahkan subtitle tersinkronisasi otomatis (Whisper lokal), menyematkan judul konteks di atas video, membubuhkan logo/bumper branding, hingga menjadwalkan/mengunggah posting ke berbagai media sosial (Buffer).

Ukuran keberhasilan produk: kreator dapat mengubah video panjang berdurasi 30–60 menit menjadi 3–5 klip vertikal siap posting dalam hitungan menit, dengan kontrol kreatif penuh dan privasi data lokal.

## Positioning

Studio klip mandiri (self-hosted / local-first) yang menggabungkan kecerdasan analisis multimodal AI dengan kekuatan render lokal FFmpeg & AI speech/vision lokal (Whisper & MediaPipe). Tidak seperti layanan SaaS klip berbasis cloud yang memungut biaya mahal per menit durasi dan mengunggah seluruh video sumber ke server pihak ketiga:
- Video diproses langsung di mesin pengguna menggunakan FFmpeg.
- Analisis AI menggunakan model terbaik dengan model BYOK (Bring Your Own Key) tanpa perantara mark-up harga langganan.
- Bebas batasan kuota waktu rendering cloud, menjaga privasi video mentah.

## Operating Context

- **Antarmuka Pengguna**: Web dashboard lokal (FastAPI + Vanilla JS/CSS) di http://localhost:8765 dengan update status & log realtime via WebSocket.
- **Workflow Kreator**: 
  1. Input video sumber: drag-and-drop file video lokal (MP4/MOV/MKV/WEBM) atau link publik (YouTube/TikTok/dll via yt-dlp).
  2. Konfigurasi klip: target rasio (9:16, 1:1, 4:5, 16:9, original), tata letak (fokus wajah, crop tengah, blur), pembuangan jeda diam, subtitle otomatis, logo watermark, dan bumper.
  3. AI Analisis: AI memindai video/transkrip dan merekomendasikan klip berpotensi viral dengan skor, hook, alasan, dan ringkasan.
  4. Review & Penyesuaian: Preview player realtime, penyesuaian manual in/out points klip, edit judul ASS di atas video, regenerasi/render ulang per klip.
  5. Distribusi: Integrasi Buffer API untuk menjadwalkan atau memposting klip langsung ke Instagram Reels, TikTok, YouTube Shorts, X, Facebook, LinkedIn, dll.
- **Mode CLI/Agent**: Dapat dijalankan tanpa UI melalui CLI (`./clip run`) untuk otomatisasi batch atau integrasi AI agent.

## Capabilities and Constraints

- **Kapabilitas**:
  - Dukungan multi-model AI (Google Gemini via video upload, Anthropic Claude & OpenAI ChatGPT via transkrip Whisper lokal + frame sampling).
  - Pelacakan wajah dinamis (MediaPipe BlazeFace & FaceMesh) dengan pergantian kamera otomatis ke pembicara aktif.
  - Pemadatan audio (voice activity detection / transkrip Whisper) untuk membuang jeda diam tanpa merusak intonasi.
  - Subtitle styling otomatis (.ass dengan bounding box aman untuk mobile feed) dan ekspor .srt/.vtt.
  - Antrean render terisolasi (concurrency semaphores & rate limiting) dengan batas waktu eksekusi otomatis untuk mencegah OOM/CPU crash.
  - Hosting klip sementara (Cloudinary / Cloudflare R2) untuk pengiriman media ke Buffer.
- **Batasan Teknis**:
  - Render encoding CPU/GPU tergantung spesifikasi hardware lokal.
  - Batas retensi file job lokal yang dapat dibersihkan otomatis.
  - Claude & ChatGPT tidak menerima video mentah langsung sehingga memerlukan transkripsi audio Whisper terlebih dahulu.

## Brand Commitments

- **Identitas**: "Clipping Studio" (✂️).
- **Tone & Voice**: Lugas, produktif, transparan (menampilkan estimasi biaya AI dalam USD & Rupiah, log terminal interaktif, dan progres realtime).
- **Bahasa**: Bahasa Indonesia sebagai bahasa utama antarmuka, dengan terminologi video internasional yang familiar bagi kreator konten.

## Evidence on Hand

- Aplikasi backend lengkap berbasis Python (FastAPI, yt-dlp, faster-whisper, mediapipe, ffmpeg).
- Frontend web single-page terpadu (`static/index.html`, `static/style.css`, `static/app.js`).
- CLI lengkap (`./clip`).
- Rangkaian pengujian integrasi (`tests/`).

## Product Principles

1. **Local-First & Creator Sovereign**: Data video, render, dan transkrip mentah tetap berada di komputer kreator; AI eksternal hanya menerima data seminimal mungkin untuk pemahaman konten.
2. **Instant Transparency**: Pengguna selalu mengetahui apa yang sedang dikerjakan sistem (status realtime "Menunggu antrean...", progres render per tahapan, rincian biaya token AI).
3. **Frictionless Handoff**: Dari file mentah di storage hingga live posting di feed sosial media terhubung dalam satu jalur kerja tanpa perlu aplikasi ketiga tambahan.
4. **Resilient & Predictable**: Pemrosesan video berat tidak boleh melumpuhkan server; antrean terkontrol rapi, subprocess terlindungi batas waktu (timeout), dan error dilaporkan secara manusiawi.
