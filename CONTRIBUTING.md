# Panduan Kontribusi Clipping Studio

Terima kasih sudah tertarik untuk berkontribusi di **Clipping Studio**

Clipping Studio adalah aplikasi yang membantu pengguna mengubah video panjang menjadi klip pendek untuk TikTok, Instagram Reels, YouTube Shorts, dan platform lainnya.

Dokumen ini menjelaskan cara menyiapkan project, mengikuti aturan Git, dan mengajukan Pull Request agar kontribusi kamu mudah diperiksa dan digabungkan.

## 1. Selamat Datang

Kami menyambut kontribusi berupa:
- Penambahan fitur baru.
- Perbaikan bug.
- Penyempurnaan tampilan dan pengalaman pengguna.
- Perbaikan dokumentasi.
- Penambahan dan perbaikan pengujian.

Sebelum mulai bekerja, periksa daftar [Issues](https://github.com/yudeka-eureka/clipping-studio/issues) untuk menemukan tugas yang tersedia. Jika perlu, diskusikan rencana perubahan terlebih dahulu agar pekerjaan tidak bertabrakan dengan kontributor lain.

## 2. Prasyarat Sistem

Pastikan perangkat kamu memiliki:

- **Python 3.10 atau lebih baru**.
- **Git** untuk mengelola versi kode.
- **Visual Studio Code** atau editor kode lainnya.
- **uv** sebagai pengelola environment yang disarankan, atau `venv` bawaan Python.
- Koneksi internet untuk mengunduh dependensi yang diperlukan.

Untuk memeriksa instalasi, jalankan:

```bash
git --version
python --version
```

Jika perintah `python` tidak tersedia, coba:

```bash
py --version
```

## 3. Langkah Instalasi Lokal

### A. Clone repositori

Jalankan perintah berikut di terminal:

```bash
git clone https://github.com/yudeka-eureka/clipping-studio.git
cd clipping-studio
```

### B. Buat virtual environment

Virtual environment membantu memisahkan dependensi project dari instalasi Python lainnya.

Menggunakan `uv`:

```bash
uv venv
```

Atau menggunakan `venv` bawaan Python:

```bash
python -m venv .venv
```

### C. Aktifkan virtual environment

Untuk Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Untuk Linux atau macOS:

```bash
source .venv/bin/activate
```

Jika PowerShell menolak aktivasi karena kebijakan eksekusi skrip, kamu dapat menggunakan Command Prompt:

```cmd
.venv\Scripts\activate.bat
```

### D. Instal dependensi

Pastikan virtual environment sudah aktif, lalu jalankan:

```bash
python -m pip install -r requirements.txt
```

### E. Siapkan konfigurasi

Buat file `.env` berdasarkan contoh konfigurasi yang tersedia.

Untuk Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Untuk Linux atau macOS:

```bash
cp .env.example .env
```

Isi konfigurasi sesuai kebutuhan. Jangan pernah memasukkan API key, password, atau informasi rahasia ke dalam commit maupun Pull Request.

## 4. Verifikasi Instalasi

Setelah dependensi terpasang, lakukan pemeriksaan berikut.

### A. Diagnosis aplikasi

Jalankan:

```bash
python clip doctor
```

Perintah ini dapat digunakan untuk memeriksa kesiapan lingkungan aplikasi.

### B. Jalankan antarmuka web

Pada lingkungan yang mendukung shell Bash:

```bash
./run.sh
```

Jika berhasil, aplikasi akan membuka antarmuka web di browser. Secara default, alamatnya adalah:

`http://localhost:8765`

Pastikan dependensi dan konfigurasi yang dibutuhkan tersedia sebelum menjalankan aplikasi.

## 5. Standar Alur Git

Setiap kontribusi harus dikerjakan pada branch terpisah. Hindari mengerjakan perubahan langsung di branch `main`.

### A. Perbarui branch utama

Sebelum memulai tugas baru, pastikan branch lokal sudah diperbarui:

```bash
git switch main
git pull origin main
```

### B. Buat branch baru

Gunakan nama branch yang menggambarkan tujuan perubahan.

| Jenis perubahan | Format branch | Contoh |
| --- | --- | --- |
| Fitur baru | `feat/<nama-fitur>` | `feat/export-vtt` |
| Perbaikan bug | `fix/<nama-bug>` | `fix/subtitle-timing` |
| Dokumentasi | `docs/<judul-dokumen>` | `docs/panduan-kontribusi` |
| Pengujian | `test/<nama-pengujian>` | `test/unit-tests` |

Contoh membuat branch dokumentasi:

```bash
git switch -c docs/panduan-kontribusi
```

### C. Simpan perubahan

Periksa file yang berubah:

```bash
git status
```

Tambahkan file yang memang ingin dikirim:

```bash
git add CONTRIBUTING.md
```

Buat commit:

```bash
git commit -m "docs: add contribution guide"
```

Gunakan pesan commit yang singkat, jelas, dan menjelaskan tujuan perubahan.

### D. Push branch ke GitHub

```bash
git push -u origin docs/panduan-kontribusi
```

Untuk tugas berikutnya, ganti nama branch sesuai pekerjaan yang sedang dilakukan.

## 6. Konvensi Pesan Commit

Gunakan format berikut:

`<type>: <deskripsi perubahan>`

Jenis commit yang disarankan:

- `feat:` untuk penambahan fitur.
- `fix:` untuk perbaikan bug.
- `docs:` untuk perubahan dokumentasi.
- `test:` untuk penambahan atau perubahan pengujian.
- `refactor:` untuk perapian kode tanpa mengubah perilaku utama.
- `chore:` untuk pemeliharaan project.

Contoh:

```text
feat: add WebVTT subtitle export
fix: handle invalid video URL
docs: improve installation guide
test: add unit tests for clip selection
```

Gunakan bahasa yang konsisten dan hindari pesan seperti `update`, `fix`, atau `perubahan baru` tanpa penjelasan tambahan.

## 7. Tata Cara Membuat Pull Request

Setelah perubahan selesai dan sudah di-push ke GitHub:

1. Buka halaman repositori Clipping Studio.
2. Pilih menu **Pull requests**.
3. Klik **New pull request**.
4. Pilih `main` sebagai branch tujuan (*base*) dan branch tugas kamu sebagai sumber (*compare*).
5. Periksa daftar perubahan sebelum mengajukan Pull Request.
6. Isi judul dan deskripsi yang menjelaskan tujuan perubahan.
7. Tautkan Issue terkait, misalnya `Fixes #6` jika perubahan tersebut memang menyelesaikan Issue #6.
8. Ajukan Pull Request dan tambahkan reviewer atau assignee sesuai instruksi maintainer.

### Checklist sebelum mengirim Pull Request

- [ ] Perubahan dikerjakan pada branch selain `main`.
- [ ] Nama branch mengikuti konvensi project.
- [ ] Pesan commit menjelaskan perubahan.
- [ ] Instalasi atau pengujian yang relevan sudah diperiksa.
- [ ] Tidak ada file `.env`, API key, password, atau rahasia lain yang ikut ter-commit.
- [ ] Tidak ada video besar atau file sementara dari folder `data/` yang tidak diperlukan.
- [ ] Deskripsi Pull Request menjelaskan perubahan dan cara memverifikasinya.
- [ ] Issue terkait sudah ditautkan jika relevan.
- [ ] Tidak ada konflik dengan branch tujuan.

Jangan menggabungkan Pull Request sendiri kecuali maintainer memang memberi izin.

## 8. Etika Berkontribusi

Agar kolaborasi berjalan baik:

- Gunakan bahasa yang sopan dan mudah dipahami.
- Berikan penjelasan yang jelas saat melaporkan bug.
- Hormati masukan dari reviewer dan kontributor lain.
- Jangan mengirim perubahan yang tidak berkaitan dengan tugas.
- Tanyakan kepada maintainer jika ada persyaratan yang belum jelas.
- Jaga kerahasiaan API key dan data pribadi.

## 9. Bantuan dan Pelaporan Masalah

Jika menemukan bug atau membutuhkan klarifikasi, buka [GitHub Issues](https://github.com/yudeka-eureka/clipping-studio/issues) dan jelaskan masalah yang ditemukan, langkah untuk mereproduksinya, serta hasil yang diharapkan.

Terima kasih telah membantu mengembangkan Clipping Studio. Setiap kontribusi, baik berupa kode, pengujian, maupun dokumentasi, sangat berarti!
