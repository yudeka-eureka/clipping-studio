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
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-outline-variant/60 bg-surface-container-low hover:bg-surface-container text-on-surface text-xs font-semibold cursor-pointer transition-colors"
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
              <span className="eyebrow-dot"></span> WORKSPACE UNTUK KLIP VIDEO
            </p>
            <h1>
              Dari video panjang,
              <br />
              <span>jadi klip</span> untuk ditinjau.
            </h1>
            <p className="hero-lede">
              Masukkan file atau link video, biarkan AI membantu menemukan beberapa kandidat momen,
              lalu tinjau dan render klip yang sesuai kebutuhanmu.
            </p>
            <div className="hero-actions">
              <button className="button button-large" type="button" onClick={handleStartClipping}>
                Mulai clipping <span aria-hidden="true">↗</span>
              </button>
              <a className="watch-link" href="#cara-kerja">
                <span className="play-icon" aria-hidden="true">
                  ▶
                </span>{" "}
                Lihat cara kerjanya
              </a>
            </div>
            <p className="hero-note">
              <span aria-hidden="true">⌁</span> Upload · pilih opsi · tinjau hasil.
            </p>
          </div>

          <div className="hero-visual" aria-label="Preview workflow Clipping Studio" role="img">
            <picture className="hero-screenshot">
              <source media="(max-width: 650px)" srcSet="/landing/workspace-mobile.png" />
              <img
                src="/landing/workspace-desktop.png"
                alt="Workspace Clipping Studio untuk mengunggah video dan mengatur opsi klip"
              />
            </picture>
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
                      <small>PROYEK / PODCAST EP. 24</small>
                      <strong>Beberapa kandidat klip.</strong>
                    </div>
                    <span className="mini-pill">3 untuk ditinjau</span>
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
                          Pembuka yang
                          <br />
                          <b>langsung ke inti</b>
                        </span>
                        <span className="result-duration">00:42</span>
                      </div>
                      <div className="result-card blue">
                        <span className="result-number">02</span>
                        <span className="result-caption">
                          Penjelasan
                          <br />
                          <b>lebih ringkas</b>
                        </span>
                        <span className="result-duration">00:38</span>
                      </div>
                      <div className="result-card peach">
                        <span className="result-number">03</span>
                        <span className="result-caption">
                          Bagian yang
                          <br />
                          <b>layak ditinjau</b>
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
                <b>Subtitle</b>
                <small>Dapat diaktifkan</small>
              </span>
            </div>
            <div className="floating-chip chip-bottom">
              <span className="chip-spark">✦</span>
              <span>
                <b>Kandidat klip</b>
                <small>3 momen untuk ditinjau</small>
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
            <p className="eyebrow">FITUR YANG TERSEDIA</p>
            <h2>
              Dari sumber yang sama,
              <br />
              <span>lebih mudah ditinjau.</span>
            </h2>
            <p>
              Clipping Studio merapikan langkah dari video mentah ke beberapa opsi klip dalam satu
              workspace.
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
                <h3>Dapatkan kandidat momen</h3>
                <p>AI membantu menganalisis video dan memberi beberapa kandidat klip untuk ditinjau.</p>
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
                <h3>Tambahkan subtitle dan judul</h3>
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
                Satu rekaman, <span>beberapa opsi klip.</span>
              </h2>
              <p>
                Mulai dari file lokal atau link yang didukung, lalu pilih format dan opsi render yang
                kamu perlukan.
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
                  PILIHAN +<br />
                  RENDER
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
                <b>Ditinjau sebelum diunduh</b>
              </div>
            </div>
          </div>
        </section>

        <section id="cara-kerja" className="section shell steps-section">
          <div className="section-intro">
            <p className="eyebrow">CARA KERJA</p>
            <h2>
              Tiga langkah dari video
              <br />
              <span>ke klip yang bisa kamu tinjau.</span>
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
                <p>Pantau progres realtime, cek setiap klip, lalu unduh hasil yang sesuai.</p>
            </article>
          </div>
        </section>

        <section className="product-section">
          <div className="shell product-grid">
            <div className="product-copy">
              <p className="eyebrow">WORKSPACE UNTUK PROSES BERULANG</p>
              <h2>
                Satu tempat untuk
                <br />
                <span>mengelola klip.</span>
              </h2>
              <p>
                Mulai proyek, lihat progres, ubah opsi, dan kelola hasil tanpa berpindah-pindah
                konteks.
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
                    AI membantu memilih kandidat momen, lalu klip dirender sesuai opsi proyek. Progres
                    tampil realtime.
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
                  <div className="preview-button">✦ Buat kandidat klip</div>
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
              Siapkan klip dari
              <br />
              <span>video yang sudah kamu punya.</span>
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
        <p>Workspace untuk menemukan, merender, dan meninjau klip video.</p>
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
