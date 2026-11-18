import { useNavigate } from "@tanstack/react-router";
import { useRef, useState, type DragEvent } from "react";
import { toast } from "sonner";

import { Dropdown } from "@/components/studio/Dropdown";
import { Toggle } from "@/components/studio/Toggle";
import { Slider } from "@/components/ui/slider";
import { useJobs } from "@/lib/jobs-context";
import { useI18n } from "@/lib/i18n";

const CAPTION_STYLES = [
  {
    value: "hormozi",
    label: "Alex Hormozi Impact (Neon Gold Highlight)",
    description: "Word-by-word dynamic scale, bottom-center anchored",
    summary: "Hormozi Kinetic Typography",
  },
  {
    value: "clean",
    label: "Clean Minimal (White Sans)",
    description: "Two-line subtitles in the lower third",
    summary: "Clean Minimal Captions",
  },
  {
    value: "cyber",
    label: "Cyber Glow (Electric Violet)",
    description: "Glowing outline with punch-in on keywords",
    summary: "Cyber Glow Captions",
  },
  {
    value: "karaoke",
    label: "Karaoke Bounce (Pastel Pop)",
    description: "Bouncing active word, center anchored",
    summary: "Karaoke Bounce Captions",
  },
] as const;
type CaptionStyleId = (typeof CAPTION_STYLES)[number]["value"];

const RATIOS = [
  {
    id: "9:16",
    title: "TikTok / Shorts / Reels",
    size: "Vertical 1080x1920",
    note: "Auto Face Lock",
    box: "w-6 h-9",
    label: "9:16 Vertical TikTok",
  },
  {
    id: "16:9",
    title: "YouTube Standard",
    size: "Landscape 1920x1080",
    note: "Direct Chapter Clips",
    box: "w-9 h-6",
    label: "16:9 YouTube Landscape",
  },
  {
    id: "1:1",
    title: "Instagram & LinkedIn",
    size: "Square 1080x1080",
    note: "Headlines Banner",
    box: "w-7 h-7",
    label: "1:1 Square",
  },
  {
    id: "4:5",
    title: "Instagram Portrait",
    size: "Feed 1080x1350",
    note: "Maximum Mobile Real Estate",
    box: "w-6 h-8",
    label: "4:5 Instagram Portrait",
  },
] as const;

const STRATEGIES = [
  {
    id: "viral",
    icon: "bolt",
    title: "Viral Highlights",
    desc: "High punchline density, strong emotional hook in first 3s",
  },
  {
    id: "tutorial",
    icon: "school",
    title: "Tutorial & Insight",
    desc: "Complete thoughts, setup, contextual payoff",
  },
  {
    id: "story",
    icon: "forum",
    title: "Story & Debate",
    desc: "Multi-speaker exchange, back-and-forth tension",
  },
  {
    id: "humor",
    icon: "sentiment_very_satisfied",
    title: "Humor & Reaction",
    desc: "Punchlines, unexpected outbursts, sudden laugh peaks",
  },
] as const;

const TAB_ON =
  "px-4 py-1.5 rounded-full bg-surface text-primary font-label-md text-label-md font-medium shadow-xs transition-all flex items-center gap-1.5 cursor-pointer";
const TAB_OFF =
  "px-4 py-1.5 rounded-full text-on-surface-variant hover:text-on-surface font-label-md text-label-md font-medium transition-all flex items-center gap-1.5 cursor-pointer";

type ProcessState = "idle" | "running" | "done";

const MIN_CLIPS = 1;
const MAX_CLIPS = 30;
const MAX_INSTRUCTIONS = 500;

const DURATION_STEPS = [10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 70, 80, 90, 100, 110, 120];
const VIRALITY_STEPS = [50, 60, 70, 80, 85, 90, 95];

function getDurationIndex(sec: number) {
  const idx = DURATION_STEPS.indexOf(sec);
  if (idx !== -1) return idx;
  return DURATION_STEPS.reduce(
    (prev, curr, i) =>
      Math.abs(curr - sec) < Math.abs(DURATION_STEPS[prev] - sec) ? i : prev,
    0,
  );
}

function getViralityIndex(pct: number) {
  const idx = VIRALITY_STEPS.indexOf(pct);
  if (idx !== -1) return idx;
  return VIRALITY_STEPS.reduce(
    (prev, curr, i) =>
      Math.abs(curr - pct) < Math.abs(VIRALITY_STEPS[prev] - pct) ? i : prev,
    0,
  );
}

function clampClips(n: number) {
  if (!Number.isFinite(n)) return MIN_CLIPS;
  return Math.min(MAX_CLIPS, Math.max(MIN_CLIPS, Math.round(n)));
}

