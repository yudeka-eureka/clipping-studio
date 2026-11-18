import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";

export type Locale = "id" | "en";

export interface Translations {
  common: {
    save: string;
    cancel: string;
    loading: string;
    error: string;
    success: string;
    retry: string;
    delete: string;
    close: string;
    back: string;
    or: string;
    active: string;
    guest: string;
    processing: string;
  };
  header: {
    studio: string;
    pipelineSubtitle: string;
    exportPresets: string;
    personalWorkspace: string;
    notifications: string;
    appearance: string;
    switchLang: string;
    currentLang: string;
  };
  sidebar: {
    studio: string;
    clips: string;
    recents: string;
    noProjects: string;
    uploadToStart: string;
    settings: string;
    signOut: string;
    signIn: string;
  };
  upload: {
    step1: string;
    step1Title: string;
    tabFile: string;
    tabUrl: string;
    dropPrompt: string;
    dropSub: string;
    browseFiles: string;
    urlPlaceholder: string;
    importUrl: string;
    step2: string;
    step2Title: string;
    showAdvanced: string;
    hideAdvanced: string;
    targetDuration: string;
    durationSub: string;
    optimalShorts: string;
    optimalReels: string;
    extendedClip: string;
    durationMax: string;
    targetClips: string;
    targetClipsDesc: string;
    decrease5: string;
    decrease1: string;
    increase1: string;
    increase5: string;
    aspectRatio: string;
    aspectDesc: string;
    customCropOverride: string;
    widthPx: string;
    heightPx: string;
    computedRatio: string;
    presetResolutions: string;
    speakerTracking: string;
    smartFaceTracking: string;
    smartFaceDesc: string;
    centerCrop: string;
    centerCropDesc: string;
    bRoll: string;
    bRollDesc: string;
    audioPacing: string;
    removeSilence: string;
    removeSilenceDesc: string;
    viralityThreshold: string;
    viralityDesc: string;
    viralityLoose: string;
    viralityRecommended: string;
    viralityStrict: string;
    targetPlatform: string;
    smartReframe: string;
    step3: string;
    step3Title: string;
    clipObjective: string;
    pacingHeuristic: string;
    strategyTitle: string;
    captionStyleTitle: string;
    instructionsTitle: string;
    instructionsLabel: string;
    instructionsPlaceholder: string;
    captionStyling: string;
    startProcessing: string;
    viewQueue: string;
  };
  clips: {
    title: string;
    noJob: string;
    noJobDesc: string;
    openStudio: string;
    newProject: string;
    publishSocials: string;
    viralityScore: string;
    timecodeAdjust: string;
    inPoint: string;
    outPoint: string;
    rerender: string;
    downloadClip: string;
    downloadZip: string;
    captionsSync: string;
    all: string;
    viral: string;
    hook: string;
    broll: string;
    masterPlayer: string;
    clipTimeline: string;
    captionStyle: string;
    faceTracking: string;
    exportZip: string;
    generatedClips: string;
    ready: string;
    processing: string;
    rerenderBtn: string;
    resetBtn: string;
  };
  settings: {
    badge: string;
    version: string;
    title: string;
    subtitle: string;
    discard: string;
    save: string;
    saveSuccess: string;
    profile: string;
    profileTitle: string;
    profileSubtitle: string;
    changeAvatar: string;
    avatarHint: string;
    displayName: string;
    email: string;
    accountSecurity: string;
    password: string;
    changePassword: string;
    credentialToken: string;
    credentialTokenHint: string;
    regenerateToken: string;
    copyToken: string;
    copied: string;
    aiModels: string;
    aiModelsTitle: string;
    aiModelsSubtitle: string;
    provider: string;
    modelVersion: string;
    refreshModels: string;
    apiKey: string;
    configureKey: string;
    testConnection: string;
    testing: string;
    connected: string;
    pipeline: string;
    pipelineTitle: string;
    pipelineSubtitle: string;
    defaultResolution: string;
    audioEngine: string;
    audioEngineSub: string;
    whisperModel: string;
    autoCaptions: string;
    autoCaptionsSub: string;
    cloudStorage: string;
    cloudStorageSub: string;
    storageProvider: string;
    localStorage: string;
    retentionPeriod: string;
    retentionSub: string;
    socialBuffer: string;
    socialBufferSub: string;
    bufferAccount: string;
    connectBuffer: string;
  };
  dialogs: {
    apiKey: {
      saveKey: string;
      saving: string;
      removeKey: string;
      replaceKey: string;
      detectKey: string;
      storedEncrypted: string;
      pastePrompt: string;
    };
    changePassword: {
      title: string;
      desc: string;
      oldPassword: string;
      newPassword: string;
      confirmPassword: string;
      submit: string;
      submitting: string;
    };
  };
}

