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
    audioPacing: string;
    removeSilence: string;
    removeSilenceDesc: string;
    viralityThreshold: string;
    viralityDesc: string;
    step3: string;
    step3Title: string;
    clipObjective: string;
    pacingHeuristic: string;
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
  };
  settings: {
    title: string;
    subtitle: string;
    profile: string;
    aiModels: string;
    pipeline: string;
    displayName: string;
    changePassword: string;
    saveChanges: string;
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
      exportPresets: "Preset Ekspor",
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
      audioPacing: "Optimasi Audio & Dialog",
      removeSilence: "Potong Otomatis Hening & Jeda Kosong",
      removeSilenceDesc: "Mendeteksi momen tanpa suara > 0.4 detik agar ritme lebih dinamis",
      viralityThreshold: "Ambang Batas Keyakinan Viralitas AI",
      viralityDesc: "Hanya mengekstrak segmen dengan skor hook di persentil {pct}% teratas.",
      step3: "3",
      step3Title: "Tujuan Klip & Instruksi Khusus",
      clipObjective: "Pacing & Gaya Konten",
      pacingHeuristic: "Heuristik Pacing",
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
    },
    settings: {
      title: "Pengaturan Studio & Preferensi",
      subtitle: "Kelola profil pembuat konten, kunci API model AI, dan pipeline default.",
      profile: "Profil Pengguna",
      aiModels: "Kunci API Model AI",
      pipeline: "Pengaturan Pipeline",
      displayName: "Nama Tampilan",
      changePassword: "Ubah Kata Sandi",
      saveChanges: "Simpan Perubahan",
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
      audioPacing: "Audio & Speech Optimization",
      removeSilence: "Auto-Trim Silence & Dead Air",
      removeSilenceDesc: "Detects silence gaps > 0.4s to maintain high viewer retention",
      viralityThreshold: "AI Virality Confidence Threshold",
      viralityDesc: "Extracts only segments scored in the top {pct}% percentile of hook strength.",
      step3: "3",
      step3Title: "Clip Objective & Custom Tone",
      clipObjective: "Pacing & Content Objective",
      pacingHeuristic: "Pacing Heuristic",
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
    },
    settings: {
      title: "Studio Settings & Preferences",
      subtitle: "Manage your creator profile, AI model keys, and pipeline configurations.",
      profile: "User Profile",
      aiModels: "AI Model Keys",
      pipeline: "Pipeline Preferences",
      displayName: "Display Name",
      changePassword: "Change Password",
      saveChanges: "Save Changes",
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
