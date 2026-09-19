# Referensi perintah `./clip`

Semua fitur Clipping Studio tersedia tanpa membuka web. Halaman ini memuat **semua** perintah
beserta pilihannya. Untuk ringkasan singkat khusus AI agent, lihat [AGENTS.md](../AGENTS.md).

```
./clip [--json] [--quiet] <perintah> [argumen…]
```

Flag global boleh ditulis sebelum atau sesudah nama perintah — `./clip --json jobs` sama dengan
`./clip jobs --json`.

| Flag global | Arti |
|---|---|
| `--json` | Hasil ditulis sebagai JSON ke **stdout**. Tanpa ini, keluarannya teks ringkas untuk dibaca manusia. |
| `--quiet`, `-q` | Tidak menampilkan progres di stderr. |
| `-h`, `--help` | Bantuan. Berlaku juga per perintah: `./clip run --help`. |

**Aturan keluaran:** hasil selalu ke stdout, progres dan log selalu ke stderr, jadi `./clip ... --json | jq`
aman dipakai. **Kode keluar:** `0` berhasil, `1` gagal (dengan `--json`, isinya `{"ok": false, "error": "…"}`),
`130` kalau dihentikan dengan Ctrl-C.

**Satuan waktu:** semua `--start`, `--end`, dan `--duration` dalam **detik** (boleh desimal), bukan `mm:ss`.

**Menyebut proyek dan klip:** argumen `JOB` menerima id penuh (`20260919-132416-d500d6`), awalan id
(`20260919-13`), nama proyek, atau kata `last` untuk proyek terbaru. Argumen `CLIP` menerima id klip
atau awalannya.

---

## Ringkasan