const translations: Record<Locale, Translations> = {
  id: {
    common: {
      save: "Simpan",
      cancel: "Batal",
      loading: "Memuat...",
      error: "Terjadi kesalahan",
      success: "Berhasil",
      retry: "Coba Lagi",
      delete: "Hapus",
      close: "Tutup",
      back: "Kembali",
      or: "atau",
      active: "Aktif",
      guest: "Tamu",
      processing: "Memproses...",
    },
    header: {
      studio: "Studio",
      pipelineSubtitle: "Pipeline Pemrosesan & Klip Video",
      exportPresets: "Expor Preset",
      personalWorkspace: "Workspace Pribadi",
      notifications: "Notifikasi",
      appearance: "Tampilan",
      switchLang: "Ganti ke Bahasa Inggris (Switch to English)",
      currentLang: "ID",
    },
    sidebar: {
      studio: "Studio",
      clips: "Klip",
      recents: "Terbaru",
      noProjects: "Belum ada proyek.",
      uploadToStart: "Unggah video untuk mulai.",
      settings: "Pengaturan",
      signOut: "Keluar",
      signIn: "Masuk",
    },
    upload: {
      step1: "1",
      step1Title: "Sumber Video Mentah",
      tabFile: "Upload File Video",
      tabUrl: "Link Video (YouTube)",
      dropPrompt: "Tarik & letakkan video panjang di sini",
      dropSub: "Format MP4, MOV, MKV, atau WebM didukung hingga resolusi 4K",
      browseFiles: "Pilih File dari Komputer",
      urlPlaceholder: "Tempel URL YouTube publik atau klip webinar...",
      importUrl: "Muat Video",
      step2: "2",
      step2Title: "Deteksi Momen & Heuristik Klip",
      showAdvanced: "Tampilkan Kontrol Lanjutan",
      hideAdvanced: "Sembunyikan Kontrol Lanjutan",
      targetDuration: "Durasi Target Tiap Klip",
      durationSub: "Rentang batas durasi yang akan diekstrak AI",
      optimalShorts: "Sangat singkat & to the point",
      optimalReels: "Optimal untuk Shorts & Reels",
      extendedClip: "Pembahasan mendalam & lengkap",
      durationMax: "Maks",
      targetClips: "Jumlah Target Klip",
      targetClipsDesc: "Jumlah klip yang diekstrak AI dari sumber ini (1 — 30 klip)",
      decrease5: "Kurangi 5 klip",
      decrease1: "Kurangi 1 klip",
      increase1: "Tambah 1 klip",
      increase5: "Tambah 5 klip",
      aspectRatio: "Rasio Aspek Target",
      aspectDesc: "Pilih rasio framing video keluaran untuk channel tujuan",
      customCropOverride: "Kustomisasi Resolusi Crop (dalam Piksel)",
      widthPx: "Lebar Target (px)",
      heightPx: "Tinggi Target (px)",
      computedRatio: "Rasio terhitung",
      presetResolutions: "Pilihan Cepat",
      speakerTracking: "Mekanisme Auto-Reframe Pembicara",
      smartFaceTracking: "Smart AI Face Tracking & Pan Dinamis",
      smartFaceDesc: "Kamera bergerak halus memusatkan wajah pembicara secara otomatis",
      centerCrop: "Center Fixed Crop",
      centerCropDesc: "Memotong bagian tengah tanpa pergerakan kamera",
      bRoll: "Sisipkan B-Roll Kontekstual Otomatis",
      bRollDesc: "Menghasilkan overlay visual relevan berdasarkan kata kunci topik pembicaraan",
      audioPacing: "Optimasi Audio & Dialog",
      removeSilence: "Pemotongan Jeda Hening & Kata Pengisi",
      removeSilenceDesc: "Memotong jeda diam > 0.4 detik dan membersihkan keraguan vokal ('uh', 'um')",
      viralityThreshold: "Ambang Batas Keyakinan Viralitas AI",
      viralityDesc: "Hanya mengekstrak segmen dengan skor hook di persentil {pct}% teratas.",
      viralityLoose: "Longgar",
      viralityRecommended: "Disarankan",
      viralityStrict: "Ketat",
      targetPlatform: "Platform Target & Rasio Aspek",
      smartReframe: "Smart Reframe",
      step3: "3",
      step3Title: "Tujuan Klip & Instruksi Khusus",
      clipObjective: "Pacing & Gaya Konten",
      pacingHeuristic: "Heuristik Pacing",
      strategyTitle: "Strategi Prompt Klip",
      captionStyleTitle: "Gaya Teks Subtitle Dinamis",
      instructionsTitle: "Instruksi Tambahan untuk AI",
      instructionsLabel: "Instruksi Khusus untuk AI (Opsional)",
      instructionsPlaceholder:
        "Contoh: Cari bagian yang membahas AI agents, utamakan punchline di awal, abaikan perkenalan sponsor...",
      captionStyling: "Gaya Teks Subtitle",
      startProcessing: "Mulai Pemrosesan AI",
      viewQueue: "Antrean Klip",
    },
    clips: {
      title: "Hasil Klip & Pemantau AI",
      noJob: "Belum Ada Proyek yang Dipilih",
      noJobDesc:
        "Unggah video panjang Anda di Studio untuk membiarkan AI menganalisis dan memotong momen viral secara otomatis.",
      openStudio: "Buka Studio & Unggah Video",
      newProject: "Proyek Baru",
      publishSocials: "Publikasikan ke Medsos",
      viralityScore: "Skor Viralitas",
      timecodeAdjust: "Penyesuaian Timecode (In / Out)",
      inPoint: "Titik Mulai",
      outPoint: "Titik Akhir",
      rerender: "Render Ulang Klip",
      downloadClip: "Unduh Klip",
      downloadZip: "Unduh Semua (.ZIP)",
      captionsSync: "Subtitle & Transkrip Terpasang",
      all: "Semua",
      viral: "Viral (>80)",
      hook: "Hook Kuat",
      broll: "B-Roll",
      masterPlayer: "Master Player & Smart Reframe",
      clipTimeline: "Timeline Klip & Pemangkas",
      captionStyle: "Gaya Teks Subtitle",
      faceTracking: "Fokus Pembicara",
      exportZip: "Ekspor Semua (.ZIP)",
      generatedClips: "Klip Dihasilkan",
      ready: "Siap Dipakai",
      processing: "Memproses...",
      rerenderBtn: "Render Ulang Klip",
      resetBtn: "Atur Ulang",
    },
    settings: {
      badge: "Preferensi Sistem",
      version: "v3.4.2 Production",
      title: "Pengaturan Studio & Preferensi",
      subtitle:
        "Kelola profil pembuat konten, kunci API model AI, dan preferensi mesin rendering default.",
      discard: "Buang Perubahan",
      save: "Simpan Perubahan",
      saveSuccess:
        "Semua pengaturan berhasil diperbarui. Pipeline AI akan menggunakan kredensial yang dipilih pada tugas berikutnya.",
      profile: "Profil Pengguna",
      profileTitle: "Profil Pengguna & Identitas Kreator",
      profileSubtitle: "Atur identitas ekspor, detail akun, dan token kredensial.",
      changeAvatar: "Ganti Foto Profil",
      avatarHint: "JPG, PNG, atau WebP hingga 5MB.",
      displayName: "Nama Tampilan",
      email: "Alamat Email",
      accountSecurity: "Keamanan Akun",
      password: "Kata Sandi",
      changePassword: "Ubah Kata Sandi",
      credentialToken: "Token Kredensial (Akses CLI & API)",
      credentialTokenHint:
        "Token autentikasi lokal untuk integrasi baris perintah CLI dan bot worker.",
      regenerateToken: "Buat Ulang Token",
      copyToken: "Salin Token",
      copied: "Tersalin!",
      aiModels: "Kunci API Model AI",
      aiModelsTitle: "Model AI & Deteksi Hook",
      aiModelsSubtitle:
        "Pilih model visi/bahasa untuk ekstraksi klip viral dan heuristik reframing.",
      provider: "Penyedia Model",
      modelVersion: "Versi Model",
      refreshModels: "Perbarui Daftar Model",
      apiKey: "Kunci API",
      configureKey: "Atur Kunci API",
      testConnection: "Uji Koneksi",
      testing: "Menguji...",
      connected: "Terhubung ✓",
      pipeline: "Pengaturan Pipeline",
      pipelineTitle: "Aturan Pipeline & Default Render",
      pipelineSubtitle:
        "Konfigurasi resolusi default, transkripsi audio, dan subtitle otomatis.",
      defaultResolution: "Resolusi Default",
      audioEngine: "Mesin Audio & Transkripsi",
      audioEngineSub:
        "Model Whisper lokal untuk mendeteksi kata dan menghasilkan subtitle otomatis.",
      whisperModel: "Model Whisper",
      autoCaptions: "Subtitle Otomatis (Gaya Hormozi)",
      autoCaptionsSub:
        "Sematkan subtitle beranimasi dengan penyorotan kata aktif pada setiap klip.",
      cloudStorage: "Penyimpanan Media Cloud",
      cloudStorageSub:
        "Simpan file klip sementara untuk dibagikan atau dikirim ke media sosial.",
      storageProvider: "Penyedia Penyimpanan",
      localStorage: "Penyimpanan Lokal (Default)",
      retentionPeriod: "Masa Simpan File Klip",
      retentionSub:
        "Batas waktu penyimpanan sebelum berkas render klip otomatis dibersihkan.",
      socialBuffer: "Penerbitan Media Sosial (Buffer)",
      socialBufferSub:
        "Jadwalkan atau unggah klip langsung ke Instagram Reels, TikTok, YouTube Shorts.",
      bufferAccount: "Akun Buffer",
      connectBuffer: "Hubungkan Akun Buffer",
    },
    dialogs: {
      apiKey: {
        saveKey: "Simpan Kunci",
        saving: "Menyimpan...",
        removeKey: "Hapus Kunci",
        replaceKey: "Kunci baru akan menggantikan kunci tersimpan.",
        detectKey: "Digunakan untuk deteksi hook klip dengan AI.",
        storedEncrypted:
          "Disimpan terenkripsi. Hanya 4 karakter terakhir yang ditampilkan.",
        pastePrompt: "Tempel kunci API Anda.",
      },
      changePassword: {
        title: "Ubah Kata Sandi",
        desc: "Minimal 8 karakter dengan kombinasi angka & simbol.",
        oldPassword: "Kata Sandi Lama",
        newPassword: "Kata Sandi Baru",
        confirmPassword: "Konfirmasi Kata Sandi Baru",
        submit: "Simpan Kata Sandi",
        submitting: "Menyimpan...",
      },
    },
  },
  en: {
    common: {
      save: "Save",
      cancel: "Cancel",
      loading: "Loading...",
      error: "An error occurred",
      success: "Success",
      retry: "Retry",
      delete: "Delete",
      close: "Close",
      back: "Back",
      or: "or",
      active: "Active",
      guest: "Guest",
      processing: "Processing...",
    },
    header: {
      studio: "Studio",
      pipelineSubtitle: "Video Ingestion & Clipping Pipeline",
      exportPresets: "Export Presets",
      personalWorkspace: "Personal Workspace",
      notifications: "Notifications",
      appearance: "Appearance",
      switchLang: "Ubah ke Bahasa Indonesia (Switch to Indonesian)",
      currentLang: "EN",
    },
    sidebar: {
      studio: "Studio",
      clips: "Clips",
      recents: "Recents",
      noProjects: "No projects yet.",
      uploadToStart: "Upload a video to get started.",
      settings: "Settings",
      signOut: "Sign Out",
      signIn: "Sign In",
    },
    upload: {
      step1: "1",
      step1Title: "Raw Video Source",
      tabFile: "Upload Video File",
      tabUrl: "Video Link (YouTube)",
      dropPrompt: "Drag & drop long-form video here",
      dropSub: "MP4, MOV, MKV, or WebM supported up to 4K resolution",
      browseFiles: "Browse Files from Computer",
      urlPlaceholder: "Paste public YouTube URL or webinar clip...",
      importUrl: "Import Video",
      step2: "2",
      step2Title: "Detection Heuristics & Reframing",
      showAdvanced: "Show Advanced Controls",
      hideAdvanced: "Hide Advanced Controls",
      targetDuration: "Target Clip Duration",
      durationSub: "Range of clip lengths to be extracted by AI",
      optimalShorts: "Snappy & to the point",
      optimalReels: "Optimal for Shorts & Reels",
      extendedClip: "In-depth & comprehensive breakdown",
      durationMax: "Max",
      targetClips: "Target Clips Count",
      targetClipsDesc: "Number of clips AI will extract from this source (1 — 30 clips)",
      decrease5: "Decrease 5 clips",
      decrease1: "Decrease 1 clip",
      increase1: "Increase 1 clip",
      increase5: "Increase 5 clips",
      aspectRatio: "Target Aspect Ratio",
      aspectDesc: "Select output video framing ratio for your target channel",
      customCropOverride: "Custom Dimensional Crop Override (in Pixels)",
      widthPx: "Target Width (px)",
      heightPx: "Target Height (px)",
      computedRatio: "Computed ratio",
      presetResolutions: "Quick Presets",
      speakerTracking: "Speaker Auto-Reframe Mechanics",
      smartFaceTracking: "Smart AI Face Tracking & Dynamic Pan",
      smartFaceDesc: "Smooth camera drift centering speaker face automatically",
      centerCrop: "Center Fixed Crop",
      centerCropDesc: "Static center framing without camera movement",
      bRoll: "Auto-Insert Contextual B-Roll",
      bRollDesc: "Synthesizes relevant visual overlays based on speech noun keywords",
      audioPacing: "Audio & Speech Optimization",
      removeSilence: "Silence & Filler Word Elimination",
      removeSilenceDesc: "Cuts dead pauses > 0.4s and removes vocal hesitations ('uh', 'um')",
      viralityThreshold: "AI Virality Confidence Threshold",
      viralityDesc: "Extracts only segments scored in the top {pct}% percentile of hook strength.",
      viralityLoose: "Loose",
      viralityRecommended: "Recommended",
      viralityStrict: "Strict",
      targetPlatform: "Target Platform & Aspect Ratio",
      smartReframe: "Smart Reframe",
      step3: "3",
      step3Title: "Clip Objective & Custom Tone",
      clipObjective: "Pacing & Content Objective",
      pacingHeuristic: "Pacing Heuristic",
      strategyTitle: "Clipping Prompt Strategy",
      captionStyleTitle: "Kinetic Captioning Style",
      instructionsTitle: "Additional Instructions",
      instructionsLabel: "Custom AI Directives (Optional)",
      instructionsPlaceholder:
        "Example: Focus on AI agent debate, hook within first 3 seconds, omit sponsor shoutouts...",
      captionStyling: "Caption Style Preset",
      startProcessing: "Start AI Pipeline",
      viewQueue: "Clips Queue",
    },
    clips: {
      title: "Clip Results & AI Output Monitor",
      noJob: "No Project Selected",
      noJobDesc:
        "Upload your long-form footage in Studio to let AI detect viral hooks and render clips automatically.",
      openStudio: "Open Studio & Upload Video",
      newProject: "New Project",
      publishSocials: "Publish to Socials",
      viralityScore: "Virality Score",
      timecodeAdjust: "Timecode Fine-Tuning (In / Out)",
      inPoint: "In Point",
      outPoint: "Out Point",
      rerender: "Re-render Clip",
      downloadClip: "Download Clip",
      downloadZip: "Download All (.ZIP)",
      captionsSync: "Synced Subtitles & Transcript Included",
      all: "All",
      viral: "Viral (>80)",
      hook: "Strong Hook",
      broll: "B-Roll",
      masterPlayer: "Master Player & Smart Reframe",
      clipTimeline: "Clip Timeline & Trimmer",
      captionStyle: "Caption Style",
      faceTracking: "Speaker Focus",
      exportZip: "Bulk Export (ZIP)",
      generatedClips: "Generated Clips",
      ready: "Ready",
      processing: "Processing...",
      rerenderBtn: "Rerender Clip",
      resetBtn: "Reset",
    },
    settings: {
      badge: "System Preferences",
      version: "v3.4.2 Production",
      title: "Studio Settings & Preferences",
      subtitle:
        "Manage your creator profile, configure custom AI model API keys, and default rendering engine preferences.",
      discard: "Discard",
      save: "Save Changes",
      saveSuccess:
        "All settings updated successfully. AI pipeline will use selected credentials on next job.",
      profile: "User Profile",
      profileTitle: "User Profile & Creator Identity",
      profileSubtitle: "Configure export branding, account details, and credential token.",
      changeAvatar: "Change Avatar",
      avatarHint: "JPG, PNG or WebP up to 5MB.",
      displayName: "Display Name",
      email: "Email Address",
      accountSecurity: "Account Security",
      password: "Password",
      changePassword: "Change Password",
      credentialToken: "Credential Token (CLI & API Access)",
      credentialTokenHint:
        "Local authentication token for command-line CLI integrations and worker bots.",
      regenerateToken: "Regenerate Token",
      copyToken: "Copy Token",
      copied: "Copied!",
      aiModels: "AI Model Keys",
      aiModelsTitle: "AI Models & Hook Detection",
      aiModelsSubtitle:
        "Configure which vision/language model handles viral clip extraction and framing heuristics.",
      provider: "AI Provider",
      modelVersion: "Model Version",
      refreshModels: "Refresh Models",
      apiKey: "API Key",
      configureKey: "Configure Key",
      testConnection: "Test Connection",
      testing: "Testing...",
      connected: "Connected ✓",
      pipeline: "Pipeline Preferences",
      pipelineTitle: "Pipeline Rules & Rendering Defaults",
      pipelineSubtitle:
        "Configure default resolution, audio transcription, and auto-caption defaults.",
      defaultResolution: "Default Resolution",
      audioEngine: "Audio & Transcription Engine",
      audioEngineSub:
        "Local Whisper model to detect speech and generate timed subtitles.",
      whisperModel: "Whisper Model",
      autoCaptions: "Auto-Captions (Hormozi Style)",
      autoCaptionsSub:
        "Burn animated word-by-word highlighted captions onto each clip.",
      cloudStorage: "Cloud Media Storage",
      cloudStorageSub:
        "Store temporary clip assets for sharing or social publishing.",
      storageProvider: "Storage Provider",
      localStorage: "Local Storage (Default)",
      retentionPeriod: "Clip Retention Period",
      retentionSub:
        "How long generated clips remain before automatic cleanup.",
      socialBuffer: "Social Publishing (Buffer)",
      socialBufferSub:
        "Schedule or publish clips directly to Instagram Reels, TikTok, YouTube Shorts.",
      bufferAccount: "Buffer Account",
      connectBuffer: "Connect Buffer Account",
    },
    dialogs: {
      apiKey: {
        saveKey: "Save Key",
        saving: "Saving...",
        removeKey: "Remove key",
        replaceKey: "The new key replaces your saved key.",
        detectKey: "Used for hook detection with AI.",
        storedEncrypted:
          "Stored encrypted. Only the last 4 characters are shown after saving.",
        pastePrompt: "Paste your API key.",
      },
      changePassword: {
        title: "Change Password",
        desc: "At least 8 characters with numbers & symbols.",
        oldPassword: "Old Password",
        newPassword: "New Password",
        confirmPassword: "Confirm New Password",
        submit: "Update Password",
        submitting: "Updating...",
      },
    },
  },
};

