import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  useRef,
  type ReactNode,
} from "react";
import { apiJobs, getWsUrl, type Job, type Clip, type JobLog } from "./api";
import { useAuth } from "./auth-context";

interface JobsContextType {
  jobs: Job[];
  activeJob: Job | null;
  activeJobId: string | null;
  setActiveJobId: (id: string | null) => void;
  loading: boolean;
  wsConnected: boolean;
  refreshJobs: () => Promise<Job[]>;
  createJob: (formData: FormData, headers?: Record<string, string>) => Promise<Job>;
  deleteJob: (jobId: string) => Promise<void>;
  rerenderJob: (
    jobId: string,
    options: {
      aspect?: string;
      layout?: string;
      subtitles?: boolean;
      remove_silence?: boolean;
      show_title?: boolean;
      logo_id?: string | null;
      intro_id?: string | null;
      outro_id?: string | null;
      target_clip_ids?: string[];
    },
  ) => Promise<Job>;
  addClip: (
    jobId: string,
    clip: { start: number; end: number; title: string; hook?: string },
  ) => Promise<Clip>;
  updateClip: (
    jobId: string,
    clipId: string,
    data: { start?: number; end?: number; title?: string; hook?: string },
  ) => Promise<Clip>;
  deleteClip: (jobId: string, clipId: string) => Promise<void>;
  publishClip: (
    jobId: string,
    clipId: string,
    channels: string[],
    text?: string,
  ) => Promise<unknown>;
}

const JobsContext = createContext<JobsContextType | undefined>(undefined);

