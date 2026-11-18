# Product-First Landing Page Design

## Intent

Membuat landing page Clipping Studio lebih menarik tanpa melebih-lebihkan kemampuan produk. Landing page harus menjelaskan alur nyata: memasukkan video, memilih opsi klip, memantau proses, lalu meninjau dan mengunduh hasil.

## Goals

- Menyampaikan manfaat produk dalam tagline yang singkat dan faktual.
- Menyelaraskan visual landing page dengan workspace yang memakai palet lilac/ungu Material 3.
- Menjadikan preview UI sebagai visual utama, bukan foto stok yang generik atau menyesatkan.
- Mengarahkan pengunjung ke CTA “Mulai clipping” atau “Buka workspace”.
- Menjelaskan kemampuan yang benar-benar tersedia: upload/link video, kandidat klip berbantuan AI, pilihan rasio/layout, subtitle, progres realtime, dan render ulang.

## Non-goals

- Tidak mengubah pipeline backend atau alur autentikasi.
- Tidak menjanjikan performa, viralitas, jumlah view, atau hasil otomatis tanpa tinjauan pengguna.
- Tidak menambahkan foto eksternal baru; mockup UI produk menjadi bukti visual utama.

## Approach

Pendekatan yang dipilih adalah product-first. Struktur landing page yang ada dipertahankan agar navigasi dan anchor tidak rusak, tetapi hero, headline, feature copy, alur kerja, dan product preview dirapikan. Copy menggunakan Bahasa Indonesia yang sederhana dengan istilah teknis seperlunya. Visual menggunakan token warna workspace dan komponen CSS landing yang sudah ada.

## Copy direction

- Tagline utama: “Ubah video panjang menjadi klip yang siap ditinjau.”
- Supporting copy: menjelaskan bahwa AI membantu menemukan kandidat momen dan pengguna tetap meninjau hasil sebelum mengunduh.
- CTA utama: “Mulai clipping”.
- CTA sekunder: “Lihat cara kerja”.
- Hindari kata “viral”, “terbaik”, “otomatis siap posting”, dan klaim hasil pasti.

## Files

- Modify `frontend/src/components/pages/LandingPage.tsx`: copy, label mockup, dan hierarchy konten.
- Modify `frontend/src/styles/landing.css`: treatment hero/product preview agar menyatu dengan design system workspace dan tetap responsif.
- Modify `frontend/src/routes/index.tsx`: metadata title/description agar konsisten dengan copy baru.
- Test existing frontend test suite and production build.

## Acceptance criteria

- Pengunjung langsung memahami fungsi produk dalam satu layar pertama.
- Semua klaim di landing page dapat ditelusuri ke fitur yang ada di workspace/backend.
- CTA tetap membuka autentikasi atau workspace sesuai status pengguna.
- Navigasi anchor `#fitur`, `#cara-kerja`, dan `#faq` tetap berfungsi.
- Tampilan desktop dan mobile tidak overflow horizontal.
- Tidak ada foto eksternal baru yang diperlukan.