function formatSize(bytes: number) {
  if (bytes > 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

function getAspectRatioLabel(width: number, height: number): string {
  if (!width || !height) return "";
  const gcd = (a: number, b: number): number => (b === 0 ? a : gcd(b, a % b));
  const d = gcd(width, height);
  const rw = width / d;
  const rh = height / d;
  if (rw <= 20 && rh <= 20) {
    return `${rw}:${rh}`;
  }
  return `${(width / height).toFixed(2)}:1`;
}

function getClosestAspect(width: number, height: number): string {
  if (width <= 0 || height <= 0) return "9:16";
  const r = width / height;
  const targets = [
    { id: "9:16", ratio: 9 / 16 },
    { id: "1:1", ratio: 1 / 1 },
    { id: "4:5", ratio: 4 / 5 },
    { id: "16:9", ratio: 16 / 9 },
  ];
  let closest = "9:16";
  let minDiff = Infinity;
  for (const t of targets) {
    const diff = Math.abs(r - t.ratio);
    if (diff < minDiff) {
      minDiff = diff;
      closest = t.id;
    }
  }
  return closest;
}

export function UploadPage() {
  const navigate = useNavigate();
  const { createJob, setActiveJobId } = useJobs();
  const { t } = useI18n();
  const fileInput = useRef<HTMLInputElement>(null);
  const [source, setSource] = useState<"file" | "url">("file");
  const [file, setFile] = useState<File | null>(null);
  const [urlInput, setUrlInput] = useState("");
  const [dragging, setDragging] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [viralityThreshold, setViralityThreshold] = useState(80);
  const [showCustomAr, setShowCustomAr] = useState(false);
  const [bRoll, setBRoll] = useState(true);
  const [silenceTrim, setSilenceTrim] = useState(true);
  const [ratio, setRatio] = useState<(typeof RATIOS)[number]["id"]>("9:16");
  const [customWidthPx, setCustomWidthPx] = useState(1080);
  const [customHeightPx, setCustomHeightPx] = useState(1920);
  const [durationRange, setDurationRange] = useState<[number, number]>([20, 60]);
  const durationIndices: [number, number] = [
    getDurationIndex(durationRange[0]),
    getDurationIndex(durationRange[1]),
  ];
  const viralityIndex = getViralityIndex(viralityThreshold);
  const [layoutMode, setLayoutMode] = useState<"face" | "crop">("face");
  const [strategy, setStrategy] = useState<(typeof STRATEGIES)[number]["id"]>("viral");
  const [processState, setProcessState] = useState<ProcessState>("idle");
  const [targetClips, setTargetClips] = useState(5);
  const [instructions, setInstructions] = useState("");
  const [captionStyle, setCaptionStyle] = useState<CaptionStyleId>("hormozi");
  const captionSummary =
    CAPTION_STYLES.find((c) => c.value === captionStyle)?.summary ?? CAPTION_STYLES[0].summary;
  const ratioLabel = RATIOS.find((r) => r.id === ratio)?.label ?? ratio;

  const startProcessing = async () => {
    if (processState !== "idle") return;

    if (source === "file") {
      if (!file) {
        toast.error("Pilih berkas video terlebih dahulu.");
        fileInput.current?.click();
        return;
      }
      const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
      if (![".mp4", ".mov", ".mkv", ".webm"].includes(ext)) {
        toast.error(`Format berkas ${ext} tidak didukung. Gunakan MP4, MOV, MKV, atau WebM.`);
        return;
      }
    } else {
      if (!urlInput.trim()) {
        toast.error("Masukkan link video yang valid.");
        return;
      }
    }

    setProcessState("running");
    try {
      const formData = new FormData();
      if (source === "file" && file) {
        formData.append("file", file);
      } else {
        formData.append("url", urlInput.trim());
      }

      const finalAspect = showCustomAr ? getClosestAspect(customWidthPx, customHeightPx) : ratio;

      const options = {
        num_clips: targetClips,
        min_len: durationRange[0],
        max_len: durationRange[1],
        aspect: finalAspect,
        layout: layoutMode,
        subtitles: true,
        remove_silence: silenceTrim,
        show_title: true,
        instructions: instructions.trim(),
        virality_threshold: viralityThreshold,
        custom_dimensions: showCustomAr
          ? { width: customWidthPx, height: customHeightPx }
          : undefined,
      };
      formData.append("options", JSON.stringify(options));

      const job = await createJob(formData);
      setActiveJobId(job.id);
      setProcessState("done");
      toast.success("Video berhasil diunggah!", {
        description: `Proyek #${job.id.slice(-6)} sedang dianalisis oleh AI.`,
      });
      setTimeout(() => {
        navigate({ to: "/app/clips" });
      }, 700);
    } catch (err: unknown) {
      setProcessState("idle");
      const msg = err instanceof Error ? err.message : "Gagal memulai pemrosesan video.";
      toast.error(msg);
    }
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) setFile(dropped);
  };

  const processLabel =
    processState === "running"
      ? "Mengunggah & Memproses..."
      : processState === "done"
        ? "Berhasil Dimulai"
        : null;
  const processIcon = processState === "running" ? "progress_activity" : "check_circle";

  return (
    <>
      <div className="flex flex-col w-full">
        <div className="relative w-full px-space-lg py-space-md max-w-[1720px] mx-auto">
          <div className="absolute top-12 left-1/4 w-96 h-96 bg-primary-fixed/30 rounded-full blur-3xl pointer-events-none -z-10"></div>{" "}
          <div className="absolute top-48 right-10 w-80 h-80 bg-secondary-fixed/40 rounded-full blur-3xl pointer-events-none -z-10"></div>{" "}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-md pb-space-lg">
            <div className="flex flex-col">
              <div className="flex items-center gap-space-xs mb-1">
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-secondary-container text-on-secondary-container font-label-sm text-label-sm font-semibold tracking-wide uppercase">
                  <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse"></span>{" "}
                  Pipeline Config{" "}
                </span>
                <span className="text-outline-variant font-label-sm text-label-sm">•</span>
                <span className="text-on-surface-variant font-label-sm text-label-sm">
                  {file ? file.name : "New Project"}
                </span>
              </div>
              <h1 className="font-headline-lg text-headline-lg font-normal text-on-surface tracking-tight">
                {"Upload & Source Video Setup"}
              </h1>
              <p className="font-body-md text-body-md text-on-surface-variant max-w-2xl mt-0.5">
                {" "}
                Select long-form source footage, tune algorithmic reframing profiles, select kinetic
                caption presets, and set intelligent clip boundary heuristics.{" "}
              </p>
            </div>
          </div>{" "}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg items-start">
            <div className="lg:col-span-7 flex flex-col gap-space-lg">
              <div className="bg-surface-container-low rounded-xl p-space-md shadow-xs">
                <div className="flex items-center justify-between pb-space-sm mb-space-sm border-b-0">
                  <div className="flex items-center gap-space-xs bg-surface-container-high p-1 rounded-full">
                    <button
                      className={source === "file" ? TAB_ON : TAB_OFF}
                      onClick={() => setSource("file")}
                      id="tab-btn-file"
                      type="button"
                    >
                      <span className="material-symbols-outlined text-[16px]">upload_file</span>
                      <span>{t.upload.tabFile}</span>
                    </button>
                    <button
                      className={source === "url" ? TAB_ON : TAB_OFF}
                      onClick={() => setSource("url")}
                      id="tab-btn-url"
                      type="button"
                    >
                      <span className="material-symbols-outlined text-[16px]">link</span>
                      <span>{t.upload.tabUrl}</span>
                    </button>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-label-sm text-label-sm text-outline">
                      Supported: MP4, MOV, MKV, WebM
                    </span>
                    <span
                      className="material-symbols-outlined text-outline text-[16px]"
                      title="Hardware-accelerated cloud rendering available"
                    >
                      info
                    </span>
                  </div>
                </div>{" "}
                {source === "file" && (
                  <div
                    className={`relative group cursor-pointer rounded-xl p-space-xl flex flex-col items-center justify-center text-center transition-all hover:bg-surface-container-high/60 ${dragging ? "bg-primary-fixed/40" : "bg-surface-container-lowest"}`}
                    id="dropzone-area"
                    role="button"
                    tabIndex={0}
                    onClick={() => fileInput.current?.click()}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") fileInput.current?.click();
                    }}
                    onDragOver={(e) => {
                      e.preventDefault();
                      setDragging(true);
                    }}
                    onDragLeave={() => setDragging(false)}
                    onDrop={onDrop}
                    style={{
                      backgroundImage:
                        "radial-gradient(circle at center, rgba(103, 80, 164, 0.04) 0%, transparent 70%)",
                    }}
                  >
                    <svg
                      className="absolute inset-0 w-full h-full pointer-events-none rounded-xl"
                      xmlns="http://www.w3.org/2000/svg"
                    >
                      <rect
                        className="transition-colors group-hover:stroke-primary"
                        fill="none"
                        height="calc(100% - 4px)"
                        rx="12"
                        stroke="#cbc4d2"
                        strokeDasharray="8 8"
                        strokeWidth="2"
                        width="calc(100% - 4px)"
                        x="2"
                        y="2"
                      ></rect>
                    </svg>
                    <input
                      ref={fileInput}
                      type="file"
                      accept="video/mp4,video/quicktime,video/x-matroska,video/webm,.mov,.mkv,.mp4,.webm"
                      className="sr-only"
                      onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                    />
                    <div className="relative z-10 flex flex-col items-center">
                      <div className="w-16 h-16 rounded-full bg-primary-fixed flex items-center justify-center text-on-primary-fixed mb-space-sm group-hover:scale-110 transition-transform shadow-xs">
                        <span className="material-symbols-outlined text-[32px]">
                          {file ? "movie" : "cloud_upload"}
                        </span>
                      </div>
                      <h3 className="font-title-md text-title-md font-medium text-on-surface">
                        {file ? file.name : "Drag & drop master video here"}
                      </h3>
                      {file && (
                        <p className="font-label-md text-label-md text-primary mt-1">
                          {formatSize(file.size)} • Ready for ingestion • Click to replace
                        </p>
                      )}
                      <p className="font-body-md text-body-md text-on-surface-variant mt-1 max-w-sm">
                        {" "}
                        or{" "}
                        <span className="text-primary font-medium underline underline-offset-4 decoration-primary/40 group-hover:decoration-primary">
                          browse files
                        </span>{" "}
                        from your local workstation or NAS{" "}
                      </p>
                      <div className="flex flex-wrap items-center justify-center gap-2 mt-space-md">
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-surface-container font-label-sm text-label-sm text-on-surface-variant">
                          <span className="material-symbols-outlined text-[14px] text-primary">
                            speed
                          </span>{" "}
                          Up to 4K @ 60fps{" "}
                        </span>
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-surface-container font-label-sm text-label-sm text-on-surface-variant">
                          <span className="material-symbols-outlined text-[14px] text-primary">
                            data_object
                          </span>{" "}
                          Max 500 MB{" "}
                        </span>
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-surface-container font-label-sm text-label-sm text-on-surface-variant">
                          <span className="material-symbols-outlined text-[14px] text-primary">
                            subtitles
                          </span>{" "}
                          Multi-channel Audio{" "}
                        </span>
                      </div>
                    </div>
                  </div>
                )}
                {source === "url" && (
                  <div
                    className="mt-space-xs p-space-md rounded-xl bg-surface-container-lowest"
                    id="url-input-area"
                  >
                    <label className="font-label-md text-label-md font-medium text-on-surface mb-2 block">
                      Direct Video Source Link
                    </label>{" "}
                    <div className="flex items-center gap-space-xs">
                      <div className="relative flex-1 flex items-center bg-surface-container rounded-lg px-3 py-2">
                        <span className="material-symbols-outlined text-outline mr-2 text-[20px]">
                          link
                        </span>
                        <input
                          className="w-full bg-transparent text-on-surface font-body-md text-body-md focus:outline-hidden placeholder:text-outline"
                          placeholder="Paste YouTube, TikTok, Instagram, or direct video URL..."
                          type="url"
                          value={urlInput}
                          onChange={(e) => setUrlInput(e.target.value)}
                        />
                      </div>
                      <button
                        className="px-5 h-11 rounded-lg bg-secondary text-on-secondary font-label-md text-label-md hover:bg-secondary/90 transition-colors flex items-center gap-1 cursor-pointer"
                        type="button"
                        onClick={startProcessing}
                      >
                        <span className="material-symbols-outlined text-[18px]">download</span>
                        <span>Fetch &amp; Process</span>
                      </button>
                    </div>{" "}
                    <div className="flex items-center gap-4 mt-2 text-on-surface-variant font-label-sm text-label-sm">
                      <span className="flex items-center gap-1">
                        <span className="w-2 h-2 rounded-full bg-primary"></span> YouTube VOD
                      </span>
                      <span className="flex items-center gap-1">
                        <span className="w-2 h-2 rounded-full bg-primary"></span> TikTok &amp; Reels
                      </span>
                      <span className="flex items-center gap-1">
                        <span className="w-2 h-2 rounded-full bg-primary"></span> Google Drive
                        Public Share
                      </span>
                    </div>
                  </div>
                )}
              </div>
              <div className="bg-surface-container-low rounded-xl p-space-md shadow-xs flex flex-col gap-space-md">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2">
                    <span className="w-7 h-7 rounded-full bg-primary-fixed text-on-primary-fixed flex items-center justify-center font-label-sm text-label-sm font-bold">
                      2
                    </span>
                    <h3 className="font-title-md text-title-md font-medium text-on-surface">
                      {"Detection & Reframing Heuristics"}
                    </h3>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-surface-container-high hover:bg-surface-variant text-on-surface font-label-sm text-label-sm transition-colors cursor-pointer"
                      type="button"
                      aria-expanded={showAdvanced}
                      onClick={() => setShowAdvanced((v) => !v)}
                    >
                      <span
                        className="material-symbols-outlined text-[16px] text-primary"
                        id="toggle-adv-icon"
                      >
                        {showAdvanced ? "expand_less" : "tune"}
                      </span>
                      <span className="font-medium" id="toggle-adv-text">
                        {showAdvanced ? t.upload.hideAdvanced : t.upload.showAdvanced}
                      </span>
                    </button>
                    <span className="material-symbols-outlined text-outline text-[20px]">
                      settings_suggest
                    </span>
                  </div>
                </div>
                <div className="flex flex-col gap-2 bg-surface-container rounded-xl p-3">
                  <div className="flex items-center justify-between font-label-md text-label-md">
                    <span className="text-on-surface font-medium">{t.upload.targetDuration}</span>
                    <span className="text-primary font-bold">
                      {durationRange[0]}s — {durationRange[1]}s{" "}
                      <span className="text-on-surface-variant font-normal text-xs">
                        (
                        {durationRange[1] <= 30
                          ? t.upload.optimalShorts
                          : durationRange[1] <= 60
                            ? t.upload.optimalReels
                            : t.upload.extendedClip}
                        )
                      </span>
                    </span>
                  </div>
                  <div className="py-2 px-1">
                    <Slider
                      value={durationIndices}
                      onValueChange={(val) => {
                        if (Array.isArray(val) && val.length === 2) {
                          const minSec = DURATION_STEPS[val[0]] ?? 10;
                          const maxSec = DURATION_STEPS[val[1]] ?? 60;
                          setDurationRange([minSec, maxSec]);
                        }
                      }}
                      min={0}
                      max={DURATION_STEPS.length - 1}
                      step={1}
                      minStepsBetweenThumbs={1}
                      aria-label={t.upload.targetDuration}
                      className="w-full cursor-pointer"
                    />
                  </div>
                  <div className="relative w-full h-5 font-label-sm text-[11px] text-outline px-1">
                    <span className="absolute left-1">10s (Min)</span>
                    <span
                      className="absolute -translate-x-1/2 text-center whitespace-nowrap"
                      style={{ left: "25%" }}
                    >
                      30s (Shorts)
                    </span>
                    <span
                      className="absolute -translate-x-1/2 text-center whitespace-nowrap"
                      style={{ left: "62.5%" }}
                    >
                      60s (Reels)
                    </span>
                    <span className="absolute right-1">
                      120s ({t.upload.durationMax})
                    </span>
                  </div>
                </div>

                <div className="flex items-center justify-between gap-space-sm bg-surface-container rounded-xl px-3 py-2.5">
                  <div className="flex flex-col min-w-0">
                    <span className="font-label-md text-label-md text-on-surface font-medium">
                      {t.upload.targetClips}
                    </span>
                    <span className="font-body-sm text-xs text-on-surface-variant truncate">
                      {t.upload.targetClipsDesc}
                    </span>
                  </div>
                  <div className="flex items-center gap-1 bg-surface-container-lowest rounded-full p-1 shadow-xs shrink-0">
                    <button
                      type="button"
                      aria-label={t.upload.decrease5}
                      title={t.upload.decrease5}
                      disabled={targetClips <= MIN_CLIPS}
                      onClick={() => setTargetClips((n) => clampClips(n - 5))}
                      className="h-7 px-2 rounded-full flex items-center justify-center text-xs font-semibold text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface disabled:opacity-30 transition-colors cursor-pointer"
                    >
                      -5
                    </button>
                    <button
                      type="button"
                      aria-label={t.upload.decrease1}
                      title={t.upload.decrease1}
                      disabled={targetClips <= MIN_CLIPS}
                      onClick={() => setTargetClips((n) => clampClips(n - 1))}
                      className="w-7 h-7 rounded-full flex items-center justify-center text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface disabled:opacity-30 transition-colors cursor-pointer"
                    >
                      <span className="material-symbols-outlined text-[16px]">remove</span>
                    </button>
                    <input
                      aria-label="Target clips"
                      type="number"
                      min={MIN_CLIPS}
                      max={MAX_CLIPS}
                      value={targetClips}
                      onChange={(e) => setTargetClips(clampClips(Number(e.target.value)))}
                      className="w-9 bg-transparent text-center text-primary font-label-md text-sm font-bold focus:outline-hidden [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                    />
                    <button
                      type="button"
                      aria-label={t.upload.increase1}
                      title={t.upload.increase1}
                      disabled={targetClips >= MAX_CLIPS}
                      onClick={() => setTargetClips((n) => clampClips(n + 1))}
                      className="w-7 h-7 rounded-full flex items-center justify-center text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface disabled:opacity-30 transition-colors cursor-pointer"
                    >
                      <span className="material-symbols-outlined text-[16px]">add</span>
                    </button>
                    <button
                      type="button"
                      aria-label={t.upload.increase5}
                      title={t.upload.increase5}
                      disabled={targetClips >= MAX_CLIPS}
                      onClick={() => setTargetClips((n) => clampClips(n + 5))}
                      className="h-7 px-2 rounded-full flex items-center justify-center text-xs font-semibold text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface disabled:opacity-30 transition-colors cursor-pointer"
                    >
                      +5
                    </button>
                  </div>
                </div>
                {showAdvanced && (
                  <div
                    className="flex flex-col gap-space-md transition-all duration-300"
                    id="heuristics-advanced-panel"
                  >
                    <div className="flex flex-col gap-2">
                      <label className="font-label-sm text-label-sm font-medium text-on-surface-variant">
                        {t.upload.speakerTracking}
                      </label>
                      <div className="grid grid-cols-1 gap-2">
                        <label
                          className={`flex items-center justify-between p-3 rounded-lg cursor-pointer transition-colors ${layoutMode === "face" ? "bg-surface-container-high ring-1 ring-primary" : "bg-surface-container hover:bg-surface-container-high"}`}
                          onClick={() => setLayoutMode("face")}
                        >
                          <div className="flex items-center gap-3">
                            <input
                              checked={layoutMode === "face"}
                              onChange={() => setLayoutMode("face")}
                              className="accent-primary w-4 h-4 cursor-pointer"
                              name="speaker-tracking"
                              type="radio"
                            />
                            <div className="flex flex-col">
                              <span className="font-label-md text-label-md font-semibold text-on-surface">
                                {t.upload.smartFaceTracking}
                              </span>
                              <span className="font-body-sm text-body-sm text-on-surface-variant">
                                {t.upload.smartFaceDesc}
                              </span>
                            </div>
                          </div>
                          <span className="material-symbols-outlined text-primary text-[20px]">
                            person_pin_circle
                          </span>
                        </label>
                        <label
                          className={`flex items-center justify-between p-3 rounded-lg cursor-pointer transition-colors ${layoutMode === "crop" ? "bg-surface-container-high ring-1 ring-primary" : "bg-surface-container hover:bg-surface-container-high"}`}
                          onClick={() => setLayoutMode("crop")}
                        >
                          <div className="flex items-center gap-3">
                            <input
                              checked={layoutMode === "crop"}
                              onChange={() => setLayoutMode("crop")}
                              className="accent-primary w-4 h-4 cursor-pointer"
                              name="speaker-tracking"
                              type="radio"
                            />
                            <div className="flex flex-col">
                              <span className="font-label-md text-label-md font-medium text-on-surface">
                                {t.upload.centerCrop}
                              </span>
                              <span className="font-body-sm text-body-sm text-on-surface-variant">
                                {t.upload.centerCropDesc}
                              </span>
                            </div>
                          </div>
                          <span className="material-symbols-outlined text-outline text-[20px]">
                            crop_free
                          </span>
                        </label>
                      </div>
                    </div>
                    <div className="flex flex-col gap-3 pt-2">
                      <div className="flex items-center justify-between">
                        <div className="flex flex-col max-w-[80%]">
                          <span className="font-label-md text-label-md font-semibold text-on-surface">
                            {t.upload.bRoll}
                          </span>
                          <span className="font-body-sm text-body-sm text-on-surface-variant">
                            {t.upload.bRollDesc}
                          </span>
                        </div>
                        <Toggle
                          checked={bRoll}
                          onChange={setBRoll}
                          label={t.upload.bRoll}
                        />
                      </div>
                      <div className="flex items-center justify-between">
                        <div className="flex flex-col max-w-[80%]">
                          <span className="font-label-md text-label-md font-semibold text-on-surface">
                            {t.upload.removeSilence}
                          </span>
                          <span className="font-body-sm text-body-sm text-on-surface-variant">
                            {t.upload.removeSilenceDesc}
                          </span>
                        </div>
                        <Toggle
                          checked={silenceTrim}
                          onChange={setSilenceTrim}
                          label={t.upload.removeSilence}
                        />
                      </div>
                      <div className="flex flex-col gap-2 pt-2">
                        <div className="flex items-center justify-between font-label-md text-label-md">
                          <span className="text-on-surface font-semibold">
                            {t.upload.viralityThreshold}
                          </span>
                          <span className="text-primary font-bold">
                            {viralityThreshold}% Minimum
                          </span>
                        </div>
                        <Slider
                          min={0}
                          max={VIRALITY_STEPS.length - 1}
                          step={1}
                          value={[viralityIndex]}
                          onValueChange={([idx]) => {
                            const val = VIRALITY_STEPS[idx] ?? 80;
                            setViralityThreshold(val);
                          }}
                          aria-label={t.upload.viralityThreshold}
                          className="w-full cursor-pointer py-1"
                        />
                        <div className="relative w-full h-5 text-xs text-on-surface-variant font-medium px-1">
                          <span className="absolute left-1">
                            50% ({t.upload.viralityLoose})
                          </span>
                          <span className="absolute left-1/2 -translate-x-1/2 text-center whitespace-nowrap">
                            80% ({t.upload.viralityRecommended})
                          </span>
                          <span className="absolute right-1">
                            95% ({t.upload.viralityStrict})
                          </span>
                        </div>
                        <p className="font-body-sm text-body-sm text-on-surface-variant">
                          {t.upload.viralityDesc.replace("{pct}", String(100 - viralityThreshold))}
                        </p>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
            <div className="lg:col-span-5 flex flex-col gap-space-lg">
              <div className="bg-surface-container-low rounded-xl p-space-md shadow-xs flex flex-col gap-space-md">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="w-7 h-7 rounded-full bg-primary-fixed text-on-primary-fixed flex items-center justify-center font-label-sm text-label-sm font-bold">
                      1
                    </span>
                    <h3 className="font-title-md text-title-md font-medium text-on-surface">
                      {t.upload.targetPlatform}
                    </h3>
                  </div>
                  <span className="text-primary font-label-sm text-label-sm font-semibold uppercase">
                    {t.upload.smartReframe}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-space-xs" role="radiogroup">
                  {RATIOS.map((r) => {
                    const active = ratio === r.id;
                    return (
                      <label
                        key={r.id}
                        className={
                          active
                            ? "relative flex flex-col p-3 rounded-xl bg-secondary-container text-on-secondary-container cursor-pointer shadow-xs transition-all"
                            : "relative flex flex-col p-3 rounded-xl bg-surface-container hover:bg-surface-container-high text-on-surface cursor-pointer transition-all"
                        }
                      >
                        <input
                          checked={active}
                          onChange={() => setRatio(r.id)}
                          className="sr-only"
                          name="aspect-ratio"
                          type="radio"
                        />
                        <div className="flex items-center justify-between mb-2">
                          <div
                            className={`${r.box} rounded-sm flex items-center justify-center ${active ? "bg-primary text-on-primary" : "bg-surface-container-highest text-on-surface-variant"}`}
                          >
                            <span className={`text-[10px] ${active ? "font-bold" : "font-medium"}`}>
                              {r.id}
                            </span>
                          </div>
                          {active ? (
                            <span
                              className="material-symbols-outlined text-[20px] text-primary"
                              style={{ fontVariationSettings: "'FILL' 1" }}
                            >
                              check_circle
                            </span>
                          ) : (
                            <span className="w-4 h-4 rounded-full bg-surface-container-highest"></span>
                          )}
                        </div>
                        <span
                          className={`font-title-sm text-title-sm ${active ? "font-bold" : "font-medium"}`}
                        >
                          {r.title}
                        </span>
                        <span
                          className={`font-body-sm text-body-sm mt-0.5 ${active ? "text-on-secondary-container" : "text-on-surface-variant"}`}
                        >
                          {r.size}
                        </span>
                        {active ? (
                          <span className="mt-2 inline-flex items-center gap-1 font-label-sm text-[10px] uppercase tracking-wider text-primary font-bold">
                            <span className="w-1.5 h-1.5 rounded-full bg-primary"></span> Auto Face
                            Lock
                          </span>
                        ) : (
                          <span className="mt-2 text-on-surface-variant font-label-sm text-[10px]">
                            {r.note}
                          </span>
                        )}
                      </label>
                    );
                  })}
                </div>
                <div className="pt-2">
                  <button
                    className="flex items-center justify-between w-full text-on-surface-variant hover:text-on-surface font-label-md text-label-md py-1 cursor-pointer"
                    id="toggle-custom-ar"
                    type="button"
                    aria-expanded={showCustomAr}
                    onClick={() => setShowCustomAr((v) => !v)}
                  >
                    <span className="flex items-center gap-1.5 font-medium">
                      <span className="material-symbols-outlined text-[16px]">tune</span>
                      {t.upload.customCropOverride}
                    </span>
                    <span
                      className={`material-symbols-outlined text-[18px] transition-transform ${showCustomAr ? "rotate-180" : ""}`}
                    >
                      keyboard_arrow_down
                    </span>
                  </button>{" "}
                  <div
                    className={`${showCustomAr ? "flex flex-col gap-3" : "hidden"} mt-2 p-3 bg-surface-container rounded-lg`}
                    id="custom-ar-panel"
                  >
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="font-label-sm text-label-sm text-on-surface-variant block mb-1">
                          {t.upload.widthPx}
                        </label>
                        <div className="relative flex items-center">
                          <input
                            className="w-full bg-surface-container-lowest text-on-surface font-label-md text-label-md px-3 py-1.5 pr-8 rounded-lg focus:outline-hidden focus:ring-1 focus:ring-primary"
                            type="number"
                            min={240}
                            max={3840}
                            step={10}
                            value={customWidthPx}
                            onChange={(e) => setCustomWidthPx(Math.max(1, Number(e.target.value)))}
                          />
                          <span className="absolute right-2.5 font-label-sm text-[11px] text-outline pointer-events-none font-medium">
                            px
                          </span>
                        </div>
                      </div>
                      <div>
                        <label className="font-label-sm text-label-sm text-on-surface-variant block mb-1">
                          {t.upload.heightPx}
                        </label>
                        <div className="relative flex items-center">
                          <input
                            className="w-full bg-surface-container-lowest text-on-surface font-label-md text-label-md px-3 py-1.5 pr-8 rounded-lg focus:outline-hidden focus:ring-1 focus:ring-primary"
                            type="number"
                            min={240}
                            max={3840}
                            step={10}
                            value={customHeightPx}
                            onChange={(e) => setCustomHeightPx(Math.max(1, Number(e.target.value)))}
                          />
                          <span className="absolute right-2.5 font-label-sm text-[11px] text-outline pointer-events-none font-medium">
                            px
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-outline-variant/30 text-xs">
                      <div className="flex items-center gap-1.5 text-on-surface-variant">
                        <span className="material-symbols-outlined text-[15px] text-primary">
                          aspect_ratio
                        </span>
                        <span>
                          {t.upload.computedRatio}:{" "}
                          <strong className="text-on-surface font-semibold">
                            {getAspectRatioLabel(customWidthPx, customHeightPx)}
                          </strong>{" "}
                          ({customWidthPx} × {customHeightPx} px)
                        </span>
                      </div>
                      <div className="flex items-center gap-1 flex-wrap">
                        {[
                          { label: "1080×1920 (9:16)", w: 1080, h: 1920, r: "9:16" },
                          { label: "1080×1080 (1:1)", w: 1080, h: 1080, r: "1:1" },
                          { label: "1080×1350 (4:5)", w: 1080, h: 1350, r: "4:5" },
                          { label: "1920×1080 (16:9)", w: 1920, h: 1080, r: "16:9" },
                        ].map((p) => (
                          <button
                            key={p.label}
                            type="button"
                            onClick={() => {
                              setCustomWidthPx(p.w);
                              setCustomHeightPx(p.h);
                              setRatio(p.r as (typeof RATIOS)[number]["id"]);
                            }}
                            className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors cursor-pointer ${
                              customWidthPx === p.w && customHeightPx === p.h
                                ? "bg-primary text-on-primary"
                                : "bg-surface-container-lowest text-on-surface-variant hover:bg-surface-container-high"
                            }`}
                          >
                            {p.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              <div className="bg-surface-container-low rounded-xl p-space-md shadow-xs flex flex-col gap-space-md">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="w-7 h-7 rounded-full bg-primary-fixed text-on-primary-fixed flex items-center justify-center font-label-sm text-label-sm font-bold">
                      3
                    </span>
                    <h3 className="font-title-md text-title-md font-medium text-on-surface">
                      {t.upload.clipObjectiveTitle}
                    </h3>
                  </div>
                  <span className="font-label-sm text-label-sm text-outline">{t.upload.pacingHeuristic}</span>
                </div>
                <div className="flex flex-col gap-2">
                  <label className="font-label-sm text-label-sm font-medium text-on-surface-variant">
                    {t.upload.strategyTitle}
                  </label>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {STRATEGIES.map((s) => {
                      const active = strategy === s.id;
                      return (
                        <button
                          key={s.id}
                          type="button"
                          aria-pressed={active}
                          onClick={() => setStrategy(s.id)}
                          className={
                            active
                              ? "p-3 rounded-xl bg-primary-fixed text-on-primary-fixed cursor-pointer flex items-start gap-2.5 shadow-xs text-left transition-all"
                              : "p-3 rounded-xl bg-surface-container hover:bg-surface-container-high text-on-surface cursor-pointer flex items-start gap-2.5 text-left transition-all"
                          }
                        >
                          <span
                            className={`material-symbols-outlined text-[20px] shrink-0 mt-0.5 ${active ? "text-primary" : "text-on-surface-variant"}`}
                            style={active ? { fontVariationSettings: "'FILL' 1" } : undefined}
                          >
                            {s.icon}
                          </span>
                          <div className="flex flex-col">
                            <span
                              className={`font-label-lg text-label-lg ${active ? "font-bold" : "font-medium"}`}
                            >
                              {s.title}
                            </span>
                            <span
                              className={`font-body-sm text-body-sm leading-tight mt-0.5 ${active ? "text-on-primary-fixed-variant" : "text-on-surface-variant"}`}
                            >
                              {s.desc}
                            </span>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="font-label-sm text-label-sm font-medium text-on-surface-variant">
                    {t.upload.captionStyleTitle}
                  </label>
                  <Dropdown
                    aria-label={t.upload.captionStyleTitle}
                    tone="container"
                    size="md"
                    className="p-2.5"
                    value={captionStyle}
                    onValueChange={setCaptionStyle}
                    options={CAPTION_STYLES}
                    renderValue={(o) => (
                      <span className="flex items-center gap-2.5 min-w-0">
                        <span className="w-8 h-8 shrink-0 rounded-sm bg-primary text-on-primary flex items-center justify-center font-bold text-xs uppercase shadow-xs">
                          CC
                        </span>
                        <span className="flex flex-col min-w-0">
                          <span className="font-label-md text-label-md font-semibold text-on-surface truncate">
                            {o.label}
                          </span>
                          <span className="font-body-sm text-body-sm text-on-surface-variant truncate">
                            {o.description}
                          </span>
                        </span>
                      </span>
                    )}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between">
                    <label
                      htmlFor="clip-instructions"
                      className="font-label-sm text-label-sm font-medium text-on-surface-variant"
                    >
                      {t.upload.instructionsTitle}
                    </label>
                    <span className="font-label-sm text-label-sm text-outline">
                      {instructions.length}/{MAX_INSTRUCTIONS}
                    </span>
                  </div>
                  <textarea
                    id="clip-instructions"
                    rows={4}
                    maxLength={MAX_INSTRUCTIONS}
                    value={instructions}
                    onChange={(e) => setInstructions(e.target.value)}
                    placeholder="e.g. Focus on the key takeaway, avoid clips that mention pricing, keep the speaker's punchline intact..."
                    className="w-full resize-y bg-surface-container rounded-lg px-3 py-2.5 text-on-surface font-body-md text-body-md focus:outline-hidden focus:ring-1 focus:ring-primary hover:bg-surface-container-high focus:bg-surface-container-lowest transition-colors"
                  />
                  <p className="font-body-sm text-body-sm text-on-surface-variant">
                    Optional guidance the AI follows when picking and cutting moments.
                  </p>
                </div>
              </div>
            </div>
          </div>{" "}
          <div className="sticky bottom-0 z-30 mt-space-lg pb-space-md">
            <div className="bg-surface-container-low/95 backdrop-blur-xl rounded-xl p-space-md shadow-[0_-4px_16px_rgba(79,55,138,0.10)] flex flex-col md:flex-row items-center justify-between gap-space-md">
              <div className="flex items-center gap-space-md">
                <div className="flex items-center justify-center w-12 h-12 rounded-full bg-secondary-container text-on-secondary-container">
                  <span className="material-symbols-outlined text-[24px]">tune</span>
                </div>
                <div>
                  <h4 className="font-title-sm text-title-sm font-medium text-on-surface">
                    Automated Production Summary
                  </h4>{" "}
                  <p className="font-body-sm text-body-sm text-on-surface-variant">
                    Preset: {ratioLabel} • {captionSummary} • Facial Tracking ON • Duration:{" "}
                    {durationRange[0]}s — {durationRange[1]}s • {targetClips}{" "}
                    {targetClips === 1 ? "clip" : "clips"}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-space-sm shrink-0">
                <div className="text-right hidden sm:block whitespace-nowrap">
                  <span className="font-label-sm text-label-sm text-outline block">
                    Estimated compute
                  </span>{" "}
                  <span className="font-label-md text-label-md font-bold text-on-surface">
                    AI Automated Pipeline
                  </span>
                </div>
                <div
                  className="flex items-stretch h-11 rounded-full bg-primary text-on-primary shadow-xs overflow-hidden"
                  role="group"
                  aria-label="Process actions"
                >
                  <button
                    className="flex items-center gap-1.5 pl-4 pr-3 whitespace-nowrap font-label-md text-label-md font-medium hover:bg-primary-container transition-colors cursor-pointer"
                    type="button"
                    onClick={() => navigate({ to: "/app/clips" })}
                  >
                    <span className="material-symbols-outlined text-[18px]">history</span>
                    <span>{t.upload.viewQueue}</span>
                  </button>
                  <span className="w-px my-2 bg-on-primary/30" aria-hidden="true"></span>
                  <button
                    className="flex items-center gap-1.5 pl-3 pr-5 whitespace-nowrap font-label-md text-label-md font-medium hover:bg-primary-container transition-colors disabled:cursor-default cursor-pointer disabled:opacity-60"
                    id="start-ai-btn"
                    type="button"
                    onClick={startProcessing}
                    disabled={processState !== "idle"}
                  >
                    {processLabel ? (
                      <>
                        <span
                          className={`material-symbols-outlined text-[18px] ${processState === "running" ? "animate-spin" : ""}`}
                          style={{ fontVariationSettings: "'FILL' 1" }}
                        >
                          {processIcon}
                        </span>
                        <span>{processLabel}</span>
                      </>
                    ) : (
                      <>
                        <span>{t.upload.startProcessing}</span>
                        <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
