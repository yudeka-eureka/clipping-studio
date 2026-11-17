"""
TOOLS CLIP VIDEO - CONTOH PROGRAM DASAR
=========================================
Fungsi program ini: memotong video panjang jadi klip pendek,
mengubah jadi format tegak (vertikal), dan membuat teks otomatis dari suara.

CARA PAKAI:
1. Install dulu program pendukung. Buka Command Prompt / Terminal, lalu ketik:
   pip install moviepy openai-whisper google-generativeai google-genai yt-dlp

2. Buat API key gratis di Google AI Studio: https://aistudio.google.com/apikey
   (Ini seperti kunci rahasia supaya program bisa memakai AI Gemini)

3. Siapkan video sumber: bisa dari file di komputer, ATAU langsung dari
   link YouTube (lihat BAGIAN 0 di bawah).

4. Ubah bagian "CONTOH PEMAKAIAN" di bawah sesuai kebutuhan, lalu jalankan
   file ini dengan mengetik: python clip_video_starter.py

CATATAN PENTING:
Pakai fitur unduh YouTube ini hanya untuk video milik sendiri, atau video
yang memang boleh diunduh/dipakai ulang (misalnya sudah dapat izin dari
pemiliknya). Mengunduh video orang lain tanpa izin untuk dipakai ulang
bisa melanggar hak cipta dan aturan YouTube.
"""

from moviepy.editor import VideoFileClip
import whisper
import google.generativeai as genai
from google import genai as genai_video
import yt_dlp
import json


# ============================================
# BAGIAN 0: Mengunduh video dari link YouTube
# ============================================
def unduh_video_youtube(url_youtube, nama_output="video_youtube.mp4"):
    """
    Mengunduh video dari YouTube berdasarkan link yang diberikan.
    Contoh: unduh_video_youtube("https://youtube.com/watch?v=xxxxx", "podcast.mp4")
    """
    opsi = {
        "format": "best[ext=mp4]/best",
        "outtmpl": nama_output,
    }
    with yt_dlp.YoutubeDL(opsi) as ydl:
        ydl.download([url_youtube])
    print(f"Selesai! Video sudah diunduh ke: {nama_output}")


# ============================================
# BAGIAN 1: Memotong video jadi klip pendek
# ============================================
def potong_video(file_video, waktu_mulai, waktu_selesai, nama_output):
    """
    Memotong video dari waktu_mulai sampai waktu_selesai (dalam satuan detik).
    Contoh: potong_video("podcast.mp4", 60, 90, "klip1.mp4")
    Artinya: ambil video dari detik ke-60 sampai detik ke-90.
    """
    video = VideoFileClip(file_video)
    klip = video.subclip(waktu_mulai, waktu_selesai)
    klip.write_videofile(nama_output, codec="libx264", audio_codec="aac")
    video.close()
    print(f"Selesai! Klip disimpan di: {nama_output}")


# ============================================
# BAGIAN 2: Mengubah video jadi format tegak (vertikal)
# Berguna kalau klip mau diunggah ke TikTok, Reels, atau Shorts
# ============================================
def ubah_ke_vertikal(file_video, nama_output):
    video = VideoFileClip(file_video)
    lebar_baru = int(video.h * 9 / 16)
    video_vertikal = video.crop(
        x_center=video.w / 2,
        width=lebar_baru,
        height=video.h,
    )
    video_vertikal.write_videofile(nama_output, codec="libx264", audio_codec="aac")
    video.close()
    print(f"Selesai! Video tegak disimpan di: {nama_output}")


# ============================================
# BAGIAN 3: Membuat teks otomatis dari suara (transkrip)
# Berguna untuk mencari bagian video yang menarik
# tanpa harus menonton ulang dari awal
# ============================================
def buat_transkrip(file_video):
    model = whisper.load_model("base")
    hasil = model.transcribe(file_video)
    for bagian in hasil["segments"]:
        mulai = round(bagian["start"], 1)
        selesai = round(bagian["end"], 1)
        teks = bagian["text"]
        print(f"[{mulai} detik - {selesai} detik] {teks}")
    return hasil["segments"]


# ============================================
# BAGIAN 4: Mencari bagian video paling menarik
# secara OTOMATIS pakai AI Gemini
# ============================================
def cari_bagian_menarik_pakai_gemini(segments, api_key, jumlah_klip=3):
    """
    AI Gemini akan membaca transkrip, lalu memilih sendiri bagian mana
    yang paling menarik untuk dijadikan klip pendek.
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    # Gabungkan semua transkrip jadi satu teks, lengkap dengan waktunya
    teks_transkrip = ""
    for bagian in segments:
        teks_transkrip += f"[{bagian['start']:.1f} detik - {bagian['end']:.1f} detik] {bagian['text']}\n"

    prompt = f"""