const LOCALE_STORAGE_KEY = "clipping_studio_locale";

interface I18nContextType {
  locale: Locale;
  t: Translations;
  setLocale: (l: Locale) => void;
  toggleLocale: () => void;
}

const I18nContext = createContext<I18nContextType | undefined>(undefined);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("id");

  useEffect(() => {
    try {
      const saved = localStorage.getItem(LOCALE_STORAGE_KEY);
      if (saved === "id" || saved === "en") {
        setLocaleState(saved);
      }
    } catch {
      // ignore storage errors
    }
  }, []);

  const setLocale = useCallback((newLocale: Locale) => {
    setLocaleState(newLocale);
    try {
      localStorage.setItem(LOCALE_STORAGE_KEY, newLocale);
    } catch {
      // ignore storage errors
    }
  }, []);

  const toggleLocale = useCallback(() => {
    setLocaleState((prev) => {
      const next: Locale = prev === "id" ? "en" : "id";
      try {
        localStorage.setItem(LOCALE_STORAGE_KEY, next);
      } catch {
        // ignore
      }
      return next;
    });
  }, []);

  return (
    <I18nContext.Provider
      value={{
        locale,
        t: translations[locale],
        setLocale,
        toggleLocale,
      }}
    >
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n(): I18nContextType {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    throw new Error("useI18n must be used within an I18nProvider");
  }
  return ctx;
}
