/**
 * Client API & Types untuk Clipping Studio Backend (FastAPI).
 */

export interface User {
  id: number;
  username: string;
  email: string;
  display_name?: string | null;
  avatar_url?: string | null;
  credential_token?: string;
  created_at?: string;
}

export interface ClipCaption {
  start: number;
  end: number;
  text: string;
}

export interface Clip {
  id: string;
  title: string;
  start: number;
  end: number;
  hook: string;
  reason: string;
  score: number | null;
  hashtags: string[];
  captions?: ClipCaption[];
  ai_captions?: ClipCaption[];
  status: "pending" | "queued" | "rendering" | "ready" | "error";
  progress: number;
  error: string | null;
  file: string | null;
  srt: string | null;
  vtt: string | null;
  stage?: string;
  version?: number;
  publish_status?: Record<string, unknown>;
}

export interface JobLog {
  t: number;
  line: string;
}

export interface Job {
  id: string;
  name: string;
  source_type: "upload" | "url";
  created_at: number;
  status:
    | "queued"
    | "downloading"
    | "transcribing"
    | "analyzing"
    | "cutting"
    | "rendering"
    | "done"
    | "error";
  stage: string;
  progress: number;
  error: string | null;
  source?: string | null;
  meta?: {
    duration?: number;
    width?: number;
    height?: number;
    fps?: number;
    [key: string]: unknown;
  } | null;
  summary?: string | null;
  clips: Clip[];
  logs: JobLog[];
  options: {
    num_clips?: number;
    min_len?: number;
    max_len?: number;
    aspect?: string;
    layout?: string;
    subtitles?: boolean;
    remove_silence?: boolean;
    show_title?: boolean;
    instructions?: string;
    retention_hours?: number;
    [key: string]: unknown;
  };
  retention_hours?: number;
}

export interface SystemHealth {
  status: string;
  disk: {
    total_gb: number;
    used_gb: number;
    free_gb: number;
    percent: number;
  };
  ffmpeg_installed: boolean;
  active_jobs: number;
  active_tasks: number;
  timestamp: string;
}

export interface StudioConfig {
  provider: string;
  public_mode: boolean;
  providers: Record<
    string,
    {
      label: string;
      video: boolean;
      has_key: boolean;
      key_hint: string;
      model: string;
      default_model: string;
    }
  >;
  has_key: boolean;
  key_hint: string;
  model: string;
  ffmpeg: boolean;
  subtitles_supported: boolean;
  face_tracking: boolean;
  whisper_model: string;
  whisper_models: string[];
  whisper_downloaded?: Record<string, boolean>;
  whisper_language: string;
  whisper_languages: string[];
  aspects: string[];
  max_filesize_mb: number;
  max_duration_minutes: number;
  job_retention_hours: number;
  limits: {
    jobs_per_window: number;
    window_seconds: number;
    max_concurrent_jobs: number;
    max_concurrent_renders: number;
    execution_timeout_minutes: number;
  };
  media_host?: string;
  server_media_configured?: boolean;
  server_media_provider?: string | null;
  media?: Record<string, string>;
  buffer_accounts?: Array<{ id: string; name: string }>;
}

const TOKEN_KEY = "clipping_auth_token";
const SESSION_KEY = "clipping_session_id";

export function getAnonymousSessionId(): string {
  if (typeof window === "undefined" || !window.localStorage) return "default-session-id";
  try {
    let sid = window.localStorage.getItem(SESSION_KEY);
    if (!sid || sid.length < 10) {
      if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
        sid = crypto.randomUUID();
      } else {
        sid = "sess-" + Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
      }
      window.localStorage.setItem(SESSION_KEY, sid);
    }
    return sid;
  } catch {
    return "fallback-session-id";
  }
}

export function getStoredToken(): string | null {
  if (typeof window === "undefined" || !window.localStorage) return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string | null): void {
  if (typeof window === "undefined" || !window.localStorage) return;
  if (token) {
    window.localStorage.setItem(TOKEN_KEY, token);
  } else {
    window.localStorage.removeItem(TOKEN_KEY);
  }
}

export function getApiBaseUrl(): string {
  if (typeof import.meta !== "undefined" && import.meta.env?.VITE_API_URL) {
    return import.meta.env.VITE_API_URL.replace(/\/$/, "");
  }
  return "";
}

export function getMediaUrl(jobId: string, path: string): string {
  if (!path) return "";
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  const base = getApiBaseUrl();
  const cleanPath = path.startsWith("/") ? path.slice(1) : path;
  let url = `${base}/media/${jobId}/${cleanPath}`;
  const token = getStoredToken();
  const sid = getAnonymousSessionId();
  const params = new URLSearchParams();
  if (token) params.set("token", token);
  if (sid) params.set("session_id", sid);
  const q = params.toString();
  if (q) {
    url += (url.includes("?") ? "&" : "?") + q;
  }
  return url;
}