Berikut ini transkrip sebuah video, lengkap dengan waktu dalam detik:

{teks_transkrip}

Tugas kamu: pilih {jumlah_klip} bagian paling menarik, seru, atau penting
dari video ini untuk dijadikan klip pendek di TikTok/Reels/Shorts.
Setiap klip sebaiknya berdurasi 30 sampai 90 detik.

Jawab HANYA dalam format JSON seperti contoh ini, tanpa kalimat tambahan apa pun:
[
  {{"mulai": 12.5, "selesai": 55.0, "alasan": "alasan singkat kenapa bagian ini menarik"}}
]
"""

    respons = model.generate_content(prompt)
    teks_hasil = respons.text.strip()

    # Membersihkan hasil, kalau-kalau Gemini menambahkan tanda ```json
    teks_hasil = teks_hasil.replace("```json", "").replace("```", "").strip()

    daftar_klip = json.loads(teks_hasil)
    return daftar_klip


# ============================================
# BAGIAN 5: (CARA BARU, LEBIH AKURAT)
# Gemini langsung MENONTON video aslinya
# Bisa langsung pakai link YouTube, tidak perlu diunduh dulu!
# Ini pakai fitur "agentic video understanding" dari Google (rilis Sept 2026)
# ============================================
def cari_bagian_menarik_dari_video_asli(url_atau_file_video, api_key, jumlah_klip=3):
    """
    Bedanya dengan cara sebelumnya: di sini Gemini benar-benar menonton
    videonya (gambar + suara), bukan cuma baca teks transkrip.
    Jadi hasilnya lebih akurat, dan bisa langsung pakai link YouTube
    tanpa perlu diunduh dulu.

    Contoh pakai link YouTube:
    cari_bagian_menarik_dari_video_asli("https://youtu.be/xxxxx", api_key)
    """
    client = genai_video.Client(api_key=api_key)

    prompt = f"""
Tonton video ini dari awal sampai akhir.
Tugas kamu: pilih {jumlah_klip} bagian paling menarik, seru, atau penting
dari video ini untuk dijadikan klip pendek di TikTok/Reels/Shorts.
Setiap klip sebaiknya berdurasi 30 sampai 90 detik.

Jawab HANYA dalam format JSON seperti contoh ini, tanpa kalimat tambahan apa pun:
[
  {{"mulai": 12.5, "selesai": 55.0, "alasan": "alasan singkat kenapa bagian ini menarik"}}
]
"""

    interaction = client.interactions.create(
        model="gemini-3.7-flash",
        input=[
            {"type": "video", "uri": url_atau_file_video, "processing": "agentic"},
            {"type": "text", "text": prompt},
        ],
    )

    teks_hasil = interaction.output_text.strip()
    teks_hasil = teks_hasil.replace("```json", "").replace("```", "").strip()
    daftar_klip = json.loads(teks_hasil)
    return daftar_klip


# ============================================
# CONTOH PEMAKAIAN
# ============================================
if __name__ == "__main__":
    file_sumber = "podcast.mp4"  # nama file video yang akan diproses
    url_youtube = "https://youtube.com/watch?v=xxxxx"  # ganti dengan link video Anda
    api_key_gemini = "MASUKKAN_API_KEY_GEMINI_ANDA_DI_SINI"

    # ---------------------------------------------------------
    # CARA BARU (disarankan): kalau video sumbernya dari YouTube,
    # Gemini bisa langsung menonton videonya tanpa perlu diunduh dulu.
    # Untuk ini, kita tetap perlu mengunduh videonya SATU KALI supaya
    # nanti bisa dipotong jadi klip pendek (unduh hanya untuk video
    # milik sendiri / yang boleh dipakai ulang).
    # ---------------------------------------------------------
    unduh_video_youtube(url_youtube, file_sumber)
    daftar_klip = cari_bagian_menarik_dari_video_asli(url_youtube, api_key_gemini, jumlah_klip=3)

    # ---------------------------------------------------------
    # CARA LAMA (kalau video dari file lokal, bukan YouTube):
    # hapus tanda # di 2 baris bawah untuk memakainya
    # ---------------------------------------------------------
    # segments = buat_transkrip(file_sumber)
    # daftar_klip = cari_bagian_menarik_pakai_gemini(segments, api_key_gemini, jumlah_klip=3)

    # Langkah terakhir: potong video sesuai pilihan AI, lalu ubah jadi format tegak
    for nomor, klip in enumerate(daftar_klip, start=1):
        print(f"Klip {nomor}: {klip['alasan']}")
        nama_file = f"klip{nomor}.mp4"
        potong_video(file_sumber, klip["mulai"], klip["selesai"], nama_file)
        ubah_ke_vertikal(nama_file, f"klip{nomor}_vertikal.mp4")