export function JobsProvider({ children }: { children: ReactNode }) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [wsConnected, setWsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refreshJobs = useCallback(async (): Promise<Job[]> => {
    try {
      const list = await apiJobs.list();
      setJobs(list);
      return list;
    } catch {
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  // Initialize and load jobs
  useEffect(() => {
    refreshJobs();
  }, [refreshJobs]);

  // Polling fallback when any job is active / in-progress
  const hasActiveJobs = jobs.some(
    (j) => j.status !== "done" && j.status !== "error",
  );

  useEffect(() => {
    if (!hasActiveJobs) return;

    const interval = setInterval(() => {
      refreshJobs();
    }, 3500);

    return () => clearInterval(interval);
  }, [hasActiveJobs, refreshJobs]);

  let currentUserId: string | number | undefined;
  try {
    const auth = useAuth();
    currentUserId = auth?.user?.id;
  } catch {
    // If mounted outside AuthProvider (e.g. standalone tests)
  }

  // WebSocket connection for real-time updates (reconnects when auth user changes)
  useEffect(() => {
    let unmounted = false;
    let pingInterval: ReturnType<typeof setInterval> | null = null;

    function connectWs() {
      if (unmounted) return;
      try {
        if (pingInterval) clearInterval(pingInterval);
        const wsUrl = getWsUrl();
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          if (unmounted) return;
          setWsConnected(true);
          // Heartbeat ping every 20s to prevent reverse proxy (Nginx/Cloudflare) timeouts
          pingInterval = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
              ws.send("ping");
            }
          }, 20000);
        };

        ws.onmessage = (event) => {
          if (unmounted) return;
          try {
            const data = JSON.parse(event.data);
            if (data.type === "snapshot" && Array.isArray(data.jobs)) {
              setJobs(data.jobs);
            } else if (data.type === "job" && data.job) {
              const updatedJob: Job = data.job;
              setJobs((prev) => {
                const idx = prev.findIndex((j) => j.id === updatedJob.id);
                if (idx >= 0) {
                  const next = [...prev];
                  next[idx] = updatedJob;
                  return next;
                }
                return [updatedJob, ...prev];
              });
            } else if (data.type === "progress" && data.job_id) {
              const progressVal =
                typeof data.progress === "number"
                  ? data.progress
                  : typeof data.value === "number"
                  ? data.value
                  : undefined;
              setJobs((prev) =>
                prev.map((j) => {
                  if (j.id !== data.job_id) return j;
                  if (data.clip_id) {
                    const clips = j.clips.map((c) => {
                      if (c.id !== data.clip_id) return c;
                      return {
                        ...c,
                        progress: progressVal ?? c.progress,
                        stage: data.stage ?? c.stage,
                      };
                    });
                    const avgProgress =
                      clips.length > 0
                        ? clips.reduce((acc, c) => acc + (c.progress || 0), 0) / clips.length
                        : j.progress;
                    return { ...j, clips, progress: avgProgress };
                  }
                  return {
                    ...j,
                    progress: progressVal ?? j.progress,
                    stage: data.stage ?? j.stage,
                  };
                }),
              );
            } else if (data.type === "log" && data.job_id) {
              const logEntry: JobLog = { t: data.t || Date.now() / 1000, line: data.line || "" };
              setJobs((prev) =>
                prev.map((j) => {
                  if (j.id !== data.job_id) return j;
                  return {
                    ...j,
                    logs: [...(j.logs || []), logEntry],
                  };
                }),
              );
            } else if (data.type === "deleted" && data.job_id) {
              setJobs((prev) => prev.filter((j) => j.id !== data.job_id));
            }
          } catch {
            // Ignore malformed WS payloads
          }
        };

        ws.onclose = () => {
          if (pingInterval) clearInterval(pingInterval);
          if (unmounted) return;
          setWsConnected(false);
          // Try reconnect after 3 seconds
          reconnectTimeoutRef.current = setTimeout(connectWs, 3000);
        };

        ws.onerror = () => {
          if (pingInterval) clearInterval(pingInterval);
          ws.close();
        };
      } catch {
        if (!unmounted) {
          reconnectTimeoutRef.current = setTimeout(connectWs, 3000);
        }
      }
    }

    connectWs();
    refreshJobs();

    return () => {
      unmounted = true;
      if (pingInterval) clearInterval(pingInterval);
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [currentUserId, refreshJobs]);

  const createJob = async (formData: FormData, headers?: Record<string, string>): Promise<Job> => {
    const job = await apiJobs.create(formData, headers);
    setJobs((prev) => [job, ...prev]);
    setActiveJobId(job.id);
    return job;
  };

  const deleteJob = async (jobId: string): Promise<void> => {
    await apiJobs.delete(jobId);
    setJobs((prev) => prev.filter((j) => j.id !== jobId));
    if (activeJobId === jobId) {
      setActiveJobId(null);
    }
  };

  const rerenderJob = async (
    jobId: string,
    options: Parameters<typeof apiJobs.rerender>[1],
  ): Promise<Job> => {
    const job = await apiJobs.rerender(jobId, options);
    setJobs((prev) => prev.map((j) => (j.id === jobId ? job : j)));
    return job;
  };

  const addClip = async (
    jobId: string,
    clip: { start: number; end: number; title: string; hook?: string },
  ): Promise<Clip> => {
    const newClip = await apiJobs.addClip(jobId, clip);
    await refreshJobs();
    return newClip;
  };

  const updateClip = async (
    jobId: string,
    clipId: string,
    data: { start?: number; end?: number; title?: string; hook?: string },
  ): Promise<Clip> => {
    const updated = await apiJobs.updateClip(jobId, clipId, data);
    setJobs((prev) =>
      prev.map((j) => {
        if (j.id !== jobId) return j;
        return {
          ...j,
          clips: j.clips.map((c) => (c.id === clipId ? updated : c)),
        };
      }),
    );
    return updated;
  };

  const deleteClip = async (jobId: string, clipId: string): Promise<void> => {
    await apiJobs.deleteClip(jobId, clipId);
    setJobs((prev) =>
      prev.map((j) => {
        if (j.id !== jobId) return j;
        return {
          ...j,
          clips: j.clips.filter((c) => c.id !== clipId),
        };
      }),
    );
  };

  const publishClip = async (
    jobId: string,
    clipId: string,
    channels: string[],
    text?: string,
  ): Promise<unknown> => {
    const res = await apiJobs.publishClip(jobId, clipId, channels, text);
    await refreshJobs();
    return res;
  };

  // Find active job
  const activeJob = jobs.find((j) => j.id === activeJobId) || jobs[0] || null;

  return (
    <JobsContext.Provider
      value={{
        jobs,
        activeJob,
        activeJobId,
        setActiveJobId,
        loading,
        wsConnected,
        refreshJobs,
        createJob,
        deleteJob,
        rerenderJob,
        addClip,
        updateClip,
        deleteClip,
        publishClip,
      }}
    >
      {children}
    </JobsContext.Provider>
  );
}

export function useJobs(): JobsContextType {
  const context = useContext(JobsContext);
  if (!context) {
    throw new Error("useJobs must be used within a JobsProvider");
  }
  return context;
}