export function getWsUrl(): string {
  const base = getApiBaseUrl();
  let url = "";
  if (base) {
    const wsProto = base.startsWith("https") ? "wss:" : "ws:";
    const host = base.replace(/^https?:\/\//, "");
    url = `${wsProto}//${host}/ws`;
  } else if (typeof window !== "undefined") {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    url = `${proto}//${window.location.host}/ws`;
  } else {
    url = "ws://127.0.0.1:8765/ws";
  }
  const token = getStoredToken();
  const sid = getAnonymousSessionId();
  const params = new URLSearchParams();
  if (token) params.set("token", token);
  if (sid) params.set("session_id", sid);
  const q = params.toString();
  if (q) {
    url += (url.includes("?") ? "&" : "?") + q;
  }
  return url;
}

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export async function fetchApi<T = unknown>(
  endpoint: string,
  options: RequestInit = {},
): Promise<T> {
  const base = getApiBaseUrl();
  const cleanEndpoint = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
  const url = `${base}${cleanEndpoint}`;

  const headers = new Headers(options.headers || {});

  // Send Bearer token if present
  const token = getStoredToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  // Send consistent anonymous session ID for cross-origin tracking
  const sid = getAnonymousSessionId();
  if (sid && !headers.has("X-Session-ID")) {
    headers.set("X-Session-ID", sid);
  }

  // Set default JSON Content-Type if body is string/object and not FormData
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(url, {
    ...options,
    headers,
    credentials: "include", // Send and receive cookies across origins / proxies
  });

  if (!response.ok) {
    let errorDetail = "";
    try {
      const data = (await response.json()) as Record<string, unknown>;
      errorDetail = String(data.detail || data.message || data.error || JSON.stringify(data));
    } catch {
      errorDetail = await response.text();
    }
    throw new ApiError(
      response.status,
      errorDetail || `Request failed with status ${response.status}`,
      errorDetail,
    );
  }

  // Handle empty or file responses
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
  }
  return (await response.text()) as unknown as T;
}

// ----------------- Auth Endpoints -----------------

export const apiAuth = {
  async register(username: string, email: string, password: string) {
    const data = await fetchApi<{
      ok: boolean;
      user: User;
      token: string;
      credential_token?: string;
    }>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, email, password }),
    });
    if (data.token) setStoredToken(data.token);
    return data;
  },

  async login(username_or_email: string, password: string) {
    const data = await fetchApi<{
      ok: boolean;
      user: User;
      token: string;
      credential_token?: string;
    }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username_or_email, password }),
    });
    if (data.token) setStoredToken(data.token);
    return data;
  },

  async me() {
    return await fetchApi<{ ok: boolean; user: User | null }>("/api/auth/me");
  },

  async logout() {
    try {
      await fetchApi("/api/auth/logout", { method: "POST" });
    } finally {
      setStoredToken(null);
    }
  },

  async changeName(display_name: string) {
    return await fetchApi<{ ok: boolean; display_name: string; user?: User }>(
      "/api/profile/change-name",
      {
        method: "POST",
        body: JSON.stringify({ display_name }),
      },
    );
  },

  async changePassword(old_password: string, new_password: string) {
    return await fetchApi<{ ok: boolean }>("/api/profile/change-pw", {
      method: "POST",
      body: JSON.stringify({ old_password, new_password }),
    });
  },

  async changePhoto(avatarFile: File) {
    const formData = new FormData();
    formData.append("avatar", avatarFile);
    return await fetchApi<{ ok: boolean; avatar_url: string; user?: User }>(
      "/api/profile/change-photo",
      {
        method: "POST",
        body: formData,
      },
    );
  },

  async regenerateToken() {
    return await fetchApi<{ ok: boolean; credential_token: string }>("/api/auth/token/regenerate", {
      method: "POST",
    });
  },

  async updateCustomToken(token: string) {
    return await fetchApi<{ ok: boolean; credential_token: string }>("/api/auth/token", {
      method: "PATCH",
      body: JSON.stringify({ token }),
    });
  },
};

// ----------------- Jobs Endpoints -----------------

