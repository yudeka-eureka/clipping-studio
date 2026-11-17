import { useNavigate } from "@tanstack/react-router";
import { useState, useEffect, useRef } from "react";
import { toast } from "sonner";

import { Toggle } from "@/components/studio/Toggle";
import { formatTimecode } from "@/lib/timecode";
import { useJobs } from "@/lib/jobs-context";
import { getMediaUrl, apiJobs, type Clip } from "@/lib/api";

type Filter = "all" | "viral" | "hook" | "broll";

const CHIP_ON =
  "px-3 py-1.5 rounded-full bg-primary text-on-primary font-label-md text-label-md font-medium shadow-xs cursor-pointer";
const CHIP_OFF =
  "px-3 py-1.5 rounded-full bg-surface-container hover:bg-surface-container-high text-on-surface font-label-md text-label-md transition-colors cursor-pointer";

const CAPTION_STYLES = [
  {
    id: "gold",
    tag: "GOLD",
    name: "Hormozi Gold",
    chip: "bg-inverse-surface font-black text-tertiary-fixed uppercase",
  },
  {
    id: "clean",
    tag: "CLEAN",
    name: "Minimalist",
    chip: "bg-surface-container-highest font-medium text-on-surface",
  },
  { id: "cyber", tag: "CYBER", name: "Cyber Violet", chip: "bg-primary font-bold text-on-primary" },
] as const;

const ANCHORS = [
  { id: "speaker1", icon: "face", label: "Speaker 1: Keynote Speaker" },
  { id: "speaker2", icon: "group", label: "Speaker 2: Stage Moderator" },
  { id: "autopan", icon: "pan_tool_alt", label: "Auto-Pan Active Voice" },
] as const;

