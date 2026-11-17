import { useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { useAuth } from "@/lib/auth-context";
import { useI18n } from "@/lib/i18n";

export function LandingPage() {
  const { user, openAuthModal } = useAuth();
  const { locale, toggleLocale } = useI18n();
  const navigate = useNavigate();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  const handleStartClipping = () => {
    if (user) {
      navigate({ to: "/app" });
    } else {
      openAuthModal("signin");
    }
  };

  const handleOpenAuth = (mode: "signin" | "register" = "signin") => {
    openAuthModal(mode);
    setMobileNavOpen(false);
  };

  return (
    <div className="landing-page">
      <header className="site-header">
        <Link className="wordmark" to="/" aria-label="Clipping Studio beranda">
          <span className="wordmark-mark" aria-hidden="true">
            <span></span>
            <span></span>
            <span></span>
          </span>
          <span>
            Clipping <em>Studio</em>
          </span>
        </Link>

        <nav className="desktop-nav" aria-label="Navigasi utama">
          <a href="#fitur">Fitur</a>
          <a href="#cara-kerja">Cara kerja</a>
          <a href="#faq">FAQ</a>
        </nav>

        <div className="header-actions">
          <button
            onClick={toggleLocale}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-white/20 bg-white/5 hover:bg-white/10 text-white text-xs font-semibold cursor-pointer transition-colors"
            type="button"
            title={locale === "id" ? "Switch to English" : "Ganti ke Bahasa Indonesia"}
          >
            <span className="material-symbols-outlined text-[15px] text-violet-400">translate</span>
            <span>{locale.toUpperCase()}</span>
          </button>
          {user ? (
            <Link className="text-link" to="/app">
              Halo, <strong>{user.display_name || user.username}</strong>
            </Link>
          ) : (
            <button className="text-link" type="button" onClick={() => handleOpenAuth("signin")}>
              Masuk
            </button>
          )}
          <button className="button button-small" type="button" onClick={handleStartClipping}>
            {user ? "Buka workspace" : "Mulai clipping"} <span aria-hidden="true">↗</span>
          </button>
        </div>

        <button
          className="menu-toggle"
          type="button"
          aria-expanded={mobileNavOpen}
          aria-controls="mobile-nav"
          aria-label="Buka navigasi"
          onClick={() => setMobileNavOpen((v) => !v)}
        >
          <span></span>
          <span></span>
        </button>

        <nav
          id="mobile-nav"
          className={`mobile-nav ${mobileNavOpen ? "open" : ""}`}
          aria-label="Navigasi mobile"
        >
          <a href="#fitur" onClick={() => setMobileNavOpen(false)}>
            Fitur
          </a>
          <a href="#cara-kerja" onClick={() => setMobileNavOpen(false)}>
            Cara kerja
          </a>
          <a href="#faq" onClick={() => setMobileNavOpen(false)}>
            FAQ
          </a>
          <button
            onClick={toggleLocale}
            className="text-link flex items-center gap-1.5 py-1 text-left"
            type="button"
          >
            <span className="material-symbols-outlined text-[16px] text-violet-400">translate</span>
            <span>
              Language: <strong>{locale === "id" ? "Bahasa Indonesia" : "English"}</strong>
            </span>
          </button>
          {user ? (
            <Link to="/app" onClick={() => setMobileNavOpen(false)} className="text-link">
              Buka workspace (@{user.username})
            </Link>
          ) : (
            <button className="text-link" type="button" onClick={() => handleOpenAuth("signin")}>
              Masuk
            </button>
          )}
          <button
            className="button"
            type="button"
            onClick={() => {
              setMobileNavOpen(false);
              handleStartClipping();
            }}
          >
            {user ? "Buka workspace" : "Mulai clipping"} <span aria-hidden="true">↗</span>
          </button>
        </nav>
      </header>

      <main>
        <section className="hero shell">
          <div className="hero-copy">
            <p className="eyebrow">
              <span className="eyebrow-dot"></span> LOCAL WORKSPACE UNTUK KREATOR VIDEO
            </p>
            <h1>
              Satu video panjang.
              <br />
              <span>Banyak konten</span> siap posting.
            </h1>
            <p className="hero-lede">
              Ubah video panjang menjadi klip pendek untuk TikTok, Instagram Reels, dan YouTube
              Shorts dengan workflow yang lebih praktis—langsung dari komputer kamu.
            </p>
            <div className="hero-actions">
              <button className="button button-large" type="button" onClick={handleStartClipping}>
                Coba clipping sekarang <span aria-hidden="true">↗</span>
              </button>
              <a className="watch-link" href="#cara-kerja">
                <span className="play-icon" aria-hidden="true">
                  ▶
                </span>{" "}
                Lihat cara kerjanya
              </a>
            </div>
            <p className="hero-note">
              <span aria-hidden="true">⌁</span> Proses lokal · Gemini API · progres realtime.
            </p>
          </div>

          <div className="hero-visual" aria-label="Preview workflow Clipping Studio" role="img">
            <div className="visual-glow"></div>
            <div className="window-card">
              <div className="window-topbar">
                <span className="window-dots">
                  <i></i>
                  <i></i>
                  <i></i>
                </span>
                <span className="window-label">
                  clipping studio <b>·</b> workspace
                </span>
                <span className="window-status">
                  <i></i> realtime
                </span>
              </div>
              <div className="window-body">
                <aside className="mini-sidebar">
                  <div className="mini-logo">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                  <div className="mini-line active"></div>
                  <div className="mini-line"></div>
                  <div className="mini-line short"></div>
                  <div className="mini-line"></div>
                </aside>
                <div className="mini-main">
                  <div className="mini-heading">
                    <div>
                      <small>PROJECT / PODCAST EP. 24</small>
                      <strong>Temukan momen terbaikmu.</strong>
                    </div>
                    <span className="mini-pill">3 klip siap</span>
                  </div>
                  <div className="source-preview">
                    <div className="source-overlay">
                      <span className="source-tag">VIDEO SUMBER</span>
                      <span className="source-title">
                        The craft of
                        <br />
                        <b>making ideas move</b>
                      </span>
                      <span className="source-time">12:48 / 48:20</span>
                    </div>
                    <div className="source-wave">
                      <i></i>
                      <i></i>
                      <i></i>
                      <i></i>
                      <i></i>
                      <i></i>
                      <i></i>
                      <i></i>
                      <i></i>
                      <i></i>
                      <i></i>
                      <i></i>
                      <i></i>
                      <i></i>
                      <i></i>
                      <i></i>
                      <i></i>
                      <i></i>
                      <i></i>
                    </div>
                    <span className="source-head"></span>
                  </div>
                  <div className="mini-results">
                    <div className="result-title">
                      <span>HASIL PILIHAN AI</span>
                      <em>3 momen ditemukan</em>
                    </div>
                    <div className="result-cards">
                      <div className="result-card purple">
                        <span className="result-number">01</span>
                        <span className="result-caption">
                          The hook that
                          <br />
                          <b>changes everything</b>
                        </span>
                        <span className="result-duration">00:42</span>
                      </div>
                      <div className="result-card blue">
                        <span className="result-number">02</span>
                        <span className="result-caption">
                          A better way
                          <br />
                          <b>to start</b>
                        </span>
                        <span className="result-duration">00:38</span>
                      </div>
                      <div className="result-card peach">
                        <span className="result-number">03</span>
                        <span className="result-caption">
                          Make it
                          <br />
                          <b>memorable</b>
                        </span>
                        <span className="result-duration">00:51</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div className="floating-chip chip-top">
              <span className="chip-check">✓</span>
              <span>
                <b>Subtitle otomatis</b>
                <small>Siap ditinjau</small>
              </span>
            </div>
            <div className="floating-chip chip-bottom">
              <span className="chip-spark">✦</span>
              <span>
                <b>AI menemukan momen</b>
                <small>3 klip · 01:42 total</small>
              </span>
            </div>
          </div>
        </section>

        <section className="proof-strip shell" aria-label="Fokus produk">
          <span>DIBUAT UNTUK</span>
          <strong>podcaster</strong>
          <strong>content creator</strong>
          <strong>tim media</strong>
          <strong>video edukasi</strong>
        </section>

        <section id="fitur" className="section shell">
          <div className="section-intro">
            <p className="eyebrow">BUKAN SEKADAR POTONG VIDEO</p>
            <h2>
              Lebih banyak momen.
              <br />
              <span>Lebih sedikit pekerjaan repetitif.</span>
            </h2>
            <p>
              Clipping Studio membantu kamu berpindah dari video mentah ke beberapa opsi klip tanpa
              bolak-balik antar tools.
            </p>
          </div>
          <div className="feature-grid">
            <article className="feature-card feature-featured">
              <div className="feature-icon icon-violet">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M4 5.5h16M4 12h10M4 18.5h16" />
                  <path d="m17 9 3 3-3 3" />
                </svg>
              </div>
              <div>
                <h3>Temukan momen yang layak dibagikan</h3>
                <p>AI menganalisis video dan memberi beberapa kandidat klip untuk kamu tinjau.</p>
              </div>
              <span className="feature-index">01</span>
            </article>
            <article className="feature-card">
              <div className="feature-icon icon-blue">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <rect x="3.5" y="5" width="17" height="14" rx="2" />
                  <path d="m10 9 5 3-5 3z" />
                </svg>
              </div>
              <div>
                <h3>Atur format untuk tiap channel</h3>
                <p>Pilih rasio 9:16, 1:1, 4:5, 16:9, atau pertahankan format asli.</p>
              </div>
              <span className="feature-index">02</span>
            </article>
            <article className="feature-card">
              <div className="feature-icon icon-orange">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M5 7h14M5 12h9M5 17h14" />
                  <path d="M17 10v4M15 12h4" />
                </svg>
              </div>
              <div>
                <h3>Subtitle dan judul lebih siap</h3>
                <p>
                  Aktifkan subtitle, judul di atas video, dan penghapusan jeda sesuai kebutuhan.
                </p>
              </div>
              <span className="feature-index">03</span>
            </article>
          </div>
        </section>

        <section className="transform-section">
          <div className="shell">
            <div className="section-intro centered">
              <p className="eyebrow">DARI SATU SUMBER</p>
              <h2>
                Satu rekaman, <span>beberapa pintu masuk.</span>
              </h2>
              <p>
                Mulai dari file video lokal atau link video, lalu siapkan output sesuai format yang
                kamu butuhkan.
              </p>
            </div>
            <div className="transform-flow">
              <div className="flow-source">
                <span className="flow-label">VIDEO PANJANG</span>
                <div className="flow-video">
                  <span className="flow-play">▶</span>
                  <div className="flow-bars">
                    <i></i>
                    <i></i>
                    <i></i>
                    <i></i>
                    <i></i>
                    <i></i>
                    <i></i>
                    <i></i>
                  </div>
                </div>
                <b>Podcast / webinar / tutorial</b>
              </div>
              <div className="flow-arrow">
                <span></span>
                <b>
                  AI +<br />
                  workflow
                </b>
                <span></span>
              </div>
              <div className="flow-outputs">
                <span className="flow-label">KLIP PENDEK</span>
                <div className="output-row">
                  <div className="output-card output-one">
                    <small>01</small>
                    <b>Hook</b>
                    <em>9:16</em>
                  </div>
                  <div className="output-card output-two">
                    <small>02</small>
                    <b>Insight</b>
                    <em>9:16</em>
                  </div>
                  <div className="output-card output-three">
                    <small>03</small>
                    <b>Takeaway</b>
                    <em>9:16</em>
                  </div>
                </div>
                <b>Siap ditinjau dan dirender</b>
              </div>
            </div>
          </div>
        </section>

        <section id="cara-kerja" className="section shell steps-section">
          <div className="section-intro">
            <p className="eyebrow">CARA KERJA</p>
            <h2>
              Tiga langkah untuk kembali
              <br />
              <span>fokus pada ceritamu.</span>
            </h2>
          </div>
          <div className="steps-grid">
            <article className="step">
              <span className="step-number">01</span>
              <div className="step-line"></div>
              <h3>Masukkan video</h3>
              <p>Upload file dari komputer atau gunakan link video yang didukung aplikasi.</p>
            </article>
            <article className="step">
              <span className="step-number">02</span>
              <div className="step-line"></div>
              <h3>Atur kebutuhanmu</h3>
              <p>Tentukan jumlah klip, durasi, rasio, layout, subtitle, dan opsi render.</p>
            </article>
            <article className="step">
              <span className="step-number">03</span>
              <div className="step-line"></div>
              <h3>Tinjau hasilnya</h3>
              <p>Pantau progres realtime, cek setiap klip, lalu unduh hasil yang paling pas.</p>
            </article>
          </div>
        </section>

        <section className="product-section">
          <div className="shell product-grid">
            <div className="product-copy">
              <p className="eyebrow">WORKSPACE YANG SUDAH KAMU KENAL</p>
              <h2>
                Semua yang kamu butuhkan
                <br />
                <span>ada di satu tempat.</span>
              </h2>
              <p>
                Dashboard Clipping Studio dibuat untuk proses yang berulang: mulai proyek, lihat
                progres, edit opsi, dan kelola hasil tanpa kehilangan konteks.
              </p>
              <button className="button" type="button" onClick={handleStartClipping}>
                Buka workspace <span aria-hidden="true">↗</span>
              </button>
              <div className="product-list">
                <span>✓ Upload file atau link video</span>
                <span>✓ Progres pemrosesan realtime</span>
                <span>✓ Editor klip dan render ulang</span>
              </div>
            </div>
            <div className="product-window">
              <div className="product-top">
                <span className="product-brand">
                  <i></i> Clipping Studio <em>· Gemini API</em>
                </span>
                <span className="product-dot"></span>
              </div>
              <div className="product-content">
                <div className="product-side">
                  <b>PROYEK</b>
                  <span className="selected">+ Proyek baru</span>
                  <span>Podcast Ep. 24</span>
                  <span>Webinar Mei</span>
                  <span>Video tutorial</span>
                </div>
                <div className="product-panel">
                  <small>PROYEK BARU</small>
                  <h3>Buat klip dari video panjang</h3>
                  <p>
                    AI memilih momen terbaik, lalu klip dirender di komputer ini. Progres tampil
                    realtime.
                  </p>
                  <div className="drop-preview">
                    <strong>↑</strong>
                    <span>Tarik video ke sini atau klik untuk memilih</span>
                    <small>MP4 · MOV · MKV · WEBM</small>
                  </div>
                  <div className="settings-preview">
                    <span>
                      Jumlah klip <b>3</b>
                    </span>
                    <span>
                      Rasio <b>9:16</b>
                    </span>
                    <span>
                      Subtitle <b className="toggle-on">ON</b>
                    </span>
                  </div>
                  <div className="preview-button">✦ Mulai proses</div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="faq" className="section shell faq-section">
          <div className="section-intro">
            <p className="eyebrow">FAQ</p>
            <h2>
              Pertanyaan yang sering
              <br />
              <span>muncul sebelum mulai.</span>
            </h2>
          </div>
          <div className="faq-list">
            <details open>
              <summary>
                Apa itu Clipping Studio?<span>+</span>
              </summary>
              <p>
                Clipping Studio adalah workspace untuk mengubah video panjang menjadi beberapa klip
                pendek. Kamu bisa mengatur kebutuhan clipping, memantau progres, dan meninjau hasil
                dari satu aplikasi.
              </p>
            </details>
            <details>
              <summary>
                Bagaimana cara memulai?<span>+</span>
              </summary>
              <p>
                Klik “Mulai clipping”, masukkan file video atau link yang didukung, lalu atur jumlah
                klip, durasi, rasio, dan opsi yang kamu perlukan.
              </p>
            </details>
            <details>
              <summary>
                Format video apa yang bisa digunakan?<span>+</span>
              </summary>
              <p>
                Workspace saat ini menerima kontainer video yang didukung aplikasi, termasuk MP4,
                MOV, MKV, dan WEBM. Validasi file dilakukan saat upload.
              </p>
            </details>
            <details>
              <summary>
                Apakah subtitle otomatis tersedia?<span>+</span>
              </summary>
              <p>
                Ya. Subtitle dapat diaktifkan dari pengaturan proyek dan diproses secara lokal
                menggunakan workflow transkripsi yang tersedia di aplikasi.
              </p>
            </details>
            <details>
              <summary>
                Apakah saya harus mengirim video ke layanan lain?<span>+</span>
              </summary>
              <p>
                Untuk workflow lokal, pemrosesan dilakukan di komputer yang menjalankan Clipping
                Studio. Konfigurasi penyedia AI tetap mengikuti pengaturan aplikasi.
              </p>
            </details>
          </div>
        </section>

        <section className="final-cta shell">
          <div>
            <p className="eyebrow">WAKTUNYA MEMBUAT LEBIH BANYAK</p>
            <h2>
              Jangan biarkan momen bagus
              <br />
              <span>berhenti di timeline.</span>
            </h2>
            <p>Mulai dari satu video yang sudah kamu punya.</p>
          </div>
          <button className="button button-large" type="button" onClick={handleStartClipping}>
            Mulai clipping <span aria-hidden="true">↗</span>
          </button>
        </section>
      </main>

      <footer className="site-footer shell">
        <Link className="wordmark" to="/">
          <span className="wordmark-mark" aria-hidden="true">
            <span></span>
            <span></span>
            <span></span>
          </span>
          <span>
            Clipping <em>Studio</em>
          </span>
        </Link>
        <p>Workflow yang lebih praktis untuk membuat konten pendek.</p>
        <div>
          <a href="#fitur">Fitur</a>
          <a href="#cara-kerja">Cara kerja</a>
          <a href="#faq">FAQ</a>
          {user ? (
            <Link to="/app">Workspace</Link>
          ) : (
            <button className="text-link" type="button" onClick={() => handleOpenAuth("signin")}>
              Masuk
            </button>
          )}
          <Link to="/app">Buka aplikasi</Link>
        </div>
        <small>© 2026 Clipping Studio</small>
      </footer>
    </div>
  );
}
