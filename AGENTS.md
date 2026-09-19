# Clipping Studio untuk AI agent

Semua fitur tersedia lewat satu perintah: `./clip <perintah>` (tanpa perlu membuka web).
Tambahkan `--json` agar hasil terstruktur ditulis ke **stdout**; progres dan log selalu ke **stderr**,
jadi stdout aman di-pipe. Kode keluar: `0` berhasil, `1` gagal (JSON berisi `{"ok": false, "error": "..."}`).

## Alur khas

```bash
./clip doctor --json                                   # cek ffmpeg, model, API key, hosting
./clip estimate video.mp4 --json                       # perkiraan token & biaya sebelum proses
./clip run video.mp4 --clips 3 --json                  # AI pilih momen → render semua klip
./clip show last --json                                # hasil terakhir: path file .mp4 & .srt per klip
./clip publish <job> <clip> --channel <id> --mode addToQueue --json
```

`run` menerima file lokal maupun link (YouTube dll). Hasil `--json` memuat `clips[].file`
(path absolut .mp4), `clips[].srt`, `duration_out` (durasi setelah jeda diam dibuang),
`score`, `hook`, `hashtags`, dan `usage` (token + biaya Gemini).

## Daftar perintah

| Perintah | Kegunaan |
|---|---|
| `doctor` | Status ffmpeg, mediapipe, model Whisper, API key, hosting video |
| `run SOURCE` | Pipeline penuh: unduh/salin → AI pilih klip → render |
| `cut SOURCE --start X --end Y` | Potong satu klip tanpa AI (`--job ID` memakai video proyek yang ada) |
| `rerender JOB [CLIP...]` | Render ulang dengan `--aspect`, `--layout`, `--start/--end`, `--title` |
| `jobs`, `show JOB`, `rm JOB` | Daftar / detail (`--logs`) / hapus proyek. `JOB` boleh awalan id atau `last` |
| `transcribe SOURCE` | Transkrip Whisper lokal, `--format text\|srt\|json` (json = waktu per kata) |
| `estimate SOURCE` | Perkiraan token & biaya Gemini |
| `usage` | Token & biaya yang sudah terpakai per proyek |
| `channels` | Daftar channel dari semua akun Buffer (`--account ID` untuk satu akun) |
| `accounts` | Kelola akun Buffer: `--add [--label X]` (key dari stdin), `--rename ID --label X`, `--remove ID` |
| `publish JOB CLIP --channel idAkun:idChannel` | Unggah klip ke hosting lalu buat post di Buffer (boleh lintas akun) |
| `publish-status JOB CLIP` | Status terbaru post di Buffer |
| `provider [gemini\|anthropic\|openai] [--model M]` | Lihat / ganti penyedia AI pemilih klip |
| `branding [--logo F] [--outro F] [--position P] [--size N] [--opacity N] [--outro-duration N]` | Logo watermark & penutup klip; `--logo-off`, `--remove-outro`, dst. |
| `config [NAMA [NILAI]]` | Lihat/ubah `.env`. Tanpa NILAI, dibaca dari stdin (aman untuk kredensial) |
| `serve --port 8765` | Jalankan antarmuka web |

Opsi klip (berlaku di `run` dan `cut`): `--clips N`, `--min-len`, `--max-len`,
`--aspect 9:16|1:1|4:5|16:9|original`, `--layout face|crop|blur`, `--instructions "..."`,
`--no-subtitles`, `--no-trim` (pertahankan jeda diam), `--no-title`, `--link` (hardlink file sumber).

## Catatan penting

- `run` memakai API berbayar dari penyedia yang aktif (Gemini, Claude, atau ChatGPT). Cek biaya dengan `estimate` dulu.
- Claude & ChatGPT tidak menerima video: klip dipilih dari transkrip Whisper lokal + sampel frame, jadi `run` butuh waktu transkripsi dulu dan tidak bisa dipakai untuk video tanpa suara.
- `publish` **mengirim konten ke akun media sosial pengguna**. Minta konfirmasi pengguna sebelum menjalankannya,
  dan gunakan `--mode addToQueue` (masuk antrean, bisa dibatalkan di Buffer) daripada `shareNow`.
- `rm` menghapus video sumber dan semua klip proyek tanpa bisa dibatalkan.
- Kredensial ada di `.env`; jangan tulis nilainya ke argumen perintah (`config NAMA` membaca dari stdin).
- Data proyek ada di `data/jobs/<job-id>/`. Kalau web app sedang berjalan, perubahan dari CLI baru terlihat setelah web app di-restart.