export function ClipsPage() {
  const navigate = useNavigate();
  const { jobs, activeJob, setActiveJobId, rerenderJob, updateClip, publishClip } = useJobs();

  const [playing, setPlaying] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const [selectedClipId, setSelectedClipId] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [aspect, setAspect] = useState<"9:16" | "1:1">("9:16");
  const [captionStyle, setCaptionStyle] = useState<(typeof CAPTION_STYLES)[number]["id"]>("gold");
  const [emoji, setEmoji] = useState(true);
  const [highlightWord, setHighlightWord] = useState(true);
  const [anchor, setAnchor] = useState<(typeof ANCHORS)[number]["id"]>("speaker1");
  const [inMs, setInMs] = useState(0);
  const [outMs, setOutMs] = useState(30000);
  const [rendering, setRendering] = useState(false);

  const videoRef = useRef<HTMLVideoElement | null>(null);

  const clips: Clip[] = activeJob?.clips || [];

  // Determine active clip
  const selectedClip = clips.find((c) => c.id === selectedClipId) || clips[0] || null;

  useEffect(() => {
    if (selectedClip) {
      setSelectedClipId(selectedClip.id);
      setInMs(Math.round(selectedClip.start * 1000));
      setOutMs(Math.round(selectedClip.end * 1000));
    }
  }, [selectedClip]);

  const togglePlay = () => {
    if (!videoRef.current) return;
    if (videoRef.current.paused) {
      videoRef.current.play();
      setPlaying(true);
    } else {
      videoRef.current.pause();
      setPlaying(false);
    }
  };

  const isVisible = (clip: Clip) => {
    if (filter === "all") return true;
    if (filter === "viral") return (clip.score || 0) >= 80;
    if (filter === "hook") return !!clip.hook;
    if (filter === "broll") return true;
    return true;
  };

  const resetEdits = () => {
    if (!selectedClip) return;
    setAspect("9:16");
    setCaptionStyle("gold");
    setEmoji(true);
    setHighlightWord(true);
    setAnchor("speaker1");
    setInMs(Math.round(selectedClip.start * 1000));
    setOutMs(Math.round(selectedClip.end * 1000));
    toast.info("Pengaturan klip dikembalikan ke default.");
  };

  const handleRerender = async () => {
    if (!activeJob || !selectedClip) return;
    setRendering(true);
    try {
      // First update clip trim timestamps if modified
      if (
        inMs !== Math.round(selectedClip.start * 1000) ||
        outMs !== Math.round(selectedClip.end * 1000)
      ) {
        await updateClip(activeJob.id, selectedClip.id, {
          start: inMs / 1000,
          end: outMs / 1000,
        });
      }

      await rerenderJob(activeJob.id, {
        aspect,
        subtitles: true,
        remove_silence: true,
        target_clip_ids: [selectedClip.id],
      });

      toast.success(`Klip dirender ulang`, {
        description: `${formatTimecode(inMs)} → ${formatTimecode(outMs)} (${aspect})`,
      });
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Gagal merender ulang klip.");
    } finally {
      setRendering(false);
    }
  };

  const handleBulkExport = () => {
    if (!activeJob) return;
    setExporting(true);
    try {
      const downloadUrl = apiJobs.getDownloadAllUrl(activeJob.id);
      window.open(downloadUrl, "_blank");
      toast.success("Mempersiapkan berkas ZIP", {
        description: `${clips.length} klip sedang dikemas.`,
      });
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Gagal mengunduh ZIP.");
    } finally {
      setTimeout(() => setExporting(false), 1200);
    }
  };

  const handlePublish = async () => {
    if (!activeJob || !selectedClip) return;
    setPublishing(true);
    try {
      await publishClip(activeJob.id, selectedClip.id, ["buffer"], selectedClip.title);
      toast.success("Berhasil masuk antrean publikasi", {
        description: "Klip dikirim ke media sosial melalui Buffer.",
      });
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Gagal mengirim ke Buffer.");
    } finally {
      setPublishing(false);
    }
  };

  // If no jobs exist at all
  if (!activeJob) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] p-8 text-center">
        <div className="w-16 h-16 rounded-2xl bg-surface-container flex items-center justify-center text-primary shadow-xs mb-4">
          <span className="material-symbols-outlined text-[36px]">video_library</span>
        </div>
        <h2 className="font-headline-sm text-headline-sm text-on-surface font-semibold">
          Belum Ada Proyek Klip
        </h2>
        <p className="font-body-md text-body-md text-on-surface-variant max-w-md mt-1 mb-6">
          Unggah video panjang Anda di Studio untuk membiarkan AI menganalisis dan memotong
          momen-momen viral secara otomatis.
        </p>
        <button
          onClick={() => navigate({ to: "/app" })}
          className="inline-flex items-center gap-2 px-6 py-2.5 rounded-full bg-primary hover:bg-primary/90 text-on-primary font-label-lg text-label-lg font-semibold shadow-md transition-all cursor-pointer"
        >
          <span className="material-symbols-outlined text-[20px]">cloud_upload</span>
          <span>Buka Studio &amp; Unggah Video</span>
        </button>
      </div>
    );
  }

  const isJobProcessing = activeJob.status !== "done" && activeJob.status !== "error";
  const videoSrc = selectedClip?.file
    ? getMediaUrl(activeJob.id, selectedClip.file)
    : activeJob.source
      ? getMediaUrl(activeJob.id, activeJob.source)
      : "";

  return (
    <>
      <div className="flex flex-col w-full">
        {/* Top Header */}
        <div className="w-full px-space-md py-space-sm bg-surface-container-low shadow-xs">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-space-sm">
            <div className="flex flex-col gap-1 min-w-0">
              <div className="flex items-center gap-1.5 text-body-sm font-body-sm text-on-surface-variant">
                <span>Studio</span>
                <span>/</span>
                <span className="font-medium text-on-surface truncate max-w-xs sm:max-w-md">
                  {activeJob.name || `Proyek #${activeJob.id.slice(-6)}`}
                </span>
                <span>/</span>
                <span className="text-primary font-medium">Generated Clips</span>
              </div>
              <div className="flex flex-wrap items-center gap-2.5">
                <h1 className="font-headline-sm text-headline-sm text-on-surface tracking-tight">
                  {"Clip Results & AI Output Monitor"}
                </h1>
                {isJobProcessing ? (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-secondary-container text-on-secondary-container font-label-md text-label-md font-medium shadow-xs">
                    <span className="w-2 h-2 rounded-full bg-primary animate-pulse"></span>
                    {activeJob.stage || activeJob.status} •{" "}
                    {Math.round((activeJob.progress || 0) * 100)}%
                  </span>
                ) : activeJob.status === "error" ? (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-error-container text-on-error-container font-label-md text-label-md font-medium shadow-xs">
                    <span className="w-2 h-2 rounded-full bg-red-500"></span>
                    Gagal: {activeJob.error || "Terjadi kesalahan"}
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-secondary-container text-on-secondary-container font-label-md text-label-md font-medium shadow-xs">
                    <span className="w-2 h-2 rounded-full bg-primary"></span>
                    {clips.length} {clips.length === 1 ? "Clip" : "Clips"} Generated •{" "}
                    {activeJob.options?.aspect || "9:16"} Vertical
                  </span>
                )}
              </div>
            </div>
            <div className="flex flex-wrap items-center justify-end self-end lg:self-auto lg:ml-auto gap-2">
              <button
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-full bg-surface-container hover:bg-surface-container-high text-on-surface text-label-md font-label-md transition-colors shadow-xs cursor-pointer"
                type="button"
                onClick={() => navigate({ to: "/app" })}
              >
                <span className="material-symbols-outlined text-[18px] text-primary">replay</span>
                <span>New Project</span>
              </button>
              <button
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-full bg-primary-fixed hover:bg-primary-fixed-dim text-on-primary-fixed font-label-md text-label-md transition-colors shadow-xs cursor-pointer disabled:opacity-50"
                type="button"
                disabled={publishing || clips.length === 0}
                onClick={handlePublish}
              >
                <span className="material-symbols-outlined text-[18px]">share</span>
                <span>{publishing ? "Publishing..." : "Publish to Socials"}</span>
              </button>
              <button
                className="inline-flex items-center gap-1.5 px-5 py-2 rounded-full bg-primary hover:bg-primary/90 text-on-primary font-label-md text-label-md shadow-md hover:shadow-lg transition-all cursor-pointer disabled:opacity-50"
                type="button"
                disabled={exporting || clips.length === 0}
                onClick={handleBulkExport}
              >
                <span
                  className={`material-symbols-outlined text-[18px] ${exporting ? "animate-spin" : ""}`}
                >
                  {exporting ? "progress_activity" : "download_for_offline"}
                </span>
                <span>{exporting ? "Packaging..." : "Bulk Export (ZIP)"}</span>
              </button>
            </div>
          </div>
        </div>

        {/* Processing Banner (if in progress) */}
        {isJobProcessing && (
          <div className="mx-space-md mt-space-md p-space-md rounded-xl bg-surface-container-low border border-outline-variant/40 shadow-xs">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-primary text-[22px] animate-spin">
                  progress_activity
                </span>
                <span className="font-title-sm text-title-sm font-semibold text-on-surface">
                  {activeJob.stage || "Sedang memproses video dengan AI..."}
                </span>
              </div>
              <span className="font-mono text-primary font-bold text-sm">
                {Math.round((activeJob.progress || 0) * 100)}%
              </span>
            </div>
            <div className="w-full h-2.5 bg-surface-container-highest rounded-full overflow-hidden">
              <div
                className="h-full bg-primary transition-all duration-300 rounded-full"
                style={{ width: `${Math.max(5, Math.round((activeJob.progress || 0) * 100))}%` }}
              ></div>
            </div>
            {activeJob.logs && activeJob.logs.length > 0 && (
              <div className="mt-3 p-2.5 rounded-lg bg-surface-container text-xs font-mono text-on-surface-variant max-h-24 overflow-y-auto">
                {activeJob.logs.slice(-4).map((log, idx) => (
                  <div key={idx} className="truncate">
                    &gt; {log.line}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="w-full p-space-md flex flex-col gap-space-md">
          {/* Master Video Player */}
          <div className="w-full bg-surface-container-low rounded-xl shadow-xs overflow-hidden flex flex-col">
            <div className="px-space-md py-2.5 bg-surface-container flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-primary text-[20px]">
                  smart_display
                </span>
                <span className="font-title-sm text-title-sm text-on-surface font-semibold">
                  {"Master Player & Smart Reframe"}
                </span>
                <span className="px-2 py-0.5 rounded-sm text-label-sm font-label-sm bg-surface-container-highest text-on-surface-variant font-mono">
                  {selectedClip
                    ? `${formatTimecode(selectedClip.start * 1000)} — ${formatTimecode(selectedClip.end * 1000)}`
                    : "00:00.00"}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-1 px-2.5 py-1 rounded-full bg-surface text-on-surface text-label-sm font-label-sm shadow-xs">
                  <span className="w-2 h-2 rounded-full bg-primary"></span>
                  <span>
                    {selectedClip?.status === "ready"
                      ? "Rendered Ready"
                      : selectedClip?.status || "Analyzing"}
                  </span>
                </div>
              </div>
            </div>
            <div className="grid grid-cols-1 xl:grid-cols-12 gap-0">
              <div className="xl:col-span-8 relative bg-inverse-surface aspect-video flex items-center justify-center overflow-hidden group">
                {videoSrc ? (
                  <video
                    ref={videoRef}
                    src={videoSrc}
                    className="w-full h-full object-contain"
                    controls
                    onPlay={() => setPlaying(true)}
                    onPause={() => setPlaying(false)}
                  />
                ) : (
                  <div className="flex flex-col items-center justify-center text-on-surface-variant p-6 text-center">
                    <span className="material-symbols-outlined text-[48px] mb-2 text-primary">
                      movie
                    </span>
                    <p className="font-medium text-sm">
                      Pratinjau video akan tersedia setelah proses render.
                    </p>
                  </div>
                )}

                {/* Subtitle / Hook Overlay Preview */}
                {selectedClip?.hook && (
                  <div className="absolute top-4 inset-x-4 flex justify-center pointer-events-none">
                    <div className="px-3 py-1.5 rounded-lg bg-inverse-surface/80 backdrop-blur-md text-center max-w-md shadow-lg">
                      <p className="font-title-sm text-title-sm font-bold uppercase tracking-tight text-tertiary-fixed leading-tight drop-shadow-md">
                        &ldquo;{selectedClip.hook}&rdquo;
                      </p>
                    </div>
                  </div>
                )}
              </div>

              {/* Dynamic Transcript & Hook Insight Panel */}
              <div className="xl:col-span-4 bg-surface-container-low border-t xl:border-t-0 xl:border-l border-outline-variant/40 flex flex-col h-full max-h-[460px]">
                <div className="px-4 py-3 border-b border-outline-variant/40 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined text-primary text-[18px]">
                      psychology
                    </span>
                    <span className="font-title-sm text-title-sm font-semibold text-on-surface">
                      AI Hook &amp; Reason
                    </span>
                  </div>
                  {selectedClip?.score && (
                    <span className="px-2 py-0.5 rounded-full bg-primary-fixed text-on-primary-fixed text-xs font-bold">
                      Score {Math.round(selectedClip.score)}/100
                    </span>
                  )}
                </div>
                <div className="flex-1 overflow-y-auto p-4 space-y-3">
                  <div>
                    <span className="text-xs uppercase font-bold text-on-surface-variant tracking-wider block mb-1">
                      Clip Title
                    </span>
                    <p className="text-sm font-semibold text-on-surface">
                      {selectedClip?.title || "Untitled Clip"}
                    </p>
                  </div>

                  {selectedClip?.reason && (
                    <div>
                      <span className="text-xs uppercase font-bold text-on-surface-variant tracking-wider block mb-1">
                        Virality Reason
                      </span>
                      <p className="text-xs text-on-surface-variant leading-relaxed bg-surface-container p-2.5 rounded-lg">
                        {selectedClip.reason}
                      </p>
                    </div>
                  )}

                  {selectedClip?.hashtags && selectedClip.hashtags.length > 0 && (
                    <div>
                      <span className="text-xs uppercase font-bold text-on-surface-variant tracking-wider block mb-1">
                        Hashtags
                      </span>
                      <div className="flex flex-wrap gap-1">
                        {selectedClip.hashtags.map((h, i) => (
                          <span
                            key={i}
                            className="px-2 py-0.5 rounded-md bg-surface-container-high text-primary font-mono text-xs"
                          >
                            {h.startsWith("#") ? h : `#${h}`}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Filter Bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 bg-surface-container-low px-space-md py-3 rounded-xl shadow-xs">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-label-sm font-label-sm text-on-surface-variant font-medium mr-1">
                Filter Clips:
              </span>
              <button
                className={filter === "all" ? CHIP_ON : CHIP_OFF}
                onClick={() => setFilter("all")}
                type="button"
              >
                All Clips ({clips.length})
              </button>
              <button
                className={filter === "viral" ? CHIP_ON : CHIP_OFF}
                onClick={() => setFilter("viral")}
                type="button"
              >
                High Virality (80%+)
              </button>
              <button
                className={filter === "hook" ? CHIP_ON : CHIP_OFF}
                onClick={() => setFilter("hook")}
                type="button"
              >
                Hook Highlights
              </button>
            </div>
            <div className="text-xs text-on-surface-variant font-medium">
              Showing {clips.filter(isVisible).length} of {clips.length} moments
            </div>
          </div>

          {/* Clips Grid & Customizer */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-md items-start">
            {/* Clips Grid */}
            <div className="lg:col-span-8">
              {clips.length === 0 ? (
                <div className="p-12 text-center bg-surface-container-low rounded-2xl">
                  <span className="material-symbols-outlined text-[36px] text-outline mb-2">
                    hourglass_empty
                  </span>
                  <p className="font-medium text-sm text-on-surface">
                    Klip sedang diproses atau belum dibuat.
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-space-md">
                  {clips.filter(isVisible).map((clip, index) => {
                    const isSelected = clip.id === selectedClipId;
                    const durationSec = Math.round(clip.end - clip.start);
                    const clipDownloadUrl = clip.file ? getMediaUrl(activeJob.id, clip.file) : "";

                    return (
                      <div
                        key={clip.id}
                        role="button"
                        tabIndex={0}
                        aria-pressed={isSelected}
                        onClick={() => setSelectedClipId(clip.id)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") setSelectedClipId(clip.id);
                        }}
                        className={`group relative rounded-2xl p-3 flex flex-col gap-3 transition-all cursor-pointer ${
                          isSelected
                            ? "bg-surface-container shadow-md hover:shadow-lg ring-2 ring-primary/30"
                            : "bg-surface-container-low hover:shadow-md"
                        }`}
                      >
                        <div className="relative w-full aspect-[9/16] rounded-xl overflow-hidden bg-surface-dim flex items-center justify-center">
                          {clip.file ? (
                            <video
                              src={getMediaUrl(activeJob.id, clip.file)}
                              className="w-full h-full object-cover"
                              muted
                              playsInline
                            />
                          ) : (
                            <div className="flex flex-col items-center justify-center p-4 text-center">
                              <span className="material-symbols-outlined text-primary text-[32px] mb-1">
                                auto_awesome
                              </span>
                              <span className="text-xs text-on-surface-variant">
                                {clip.stage || clip.status}
                              </span>
                            </div>
                          )}

                          {/* Virality score badge */}
                          <div className="absolute top-2.5 left-2.5 right-2.5 flex items-center justify-between">
                            <div className="flex items-center gap-1 px-2 py-1 rounded-full bg-inverse-surface/85 backdrop-blur-md text-inverse-on-surface font-label-sm text-[11px] font-bold">
                              <span className="material-symbols-outlined text-primary-fixed text-[14px]">
                                bolt
                              </span>
                              <span>
                                {clip.score ? `${Math.round(clip.score)}/100` : "Score 90+"}
                              </span>
                            </div>
                            <span className="px-2 py-1 rounded-full bg-primary text-on-primary font-label-sm text-[11px] font-bold shadow-xs">
                              Clip {index + 1}
                            </span>
                          </div>

                          {/* Hook preview */}
                          {clip.hook && (
                            <div className="absolute inset-x-3 bottom-14 flex flex-col items-center text-center">
                              <span className="px-2 py-0.5 rounded-sm bg-surface/90 text-on-surface font-title-sm text-title-sm font-bold uppercase tracking-tight shadow-sm line-clamp-2">
                                &ldquo;{clip.hook}&rdquo;
                              </span>
                            </div>
                          )}

                          <div className="absolute bottom-2.5 left-2.5 right-2.5 flex items-center justify-between">
                            <span className="px-2 py-0.5 rounded-full bg-inverse-surface/80 backdrop-blur-md text-inverse-on-surface font-mono text-[11px]">
                              {durationSec}s
                            </span>
                            <div className="w-9 h-9 rounded-full bg-surface-container-high text-on-surface flex items-center justify-center shadow-sm group-hover:bg-primary group-hover:text-on-primary transition-colors">
                              <span className="material-symbols-outlined text-[20px]">
                                play_arrow
                              </span>
                            </div>
                          </div>
                        </div>

                        <div className="flex flex-col gap-2">
                          <div className="flex items-start justify-between gap-1">
                            <h2 className="font-title-md text-title-md font-bold text-on-surface line-clamp-1">
                              {clip.title}
                            </h2>
                            {isSelected && (
                              <span
                                className="w-2.5 h-2.5 rounded-full bg-primary mt-1.5 shrink-0"
                                title="Selected for Editor"
                              ></span>
                            )}
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            <span className="px-2 py-0.5 rounded-md bg-secondary-container text-on-secondary-container text-[11px] font-label-sm font-medium">
                              {clip.status === "ready" ? "Ready" : clip.status}
                            </span>
                            <span className="px-2 py-0.5 rounded-md bg-surface-container-high text-on-surface-variant text-[11px] font-label-sm">
                              {formatTimecode(clip.start * 1000)}
                            </span>
                          </div>
                          <div className="flex items-center justify-between pt-2">
                            <div className="flex items-center gap-1">
                              {clipDownloadUrl ? (
                                <a
                                  href={clipDownloadUrl}
                                  download
                                  className="px-3 py-1.5 rounded-full bg-primary text-on-primary text-label-sm font-label-sm font-medium hover:bg-primary/90 transition-colors inline-block"
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  Download
                                </a>
                              ) : (
                                <button
                                  className="px-3 py-1.5 rounded-full bg-surface-container-high text-outline text-label-sm font-label-sm"
                                  disabled
                                  type="button"
                                >
                                  Processing
                                </button>
                              )}
                            </div>
                            <span className="text-xs text-on-surface-variant font-mono">
                              ID: {clip.id}
                            </span>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Customizer Sidebar */}
            <div className="lg:col-span-4 flex flex-col gap-space-md">
              <div className="bg-surface-container-low rounded-2xl p-space-md shadow-xs flex flex-col gap-space-md sticky top-20">
                <div className="flex items-center justify-between pb-2">
                  <div className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded-full bg-primary"></span>
                    <h2 className="font-title-md text-title-md font-bold text-on-surface">
                      Clip Customizer
                    </h2>
                  </div>
                  <span className="text-label-sm font-label-sm px-2 py-0.5 rounded-full bg-secondary-container text-on-secondary-container font-mono">
                    ID: {selectedClip?.id || "---"}
                  </span>
                </div>
                <div className="flex flex-col gap-1.5">
                  <span className="text-label-sm font-label-sm font-medium text-on-surface-variant">
                    {"Aspect Ratio & Target Platform"}
                  </span>
                  <div className="grid grid-cols-2 p-1 rounded-xl bg-surface-container gap-1">
                    {(
                      [
                        { id: "9:16", icon: "smartphone", label: "9:16 Vertical" },
                        { id: "1:1", icon: "crop_square", label: "1:1 Square" },
                      ] as const
                    ).map((a) => (
                      <button
                        key={a.id}
                        aria-pressed={aspect === a.id}
                        onClick={() => setAspect(a.id)}
                        className={
                          aspect === a.id
                            ? "flex items-center justify-center gap-1.5 py-1.5 rounded-lg bg-surface text-on-surface font-label-sm text-label-sm font-bold shadow-xs cursor-pointer"
                            : "flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-on-surface-variant hover:text-on-surface font-label-sm text-label-sm font-medium transition-colors cursor-pointer"
                        }
                        type="button"
                      >
                        <span
                          className={`material-symbols-outlined text-[16px] ${aspect === a.id ? "text-primary" : ""}`}
                        >
                          {a.icon}
                        </span>
                        <span>{a.label}</span>
                      </button>
                    ))}
                  </div>
                </div>
                <div className="flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <span className="text-label-sm font-label-sm font-medium text-on-surface-variant">
                      {"Caption Typography & Motion"}
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    {CAPTION_STYLES.map((c) => {
                      const active = captionStyle === c.id;
                      return (
                        <button
                          key={c.id}
                          type="button"
                          aria-pressed={active}
                          onClick={() => setCaptionStyle(c.id)}
                          className={`p-2 rounded-xl flex flex-col items-center gap-1 cursor-pointer transition-colors ${
                            active
                              ? "bg-surface-bright shadow-xs ring-1 ring-primary"
                              : "bg-surface-container hover:bg-surface-bright"
                          }`}
                        >
                          <span
                            className={`w-full py-1 rounded-sm text-center text-[10px] tracking-tight ${c.chip}`}
                          >
                            {c.tag}
                          </span>
                          <span
                            className={`text-[11px] font-label-sm truncate ${active ? "font-bold text-primary" : "text-on-surface-variant"}`}
                          >
                            {c.name}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                  <div className="flex items-center justify-between p-2 rounded-lg bg-surface-container mt-1">
                    <span className="text-body-sm font-body-sm text-on-surface">
                      Auto-Emoji Injection
                    </span>
                    <Toggle
                      size="sm"
                      checked={emoji}
                      onChange={setEmoji}
                      label="Auto-Emoji Injection"
                    />
                  </div>
                  <div className="flex items-center justify-between p-2 rounded-lg bg-surface-container">
                    <span className="text-body-sm font-body-sm text-on-surface">
                      Highlight Active Spoken Word
                    </span>
                    <Toggle
                      size="sm"
                      checked={highlightWord}
                      onChange={setHighlightWord}
                      label="Highlight Active Spoken Word"
                    />
                  </div>
                </div>
                <div className="flex flex-col gap-2">
                  <span className="text-label-sm font-label-sm font-medium text-on-surface-variant">
                    Smart Reframe Tracking Anchor
                  </span>
                  <div className="flex flex-col gap-1.5" role="radiogroup">
                    {ANCHORS.map((a) => {
                      const active = anchor === a.id;
                      return (
                        <button
                          key={a.id}
                          type="button"
                          role="radio"
                          aria-checked={active}
                          onClick={() => setAnchor(a.id)}
                          className={`flex items-center justify-between p-2 rounded-lg cursor-pointer transition-colors text-left ${
                            active
                              ? "bg-primary-fixed/40"
                              : "bg-surface-container hover:bg-surface-container-high"
                          }`}
                        >
                          <div className="flex items-center gap-2">
                            <span
                              className={`material-symbols-outlined text-[18px] ${active ? "text-primary" : "text-on-surface-variant"}`}
                            >
                              {a.icon}
                            </span>
                            <span
                              className={`text-label-sm font-label-sm ${active ? "font-bold text-on-primary-fixed" : "text-on-surface"}`}
                            >
                              {a.label}
                            </span>
                          </div>
                          <span
                            className={`material-symbols-outlined text-[18px] ${active ? "text-primary" : "text-outline"}`}
                          >
                            {active ? "radio_button_checked" : "radio_button_unchecked"}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
                <div className="flex flex-col gap-2">
                  <span className="text-label-sm font-label-sm font-medium text-on-surface-variant">
                    {"Trim Points & Millisecond Nudge"}
                  </span>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="flex flex-col gap-1 bg-surface-container p-2 rounded-lg">
                      <span className="text-[10px] text-on-surface-variant uppercase font-medium">
                        In Point
                      </span>
                      <div className="flex items-center justify-between">
                        <button
                          className="w-6 h-6 rounded-sm bg-surface hover:bg-surface-bright text-on-surface font-bold text-xs cursor-pointer"
                          type="button"
                          aria-label="In point -1000 ms"
                          onClick={() => setInMs((v) => Math.max(0, v - 1000))}
                        >
                          -1s
                        </button>
                        <span className="font-mono text-xs font-bold text-primary">
                          {formatTimecode(inMs)}
                        </span>
                        <button
                          className="w-6 h-6 rounded-sm bg-surface hover:bg-surface-bright text-on-surface font-bold text-xs cursor-pointer"
                          type="button"
                          aria-label="In point +1000 ms"
                          onClick={() => setInMs((v) => v + 1000)}
                        >
                          +1s
                        </button>
                      </div>
                    </div>
                    <div className="flex flex-col gap-1 bg-surface-container p-2 rounded-lg">
                      <span className="text-[10px] text-on-surface-variant uppercase font-medium">
                        Out Point
                      </span>
                      <div className="flex items-center justify-between">
                        <button
                          className="w-6 h-6 rounded-sm bg-surface hover:bg-surface-bright text-on-surface font-bold text-xs cursor-pointer"
                          type="button"
                          aria-label="Out point -1000 ms"
                          onClick={() => setOutMs((v) => Math.max(inMs + 1000, v - 1000))}
                        >
                          -1s
                        </button>
                        <span className="font-mono text-xs font-bold text-primary">
                          {formatTimecode(outMs)}
                        </span>
                        <button
                          className="w-6 h-6 rounded-sm bg-surface hover:bg-surface-bright text-on-surface font-bold text-xs cursor-pointer"
                          type="button"
                          aria-label="Out point +1000 ms"
                          onClick={() => setOutMs((v) => v + 1000)}
                        >
                          +1s
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="flex flex-col gap-2 pt-2">
                  <button
                    className="w-full py-2.5 rounded-full bg-primary hover:bg-primary/90 text-on-primary font-label-md text-label-md font-semibold shadow-md transition-all flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50"
                    type="button"
                    disabled={rendering || !selectedClip}
                    onClick={handleRerender}
                  >
                    <span
                      className={`material-symbols-outlined text-[18px] ${rendering ? "animate-spin" : ""}`}
                    >
                      {rendering ? "progress_activity" : "movie_filter"}
                    </span>
                    <span>{rendering ? "Rendering Clip..." : "Re-render Selected Clip"}</span>
                  </button>
                  <button
                    className="w-full py-2 rounded-full bg-surface-container hover:bg-surface-container-high text-on-surface text-label-sm font-label-sm font-medium transition-colors cursor-pointer"
                    type="button"
                    onClick={resetEdits}
                  >
                    {" "}
                    Reset Edits to AI Default{" "}
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