export const apiJobs = {
  async list(): Promise<Job[]> {
    return await fetchApi<Job[]>("/api/jobs");
  },

  async create(formData: FormData, headers?: Record<string, string>): Promise<Job> {
    return await fetchApi<Job>("/api/jobs", {
      method: "POST",
      body: formData,
      headers: headers || {},
    });
  },

  async delete(jobId: string): Promise<{ ok: boolean }> {
    return await fetchApi<{ ok: boolean }>(`/api/jobs/${jobId}`, {
      method: "DELETE",
    });
  },

  async rerender(
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
  ): Promise<Job> {
    return await fetchApi<Job>(`/api/jobs/${jobId}/rerender`, {
      method: "POST",
      body: JSON.stringify({
        aspect: options.aspect || "9:16",
        layout: options.layout || "face",
        subtitles: options.subtitles ?? true,
        remove_silence: options.remove_silence ?? true,
        show_title: options.show_title ?? true,
        logo_id: options.logo_id,
        intro_id: options.intro_id,
        outro_id: options.outro_id,
        target_clip_ids: options.target_clip_ids,
      }),
    });
  },

  async addClip(
    jobId: string,
    clip: { start: number; end: number; title: string; hook?: string },
  ): Promise<Clip> {
    return await fetchApi<Clip>(`/api/jobs/${jobId}/clips`, {
      method: "POST",
      body: JSON.stringify(clip),
    });
  },

  async updateClip(
    jobId: string,
    clipId: string,
    data: { start?: number; end?: number; title?: string; hook?: string },
  ): Promise<Clip> {
    return await fetchApi<Clip>(`/api/jobs/${jobId}/clips/${clipId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },

  async deleteClip(jobId: string, clipId: string): Promise<{ ok: boolean }> {
    return await fetchApi<{ ok: boolean }>(`/api/jobs/${jobId}/clips/${clipId}`, {
      method: "DELETE",
    });
  },

  getDownloadAllUrl(jobId: string): string {
    const base = getApiBaseUrl();
    let url = `${base}/api/jobs/${jobId}/download-all`;
    const token = getStoredToken();
    const sid = getAnonymousSessionId();
    const params = new URLSearchParams();
    if (token) params.set("token", token);
    if (sid) params.set("session_id", sid);
    const q = params.toString();
    if (q) {
      url += (url.includes("?") ? "&" : "?") + q;
    }
    return url;
  },

  async publishClip(
    jobId: string,
    clipId: string,
    channels: string[],
    text?: string,
  ): Promise<unknown> {
    return await fetchApi(`/api/jobs/${jobId}/clips/${clipId}/publish`, {
      method: "POST",
      body: JSON.stringify({ channels, text }),
    });
  },
};

// ----------------- Config & Settings Endpoints -----------------

export const apiConfig = {
  async get(): Promise<StudioConfig> {
    return await fetchApi<StudioConfig>("/api/config");
  },

  async save(
    cfg: Partial<StudioConfig> & {
      api_key?: string;
      model?: string;
      buffer_api_key?: string;
    },
  ): Promise<StudioConfig> {
    return await fetchApi<StudioConfig>("/api/config", {
      method: "POST",
      body: JSON.stringify(cfg),
    });
  },

  async getModels(
    provider?: string,
    apiKey?: string,
    model?: string,
  ): Promise<{ provider: string; models: string[] }> {
    const headers: Record<string, string> = {};
    if (provider) headers["X-AI-Provider"] = provider;
    if (apiKey) headers["X-AI-Key"] = apiKey;
    if (model) headers["X-AI-Model"] = model;
    const query = provider ? `?provider=${encodeURIComponent(provider)}` : "";
    return await fetchApi<{ provider: string; models: string[] }>(`/api/models${query}`, {
      headers,
    });
  },

  async getAiCredentials(): Promise<Record<string, unknown>> {
    return await fetchApi<Record<string, unknown>>("/api/credentials/ai");
  },

  async saveAiCredentials(data: {
    provider: string;
    key?: string;
    model?: string;
  }): Promise<Record<string, unknown>> {
    return await fetchApi<Record<string, unknown>>("/api/credentials/ai", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async deleteAiCredentials(provider?: string): Promise<{ ok: boolean }> {
    const query = provider ? `?provider=${encodeURIComponent(provider)}` : "";
    return await fetchApi<{ ok: boolean }>(`/api/credentials/ai${query}`, {
      method: "DELETE",
    });
  },

  async getMediaCredentials(): Promise<Record<string, unknown>> {
    return await fetchApi<Record<string, unknown>>("/api/credentials/media");
  },

  async saveMediaCredentials(data: {
    host: string;
    [key: string]: unknown;
  }): Promise<Record<string, unknown>> {
    return await fetchApi<Record<string, unknown>>("/api/credentials/media", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async deleteMediaCredentials(): Promise<{ ok: boolean }> {
    return await fetchApi<{ ok: boolean }>("/api/credentials/media", {
      method: "DELETE",
    });
  },

  async getHealth(): Promise<SystemHealth> {
    return await fetchApi<SystemHealth>("/api/system/health");
  },

  async getBufferAccounts(): Promise<unknown[]> {
    return await fetchApi<unknown[]>("/api/buffer/accounts");
  },

  async getBufferChannels(): Promise<unknown[]> {
    return await fetchApi<unknown[]>("/api/buffer/channels");
  },
};