| Perintah | Kegunaan | Biaya |
|---|---|---|
| [`doctor`](#doctor) | Cek ffmpeg, model, API key, hosting | gratis |
| [`run`](#run) | Pipeline penuh: AI pilih momen → render semua klip | **API berbayar** |
| [`cut`](#cut) | Potong satu klip pada waktu tertentu, tanpa AI | gratis |
| [`rerender`](#rerender) | Render ulang klip dengan format/waktu berbeda | gratis |
| [`jobs`](#jobs) | Daftar proyek | gratis |
| [`show`](#show) | Detail satu proyek beserta klipnya | gratis |
| [`rm`](#rm) | Hapus proyek beserta filenya | gratis, **permanen** |
| [`transcribe`](#transcribe) | Transkrip Whisper lokal | gratis |
| [`estimate`](#estimate) | Perkiraan token & biaya sebelum proses | gratis |
| [`usage`](#usage) | Token & biaya yang sudah terpakai | gratis |
| [`provider`](#provider) | Lihat / ganti penyedia AI | gratis |
| [`branding`](#branding) | Logo watermark & penutup klip | gratis |
| [`accounts`](#accounts) | Kelola akun Buffer | 2 request Buffer saat menambah |
| [`channels`](#channels) | Daftar channel media sosial | 2 request Buffer per akun |
| [`publish`](#publish) | Kirim klip ke media sosial lewat Buffer | **memposting ke akun Anda** |
| [`publish-status`](#publish-status) | Status terbaru post di Buffer | 1 request Buffer |
| [`config`](#config) | Lihat / ubah pengaturan di `.env` | gratis |
| [`serve`](#serve) | Jalankan antarmuka web | gratis |

---

## doctor

Memastikan semuanya siap sebelum memproses: ffmpeg, dukungan subtitle, deteksi wajah, API key tiap
penyedia AI, model Whisper yang sudah terunduh, akun Buffer, dan hosting video.

```bash
./clip doctor
./clip doctor --json
```

Keluaran JSON: `ffmpeg`, `subtitles_supported`, `face_tracking`, `provider`, `model`, `providers`
(per penyedia: `label`, `video`, `key`, `model`), `whisper_model`, `whisper_downloaded`,
`whisper_language`, `buffer_key`, `media_host`, `media_host_missing`, `pricing_tier`, `usd_idr`,
`data_dir`, `jobs`.

---

## run

Pipeline penuh: salin/unduh video → AI memilih momen → render semua klip.

```bash
./clip run podcast.mp4
./clip run "https://www.youtube.com/watch?v=..." --clips 5 --min-len 20 --max-len 60
./clip run rapat.mp4 --aspect 1:1 --layout blur --no-trim --json
```

| Argumen | Default | Arti |
|---|---|---|
| `source` | wajib | File video lokal atau link (YouTube dll, lewat yt-dlp) |
| `--clips N` | `3` | Jumlah klip yang dipilih AI (1–15) |
| `--min-len N` | `30` | Durasi klip minimal, detik |
| `--max-len N` | `90` | Durasi klip maksimal, detik |
| `--aspect` | `9:16` | `9:16`, `1:1`, `4:5`, `16:9`, atau `original` |
| `--layout` | `face` | `face` (crop mengikuti pembicara), `crop` (crop tengah), `blur` (video utuh + latar blur) |
| `--no-subtitles` | — | Tanpa subtitle |
| `--no-trim` | — | Jeda diam dibiarkan |
| `--no-title` | — | Judul tidak ditempel di atas video |
| `--instructions "…"` | — | Instruksi tambahan untuk AI, mis. `"fokus ke tips praktis, hindari iklan"` |
| `--link` | — | Hardlink file sumber alih-alih menyalin (hemat disk, hanya untuk file di drive yang sama) |

Memakai penyedia AI yang aktif (lihat [`provider`](#provider)). Untuk Claude dan ChatGPT, transkrip
Whisper dibuat lebih dulu sehingga prosesnya lebih lama dan video tanpa suara tidak bisa diproses.
Keluar dengan kode `1` kalau analisis AI gagal; klip manual tetap bisa dibuat dengan [`cut --job`](#cut).

---

## cut

Memotong satu klip pada waktu yang Anda tentukan sendiri, **tanpa memanggil AI**. Berguna untuk
menambah klip ke proyek yang sudah ada, atau memotong video tanpa biaya API sama sekali.

```bash
./clip cut podcast.mp4 --start 90 --end 140 --title "Bagian menarik"
./clip cut --job last --start 750 --end 785            # tambah klip ke proyek yang sudah ada
```

| Argumen | Default | Arti |
|---|---|---|
| `source` | — | File/link video. Boleh dikosongkan kalau memakai `--job` |
| `--job JOB` | — | Pakai video sumber proyek yang sudah ada |
| `--start N` | wajib | Detik mulai |
| `--end N` | akhir video | Detik selesai |
| `--title "…"` | `Klip manual N` | Judul klip (tampil di atas video) |

Menerima juga semua opsi format dari [`run`](#run) (`--aspect`, `--layout`, `--no-subtitles`,
`--no-trim`, `--no-title`, `--link`) untuk proyek baru.

---

## rerender

Render ulang klip yang sudah ada: ganti format, ubah waktu potong, atau ganti judul. Transkrip yang
sudah ada dipakai ulang, jadi tidak ada transkripsi ulang selama rentang waktunya sama.

```bash
./clip rerender last                       # semua klip, format dari proyeknya
./clip rerender last a1b2c3d4 --aspect 1:1 --no-title
./clip rerender last a1b2c3d4 --start 95 --end 150 --title "Judul baru"
```

| Argumen | Arti |
|---|---|
| `job` | Proyek yang dirender ulang |
| `clips…` | Id klip (boleh beberapa). Kosong = semua klip |
| `--start N`, `--end N` | Ubah rentang waktu klip |
| `--title "…"` | Ubah judul |
| `--aspect`, `--layout` | Ubah format video |
| `--no-subtitles`, `--no-trim`, `--no-title` | Matikan subtitle / pembuangan jeda / judul |

Opsi format yang diberikan **disimpan ke proyek**, jadi render berikutnya ikut memakainya.
Logo dan penutup dari [`branding`](#branding) ikut terpasang di sini.

---

## jobs

```bash
./clip jobs
./clip jobs --limit 5 --json
```

`--limit N` (default `20`) membatasi jumlah proyek terbaru yang ditampilkan.

---

## show

Detail satu proyek: status, ringkasan AI, semua klip beserta path filenya, dan pemakaian token.

```bash
./clip show last
./clip show 20260919-13 --logs
./clip show last --json | jq -r '.clips[].file'
```

`--logs` menyertakan log proses (unduh, deteksi wajah, subtitle, render, posting).

---

## rm

```bash
./clip rm 20260919-132416-d500d6
```

**Menghapus permanen** video sumber, semua klip, transkrip, dan catatan pemakaian proyek tersebut.
Tidak ada konfirmasi dan tidak bisa dibatalkan.

---

## transcribe

Transkrip Whisper lokal dengan waktu per kata. Tidak memakai API dan tidak membuat proyek.

```bash
./clip transcribe rapat.mp4                          # teks dengan timestamp
./clip transcribe rapat.mp4 --format srt > rapat.srt
./clip transcribe --job last --start 60 --end 120 --format json
```

| Argumen | Default | Arti |
|---|---|---|
| `source` | — | File video atau audio (mp4, mov, m4a, mp3, …). Boleh dikosongkan kalau memakai `--job` |
| `--job JOB` | — | Transkrip video sumber sebuah proyek |
| `--start N` | `0` | Detik mulai |
| `--end N` | akhir | Detik selesai |
| `--format` | `text` | `text` (per baris dengan waktu), `srt` (ke stdout), `json` (kata + baris subtitle) |

Model diatur lewat `WHISPER_MODEL` dan `WHISPER_LANGUAGE` (lihat [`config`](#config)); model diunduh
sekali saat pertama dipakai.

---

## estimate

Perkiraan token dan biaya **sebelum** memproses. Hitungan lokal, tidak memanggil API.

```bash
./clip estimate podcast.mp4
./clip estimate --duration 3600 --clips 5          # untuk sumber berupa link
./clip estimate podcast.mp4 --json | jq .usd
```

| Argumen | Default | Arti |
|---|---|---|
| `source` | — | File video (durasinya dibaca dari file) |
| `--duration N` | — | Durasi dalam detik, dipakai kalau sumbernya link |
| `--clips N` | `3` | Jumlah klip yang direncanakan |
| `--max-len N` | `90` | Durasi klip maksimal |
| `--no-subtitles` | — | Tanpa subtitle (mengurangi token keluaran untuk Gemini) |

Keluaran JSON: `prompt_tokens`, `output_tokens`, `usd`, `tier`, `low_res`, `price`, `model`,
`provider`, `duration`, `usd_idr`.

---

## usage

Token dan biaya yang sudah terpakai, per proyek dan totalnya.

```bash
./clip usage
./clip usage --json | jq '.total.usd'
```

Keluaran JSON: `total` (`calls`, `prompt_tokens`, `output_tokens`, `usd`), `projects[]`
(`id`, `name`, `calls`, `prompt_tokens`, `output_tokens`, `usd`, `model`), `usd_idr`, `tier`.
Tier, kurs, dan harga manual diatur dari halaman **📊 Pemakaian AI** di web.

---

## provider

Lihat atau ganti penyedia AI pemilih klip.

```bash
./clip provider                                   # lihat semua, tanda * = aktif
./clip provider anthropic --model claude-opus-5
./clip provider gemini
```

| Argumen | Arti |
|---|---|
| `name` | `gemini`, `anthropic`, atau `openai`. Kosong = hanya menampilkan |
| `--model M` | Model untuk penyedia tersebut |

API key diisi lewat [`config`](#config). Gemini menonton video langsung; Claude dan ChatGPT membaca
transkrip Whisper + sekitar 20 frame.

---

## branding

Logo (watermark) dan video/gambar penutup untuk semua klip yang dirender berikutnya.

```bash
./clip branding                                   # lihat pengaturan sekarang
./clip branding --logo logo.png --position bottom-right --size 12 --opacity 0.85
./clip branding --outro penutup.mp4
./clip branding --outro penutup.png --outro-duration 3
./clip branding --logo-off                        # matikan sementara, file tetap disimpan
./clip branding --remove-outro
```

| Argumen | Default | Arti |
|---|---|---|
| `--logo FILE` | — | Pasang logo (`.png`, `.jpg`, `.jpeg`, `.webp`) |
| `--position` | `bottom-right` | `top-left`, `top-right`, `bottom-left`, `bottom-right` |
| `--size N` | `12` | Lebar logo, persen dari lebar video (3–40) |
| `--opacity N` | `0.85` | Transparansi logo (0.1–1.0) |
| `--margin N` | `5` | Jarak dari tepi, persen lebar video (0–25) |
| `--logo-off`, `--logo-on` | — | Matikan/hidupkan tanpa menghapus file |
| `--remove-logo` | — | Hapus file logo |
| `--outro FILE` | — | Pasang penutup (video atau gambar) |
| `--outro-duration N` | `2.5` | Durasi penutup kalau berupa gambar, detik (0.5–15) |
| `--outro-mute` | — | Buang audio penutup |
| `--outro-off`, `--outro-on` | — | Matikan/hidupkan tanpa menghapus file |
| `--remove-outro` | — | Hapus file penutup |

Berlaku **global** untuk semua proyek. Klip yang sudah jadi perlu [`rerender`](#rerender) supaya ikut
berubah. Logo tidak ditempel di bagian penutup.

---

## accounts

Kelola akun Buffer. Boleh lebih dari satu akun (mis. akun sendiri dan akun klien).

```bash
./clip accounts                                   # daftar akun
./clip accounts --add --label "Klien A"           # API key dibaca dari stdin
echo "$KEY" | ./clip accounts --add --label "Klien A"
./clip accounts --rename a1b2c3d4 --label "Akun utama"
./clip accounts --remove a1b2c3d4
```

| Argumen | Arti |
|---|---|
| `--add` | Tambah akun. API key dibaca dari stdin kalau `--key` tidak diberikan |
| `--key K` | API key langsung di perintah — **hindari**, tersimpan di riwayat shell |
| `--label "…"` | Nama akun. Kosong = diambil dari nama organisasi di Buffer |
| `--rename ID --label "…"` | Ganti nama akun |
| `--remove ID` | Hapus akun (tanpa konfirmasi) |

API key diperiksa ke Buffer sebelum disimpan. Disimpan di `data/buffer_accounts.json` dengan izin 600.
`BUFFER_API_KEY` lama di `.env` otomatis menjadi akun pertama.

---

## channels

Daftar channel media sosial dari semua akun Buffer. Kolom pertama adalah id channel yang dipakai
[`publish`](#publish).

```bash
./clip channels
./clip channels --account a1b2c3d4
./clip channels --refresh --json | jq -r '.channels[] | "\(.key) \(.service)"'
```

| Argumen | Arti |
|---|---|
| `--refresh` | Abaikan cache 10 menit dan ambil ulang dari Buffer |
| `--account ID` | Batasi ke satu akun |

Akun yang bermasalah (API key dicabut, kuota habis) muncul sebagai peringatan di `errors`, tanpa
menghentikan akun lain. Paket Free Buffer dibatasi 250 request/hari, karena itu hasilnya di-cache.

---

## publish

Unggah klip ke hosting video, lalu buat post di Buffer. **Perintah ini memposting ke akun media sosial
Anda** — pastikan channel dan waktunya benar sebelum menjalankan.

```bash
./clip publish last a1b2c3d4 --channel a1b2c3d4:ig1
./clip publish last a1b2c3d4 --channel akun1:ig1 --channel akun2:tt9 --mode shareNow
./clip publish last a1b2c3d4 --channel akun1:yt1 --mode customScheduled --at 2026-10-01T09:00:00+07:00
./clip publish last a1b2c3d4 --channel akun1:ig1 --text "Caption sendiri #ai"
```

| Argumen | Default | Arti |
|---|---|---|
| `job`, `clip` | wajib | Proyek dan klip yang diposting |
| `--channel X` | wajib | `idAkun:idChannel` dari [`channels`](#channels). Boleh diulang untuk beberapa channel |
| `--mode` | `addToQueue` | `addToQueue` (antrean Buffer), `shareNext` (slot berikutnya), `shareNow` (langsung), `customScheduled` (butuh `--at`) |
| `--at ISO` | — | Waktu jadwal, mis. `2026-10-01T09:00:00+07:00`. Harus di masa depan |
| `--text "…"` | judul + hook + hashtag | Caption |

Klip diunggah sekali per versi, lalu URL yang sama dipakai untuk semua channel. Instagram dan Facebook
dikirim sebagai Reel; YouTube sebagai video publik dengan judul klip. Kegagalan di satu channel tidak
menghentikan channel lain; kode keluar `1` kalau tidak ada satu pun yang berhasil.
Hosting video (Cloudinary atau Cloudflare R2) harus sudah diatur — cek dengan [`doctor`](#doctor).

---

## publish-status

Status terbaru post yang sudah dikirim (terjadwal → terkirim, beserta link post).

```bash
./clip publish-status last a1b2c3d4
```

Status ditanyakan ke akun Buffer yang memposting masing-masing.

---

## config

Lihat atau ubah pengaturan yang tersimpan di `.env`.

```bash
./clip config                                     # lihat semua (rahasia disamarkan)
./clip config GEMINI_API_KEY                      # nilai dibaca dari stdin — aman
./clip config WHISPER_MODEL large-v3-turbo
```

Tanpa nilai, perintah membaca dari stdin supaya kredensial tidak tersimpan di riwayat shell.
Nilai yang bisa diatur:

| Nama | Isi |
|---|---|
| `AI_PROVIDER` | `gemini`, `anthropic`, atau `openai` |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Kredensial dan model Gemini |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | Kredensial dan model Claude |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | Kredensial dan model ChatGPT |
| `WHISPER_MODEL` | `small`, `medium`, atau `large-v3-turbo` |
| `WHISPER_LANGUAGE` | `auto`, `id`, atau `en` |
| `BUFFER_API_KEY` | Akun Buffer pertama (selanjutnya pakai [`accounts`](#accounts)) |
| `MEDIA_HOST` | `cloudinary` atau `r2` |
| `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` | Hosting Cloudinary |
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_PUBLIC_URL` | Hosting Cloudflare R2 |

---

## serve

Menjalankan antarmuka web (mode yang sama dengan `./run.sh`).

```bash
./clip serve
./clip serve --port 9000
./clip serve --host 0.0.0.0 --port 9000     # bisa diakses dari perangkat lain di jaringan Anda
```

`--port` default `8765` (atau dari variabel `PORT`), `--host` default `127.0.0.1`.
Aplikasi tidak punya login, jadi ganti `--host` hanya di jaringan yang Anda percaya.

---

## Bentuk keluaran JSON

**Proyek** (`jobs`, `show`, `run`, `rerender`):
`id`, `name`, `status`, `stage`, `error`, `created_at`, `options`, `source`, `meta`, `summary`,
`usage`, `clips[]`, dan `logs[]` kalau `--logs`.

- `status`: `queued`, `downloading`, `preparing`, `analyzing`, `rendering`, `done`, `error`
- `meta`: `duration`, `fps`, `width`, `height`, `has_audio`
- `options`: `num_clips`, `min_len`, `max_len`, `aspect`, `layout`, `subtitles`, `remove_silence`,
  `show_title`, `instructions`
- `usage`: `calls`, `prompt_tokens`, `output_tokens`, `cost_usd`

**Klip** (`clips[]`, `cut`):
`id`, `title`, `start`, `end`, `duration`, `duration_out` (durasi setelah jeda dibuang),
`status` (`pending`/`queued`/`rendering`/`ready`/`error`), `error`, `score`, `hook`, `reason`,
`hashtags`, `captions` (jumlah baris subtitle), `file` (path absolut `.mp4`), `srt`, `publish`.

**Hasil posting** (`publish`, `publish-status`):
`status`, `progress`, `error`, `mode`, `due_at`, `started_at`, dan `results[]` berisi
`channel_id`, `channel`, `service`, `account_id`, `account`, `ok`, `post_id`, `status`, `due_at`,
`link`, `error`.

---

## Contoh alur

Proses beberapa video lalu ambil path semua klip yang jadi:

```bash
for f in video/*.mp4; do
  ./clip run "$f" --clips 3 --json > "hasil-$(basename "$f").json" || echo "gagal: $f"
done
jq -r '.clips[] | select(.status == "ready") | .file' hasil-*.json
```

Cek biaya dulu, proses kalau masih masuk anggaran:

```bash
usd=$(./clip estimate podcast.mp4 --json | jq .usd)
awk -v u="$usd" 'BEGIN { exit !(u < 0.5) }' && ./clip run podcast.mp4
```

Potong manual tanpa biaya API, lalu posting ke dua akun sekaligus:

```bash
klip=$(./clip cut podcast.mp4 --start 300 --end 345 --title "Highlight" --json | jq -r .id)
./clip channels --json | jq -r '.channels[] | "\(.key)\t\(.account)\t\(.service)"'
./clip publish last "$klip" --channel akun1:ig1 --channel akun2:tt9 --mode addToQueue
```
