/** Settings-page rules: hook provider/version and its API key, cloud storage, passwords. */

export type KeyProvider = "openai" | "gemini" | "anthropic";
export type HookProviderId = KeyProvider | "clipai";

export type ModelVersion = { id: string; label: string; hint: string };

/**
 * Hook detection is chosen as provider + version. `versions` are known offline;
 * `remoteVersions` only appear after the user checks for available versions.
 */
export const HOOK_PROVIDERS: Record<
  HookProviderId,
  {
    label: string;
    icon: string;
    keyProvider: KeyProvider | null;
    versions: ModelVersion[];
    remoteVersions: ModelVersion[];
  }
> = {
  gemini: {
    label: "Google Gemini",
    icon: "auto_awesome",
    keyProvider: "gemini",
    versions: [
      {
        id: "gemini-1.5-pro",
        label: "Gemini 1.5 Pro",
        hint: "Multimodal video analysis with precise cut timestamps.",
      },
      {
        id: "gemini-1.5-flash",
        label: "Gemini 1.5 Flash",
        hint: "Faster and cheaper, slightly looser cut points.",
      },
    ],
    remoteVersions: [
      {
        id: "gemini-2.5-pro",
        label: "Gemini 2.5 Pro",
        hint: "Newest multimodal model with longer video context.",
      },
    ],
  },
  openai: {
    label: "OpenAI",
    icon: "bolt",
    keyProvider: "openai",
    versions: [
      {
        id: "gpt-4o",
        label: "GPT-4o",
        hint: "Native vision, strong at visual hooks and reactions.",
      },
      { id: "gpt-4o-mini", label: "GPT-4o mini", hint: "Lower cost, good for short-form sources." },
    ],
    remoteVersions: [
      { id: "gpt-4.1", label: "GPT-4.1", hint: "Improved long-context transcript reasoning." },
    ],
  },
  anthropic: {
    label: "Anthropic",
    icon: "forum",
    keyProvider: "anthropic",
    versions: [
      {
        id: "claude-3.5-sonnet",
        label: "Claude 3.5 Sonnet",
        hint: "Best for story-driven podcasts and narrative arcs.",
      },
      { id: "claude-3-haiku", label: "Claude 3 Haiku", hint: "Fast transcript-only hook scoring." },
    ],
    remoteVersions: [
      { id: "claude-sonnet-4", label: "Claude Sonnet 4", hint: "Newest narrative-flow model." },
    ],
  },
  clipai: {
    label: "ClipAI Turbo-Local",
    icon: "memory",
    keyProvider: null,
    versions: [
      {
        id: "turbo-local-v2",
        label: "Turbo-Local v2",
        hint: "Runs on ClipAI GPUs and uses your Studio quota minutes.",
      },
    ],
    remoteVersions: [
      {
        id: "turbo-local-v3",
        label: "Turbo-Local v3 (Beta)",
        hint: "Beta on-device model with faster reframing.",
      },
    ],
  },
};

/** The only API key field shown is the one for the chosen provider; ClipAI needs none. */
export function keyProviderFor(provider: HookProviderId): KeyProvider | null {
  return HOOK_PROVIDERS[provider].keyProvider;
}

/** Checking available versions needs the provider's API key (ClipAI needs none). */
export function canRefreshVersions(provider: HookProviderId, apiKey: string): boolean {
  return keyProviderFor(provider) === null || apiKey.trim().length > 0;
}

/** Versions offered for a provider, including remote ones once they've been checked. */
export function versionsFor(provider: HookProviderId, refreshed: boolean): ModelVersion[] {
  const p = HOOK_PROVIDERS[provider];
  return refreshed ? [...p.remoteVersions, ...p.versions] : p.versions;
}

/** Saved keys are shown masked, keeping only the last 4 characters. */
export function maskApiKey(key: string): string {
  if (!key) return "";
  if (key.length <= 4) return "•".repeat(key.length);
  return `${"•".repeat(8)}${key.slice(-4)}`;
}

export const WHISPER_MODELS = ["small", "medium", "large"] as const;
export type WhisperModel = (typeof WHISPER_MODELS)[number];

export type StorageProvider = "standard" | "cloudinary" | "r2";

export type StorageField = { id: string; label: string; secret?: boolean; placeholder: string };

export const STORAGE_PROVIDERS: Record<
  StorageProvider,
  { label: string; icon: string; fields: StorageField[] }
> = {
  standard: { label: "Server Standard", icon: "cloud", fields: [] },
  cloudinary: {
    label: "Cloudinary",
    icon: "photo_library",
    fields: [
      { id: "cloud-name", label: "Cloud Name", secret: true, placeholder: "my-studio" },
      { id: "api-key", label: "API Key", secret: true, placeholder: "123456789012345" },
      { id: "api-secret", label: "API Secret", secret: true, placeholder: "••••••••••••••••" },
    ],
  },
  r2: {
    label: "Cloudflare R2",
    icon: "cloud_upload",
    fields: [
      { id: "account-id", label: "Account ID", secret: true, placeholder: "a1b2c3d4e5f6..." },
      { id: "bucket", label: "Bucket Name", secret: true, placeholder: "clipai-exports" },
      { id: "access-key-id", label: "Access Key ID", secret: true, placeholder: "AKIA..." },
      {
        id: "secret-access-key",
        label: "Secret Access Key",
        secret: true,
        placeholder: "••••••••••••••••",
      },
      { id: "public-url", label: "Public Bucket URL", placeholder: "https://pub-xxxx.r2.dev" },
    ],
  },
};

/** Standard storage keeps files for a fixed 4 hours. */
export const STANDARD_RETENTION_HOURS = 4;

/** Retention can only be customised on the user's own storage (Cloudinary or R2). */
export function canCustomizeRetention(provider: StorageProvider): boolean {
  return provider !== "standard";
}

/** Change-password rules: same strength rule as sign-up (8+ chars with a number and a symbol). */
export const PASSWORD_MIN_LENGTH = 8;

export type PasswordChange = { current: string; next: string; confirm: string };
export type PasswordErrors = Partial<Record<keyof PasswordChange, string>>;

export function validatePasswordChange({ current, next, confirm }: PasswordChange): PasswordErrors {
  const errors: PasswordErrors = {};
  if (!current) errors.current = "Enter your current password.";
  if (next.length < PASSWORD_MIN_LENGTH || !/\d/.test(next) || !/[^A-Za-z0-9]/.test(next)) {
    errors.next = `Use at least ${PASSWORD_MIN_LENGTH} characters with numbers & symbols.`;
  } else if (current && next === current) {
    errors.next = "New password must be different from your current one.";
  }
  if (confirm !== next || !confirm) errors.confirm = "Passwords don't match.";
  return errors;
}
