import { useRef, useState, useEffect, type ReactNode } from "react";
import { toast } from "sonner";

import { PROFILE_URL } from "@/components/layout/AppShell";
import { ApiKeyDialog } from "@/components/studio/ApiKeyDialog";
import { ChangePasswordDialog } from "@/components/studio/ChangePasswordDialog";
import { Dropdown } from "@/components/studio/Dropdown";
import { useAuth } from "@/lib/auth-context";
import { apiConfig, apiAuth, type StudioConfig } from "@/lib/api";
import {
  HOOK_PROVIDERS,
  STANDARD_RETENTION_HOURS,
  STORAGE_PROVIDERS,
  WHISPER_MODELS,
  canCustomizeRetention,
  canRefreshVersions,
  keyProviderFor,
  maskApiKey,
  versionsFor,
  type HookProviderId,
  type KeyProvider,
  type StorageProvider,
  type WhisperModel,
} from "@/lib/settings";

const RES_OPTIONS = [
  { id: "1080p", icon: "hd", label: "1080p 60fps" },
  { id: "4k", icon: "4k", label: "4K UltraHD" },
  { id: "720p", icon: "smartphone", label: "720p Mobile" },
] as const;

const LANGUAGES = [
  "English (US)",
  "English (UK)",
  "Indonesian (ID)",
  "Spanish (ES / LATAM)",
  "German (DE)",
  "French (FR)",
  "Japanese (JA)",
];

const NICHES = [
  "Tech & AI Product Reviews",
  "Finance & Market Breakdowns",
  "Software Engineering & Dev Tutorials",
  "Startup Founder Stories & Podcasts",
  "Gaming Highlights & Stream Clips",
];

const RETENTION_UNITS = [
  { value: "hours", label: "Hours" },
  { value: "days", label: "Days" },
  { value: "weeks", label: "Weeks" },
  { value: "months", label: "Months" },
];

const PROVIDER_KEYS: Record<KeyProvider, { label: string; placeholder: string }> = {
  gemini: { label: "Google Gemini API Key", placeholder: "AIzaSy..." },
  openai: { label: "OpenAI API Key", placeholder: "sk-proj-..." },
  anthropic: { label: "Anthropic API Key", placeholder: "sk-ant-..." },
};

type TestStatus = "idle" | "pinging" | "ok";
type KeyId = KeyProvider | "buffer";

function SettingSwitch({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
}) {
  return (
    <button
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`shrink-0 w-12 h-7 rounded-full p-0.5 transition-colors relative flex items-center cursor-pointer ${
        checked ? "bg-primary-container" : "bg-surface-container-highest"
      }`}
      role="switch"
      type="button"
    >
      <span
        className={`block w-6 h-6 rounded-full shadow-xs transition-transform flex items-center justify-center ${
          checked ? "translate-x-5 bg-on-primary" : "translate-x-0 bg-surface-container-lowest"
        }`}
      >
        <span
          className={`material-symbols-outlined text-[14px] ${checked ? "text-primary" : "text-outline"}`}
        >
          {checked ? "check" : "remove"}
        </span>
      </span>
    </button>
  );
}

function RevealButton({ shown, onToggle }: { shown: boolean; onToggle: () => void }) {
  return (
    <button
      className="p-1 rounded-full text-outline hover:text-on-surface cursor-pointer"
      type="button"
      aria-label={shown ? "Hide key" : "Show key"}
      onClick={onToggle}
    >
      <span className="material-symbols-outlined text-[18px]">
        {shown ? "visibility_off" : "visibility"}
      </span>
    </button>
  );
}

function boxClass(tone: "lowest" | "container" = "lowest") {
  return `relative flex items-center h-10 rounded-lg px-space-sm focus-within:ring-2 focus-within:ring-primary ${
    tone === "lowest" ? "bg-surface-container-lowest" : "bg-surface-container"
  }`;
}

function Field({
  label,
  htmlFor,
  hint,
  children,
}: {
  label: string;
  htmlFor?: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5 min-w-0">
      <label
        className="font-label-md text-label-md text-on-surface-variant font-medium"
        htmlFor={htmlFor}
      >
        {label}
      </label>
      {children}
      {hint && <span className="font-label-sm text-label-sm text-on-surface-variant">{hint}</span>}
    </div>
  );
}

function TextBox({
  icon,
  ...props
}: { icon: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div className={boxClass()}>
      <span className="material-symbols-outlined text-outline text-[18px] mr-2 shrink-0">
        {icon}
      </span>
      <input
        type="text"
        className="bg-transparent w-full min-w-0 text-on-surface placeholder:text-outline font-body-sm text-body-sm outline-hidden"
        {...props}
      />
    </div>
  );
}

function SecretInput({
  id,
  icon,
  value,
  onChange,
  placeholder,
  shown,
  onToggle,
  tone,
  ...props
}: {
  id: string;
  icon: string;
  value?: string;
  onChange?: (v: string) => void;
  placeholder?: string;
  shown: boolean;
  onToggle: () => void;
  tone?: "lowest" | "container";
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, "onChange" | "value">) {
  return (
    <div className={boxClass(tone)}>
      <span className="material-symbols-outlined text-outline text-[18px] mr-2 shrink-0">
        {icon}
      </span>
      <input
        id={id}
        type={shown ? "text" : "password"}
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        placeholder={placeholder}
        className="bg-transparent w-full min-w-0 text-on-surface placeholder:text-outline font-body-sm text-body-sm outline-hidden"
        {...props}
      />
      <RevealButton shown={shown} onToggle={onToggle} />
    </div>
  );
}

function TestButton({
  status,
  disabled,
  onClick,
}: {
  status: TestStatus;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className={`px-2.5 py-0.5 rounded-full font-label-sm text-label-sm font-medium transition-colors disabled:opacity-50 cursor-pointer ${
        status === "ok"
          ? "bg-primary-fixed text-on-primary-fixed"
          : "bg-secondary-container text-on-secondary-container hover:bg-secondary-fixed"
      }`}
      type="button"
      disabled={disabled || status === "pinging"}
      onClick={onClick}
    >
      {status === "pinging" ? "Testing..." : status === "ok" ? "Connected ✓" : "Test Connection"}
    </button>
  );
}

function RuleCard({
  icon,
  title,
  description,
  action,
  children,
}: {
  icon: string;
  title: string;
  description: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="p-space-md rounded-xl bg-surface-container flex flex-col gap-space-sm">
      <div className="flex items-start justify-between gap-space-md">
        <div className="flex items-start gap-space-sm min-w-0">
          <div className="w-8 h-8 rounded-lg bg-primary-fixed/60 flex items-center justify-center text-primary shrink-0 mt-0.5">
            <span className="material-symbols-outlined text-[18px]">{icon}</span>
          </div>
          <div className="flex flex-col">
            <h3 className="font-title-sm text-title-sm text-on-surface font-medium">{title}</h3>
            <span className="font-body-sm text-body-sm text-on-surface-variant">{description}</span>
          </div>
        </div>
        {action}
      </div>
      <div className="sm:pl-11 flex flex-col gap-space-sm pt-1">{children}</div>
    </section>
  );
}

const DEFAULTS = {
  resolution: "1080p" as (typeof RES_OPTIONS)[number]["id"],
  provider: "gemini" as HookProviderId,
  version: "gemini-1.5-pro",
  captions: true,
  whisper: "medium" as WhisperModel,
  publish: true,
  storage: "standard" as StorageProvider,
};

export function SettingsPage() {
  const { user, updateDisplayName, updatePhoto, refreshUser } = useAuth();
  const avatarInput = useRef<HTMLInputElement>(null);

  const [formKey, setFormKey] = useState(0);
  const [saved, setSaved] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [resolution, setResolution] = useState(DEFAULTS.resolution);
  const [provider, setProvider] = useState<HookProviderId>(DEFAULTS.provider);
  const [version, setVersion] = useState(DEFAULTS.version);
  const [refreshed, setRefreshed] = useState<Partial<Record<HookProviderId, boolean>>>({});
  const [refreshing, setRefreshing] = useState(false);
  const [keyDialogOpen, setKeyDialogOpen] = useState(false);
  const [captions, setCaptions] = useState(DEFAULTS.captions);
  const [whisper, setWhisper] = useState<WhisperModel>(DEFAULTS.whisper);
  const [publish, setPublish] = useState(DEFAULTS.publish);
  const [storage, setStorage] = useState<StorageProvider>(DEFAULTS.storage);
  const [bufferAccount, setBufferAccount] = useState("");
  const [storageRetention, setStorageRetention] = useState("30");
  const [retentionUnit, setRetentionUnit] = useState("days");
  const [storageCreds, setStorageCreds] = useState<Record<string, string>>({
    "cloudinary-cloud-name": "",
    "cloudinary-api-key": "",
    "cloudinary-api-secret": "",
    "r2-account-id": "",
    "r2-bucket": "",
    "r2-access-key-id": "",
    "r2-secret-access-key": "",
    "r2-public-url": "",
  });

  const [displayNameInput, setDisplayNameInput] = useState(
    user?.display_name || user?.username || "",
  );
  const [shownKeys, setShownKeys] = useState<Record<string, boolean>>({});
  const [apiKeys, setApiKeys] = useState<Record<KeyId, string>>({
    gemini: "",
    openai: "",
    anthropic: "",
    buffer: "",
  });
  const [keyStatus, setKeyStatus] = useState<Record<KeyId, TestStatus>>({
    gemini: "idle",
    openai: "idle",
    anthropic: "idle",
    buffer: "idle",
  });

  const toggleKey = (key: string) => {
    setShownKeys((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  // Load config from backend
  useEffect(() => {
    let mounted = true;
    apiConfig
      .get()
      .then((cfg: StudioConfig) => {
        if (!mounted) return;
        if (cfg.provider && cfg.provider in HOOK_PROVIDERS) {
          setProvider(cfg.provider as HookProviderId);
        }
        if (cfg.model) {
          setVersion(cfg.model);
        }
        if (cfg.whisper_model) {
          setWhisper(cfg.whisper_model as WhisperModel);
        }

        if (cfg.buffer_accounts && cfg.buffer_accounts.length > 0) {
          setBufferAccount(cfg.buffer_accounts[0].name || cfg.buffer_accounts[0].id);
        }

        // Check has_key from backend
        const provs = cfg.providers || {};
        setApiKeys((prev) => {
          const next = { ...prev };
          for (const p of ["gemini", "openai", "anthropic"] as KeyProvider[]) {
            if (provs[p]?.has_key) {
              next[p] = provs[p].key_hint || "••••••••••••";
            }
          }
          return next;
        });
        setKeyStatus((prev) => {
          const next = { ...prev };
          for (const p of ["gemini", "openai", "anthropic"] as KeyProvider[]) {
            if (provs[p]?.has_key) {
              next[p] = "ok";
            }
          }
          return next;
        });
      })
      .catch(() => {});

    // Load media credentials
    apiConfig
      .getMediaCredentials()
      .then((res: Record<string, unknown>) => {
        if (!mounted) return;
        const host = res.host as string;
        if (host === "cloudinary" || host === "r2") {
          setStorage(host as StorageProvider);
        } else if (host === "default") {
          setStorage("standard");
        }
        const fields = res.fields as Record<string, Record<string, unknown>> | undefined;
        if (fields) {
          setStorageCreds((prev) => {
            const next = { ...prev };
            if (fields.cloudinary) {
              if (fields.cloudinary.cloud_name) {
                next["cloudinary-cloud-name"] = String(fields.cloudinary.cloud_name);
              }
              if (fields.cloudinary.has_key) {
                next["cloudinary-api-key"] = "••••••••••••••••";
              }
              if (fields.cloudinary.has_secret) {
                next["cloudinary-api-secret"] = "••••••••••••••••";
              }
            }
            if (fields.r2) {
              if (fields.r2.account_id) {
                next["r2-account-id"] = String(fields.r2.account_id);
              }
              if (fields.r2.bucket) {
                next["r2-bucket"] = String(fields.r2.bucket);
              }
              if (fields.r2.has_access_key) {
                next["r2-access-key-id"] = "••••••••••••••••";
              }
              if (fields.r2.has_secret_access_key) {
                next["r2-secret-access-key"] = "••••••••••••••••";
              }
              if (fields.r2.public_url) {
                next["r2-public-url"] = String(fields.r2.public_url);
              }
            }
            return next;
          });
        }
      })
      .catch(() => {});

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (user) {
      setDisplayNameInput(user.display_name || user.username || "");
    }
  }, [user]);

  const keyProvider = keyProviderFor(provider);
  const providerInfo = HOOK_PROVIDERS[provider] || HOOK_PROVIDERS.gemini;
  const versions = versionsFor(provider, !!refreshed[provider]);
  const versionInfo = versions.find((v) => v.id === version) ?? versions[0]!;
  const providerKey = keyProvider ? apiKeys[keyProvider] : "";
  const canRefresh = canRefreshVersions(provider, providerKey);

  const changeProvider = (p: HookProviderId) => {
    setProvider(p);
    setVersion(versionsFor(p, !!refreshed[p])[0]!.id);
  };

  const refreshVersions = async () => {
    const p = provider;
    setRefreshing(true);
    try {
      if (keyProvider) {
        const res = await apiConfig.getModels(keyProvider);
        if (res.models && res.models.length > 0) {
          setRefreshed((r) => ({ ...r, [p]: true }));
          toast.success(`Ditemukan model ${HOOK_PROVIDERS[p].label}`, {
            description: `${res.models.length} model aktif tersedia.`,
          });
          return;
        }
      }
      setRefreshed((r) => ({ ...r, [p]: true }));
      toast(`${HOOK_PROVIDERS[p].label} model up to date.`);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Gagal mengambil daftar model.");
    } finally {
      setRefreshing(false);
    }
  };

  const runTest = async (id: KeyId) => {
    if (id === "buffer") {
      setKeyStatus((s) => ({ ...s, [id]: "pinging" }));
      setTimeout(() => setKeyStatus((s) => ({ ...s, [id]: "ok" })), 500);
      return;
    }

    setKeyStatus((s) => ({ ...s, [id]: "pinging" }));
    try {
      await apiConfig.getModels(id);
      setKeyStatus((s) => ({ ...s, [id]: "ok" }));
      toast.success(`Koneksi ${HOOK_PROVIDERS[id as HookProviderId]?.label || id} Berhasil!`);
    } catch (err: unknown) {
      setKeyStatus((s) => ({ ...s, [id]: "idle" }));
      toast.error(err instanceof Error ? err.message : `Koneksi gagal. Periksa API key ${id}.`);
    }
  };

  const handleAvatarChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      await updatePhoto(file);
      toast.success("Foto profil berhasil diperbarui.");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Gagal mengunggah foto profil.");
    }
  };

  const handleRegenerateToken = async () => {
    try {
      const res = await apiAuth.regenerateToken();
      await refreshUser();
      toast.success("Credential token berhasil diperbarui!", {
        description: `Token baru: ${res.credential_token.slice(0, 10)}...`,
      });
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Gagal memperbarui token.");
    }
  };

  const saveAll = async () => {
    try {
      // 1. Update Display Name if changed
      if (
        user &&
        displayNameInput.trim() &&
        displayNameInput.trim() !== (user.display_name || user.username)
      ) {
        await updateDisplayName(displayNameInput.trim());
      }

      // 2. Save global config
      await apiConfig.save({
        provider: provider in HOOK_PROVIDERS && keyProvider ? provider : undefined,
        model: version,
        whisper_model: whisper,
        buffer_api_key:
          publish && apiKeys.buffer && !apiKeys.buffer.startsWith("••••")
            ? apiKeys.buffer
            : undefined,
      });

      // 3. Save Media Credentials
      if (storage === "standard") {
        await apiConfig.saveMediaCredentials({ host: "default" });
      } else if (storage === "cloudinary") {
        const creds: Record<string, string> = {};
        const cn = storageCreds["cloudinary-cloud-name"];
        const ak = storageCreds["cloudinary-api-key"];
        const sec = storageCreds["cloudinary-api-secret"];
        if (cn && !cn.startsWith("••••")) creds.cloud_name = cn;
        if (ak && !ak.startsWith("••••")) creds.api_key = ak;
        if (sec && !sec.startsWith("••••")) creds.api_secret = sec;
        if (Object.keys(creds).length > 0) {
          await apiConfig.saveMediaCredentials({
            host: "cloudinary",
            credentials: creds,
          });
        }
      } else if (storage === "r2") {
        const creds: Record<string, string> = {};
        const acc = storageCreds["r2-account-id"];
        const bkt = storageCreds["r2-bucket"];
        const ak = storageCreds["r2-access-key-id"];
        const sak = storageCreds["r2-secret-access-key"];
        const pub = storageCreds["r2-public-url"];
        if (acc && !acc.startsWith("••••")) creds.account_id = acc;
        if (bkt && !bkt.startsWith("••••")) creds.bucket = bkt;
        if (ak && !ak.startsWith("••••")) creds.access_key_id = ak;
        if (sak && !sak.startsWith("••••")) creds.secret_access_key = sak;
        if (pub) creds.public_url = pub;
        if (Object.keys(creds).length > 0) {
          await apiConfig.saveMediaCredentials({
            host: "r2",
            credentials: creds,
          });
        }
      }

      setSaved(true);
      window.scrollTo({ top: 0, behavior: "smooth" });
      toast.success("Pengaturan berhasil disimpan.");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Gagal menyimpan pengaturan.");
    }
  };

  const discard = () => {
    setResolution(DEFAULTS.resolution);
    setProvider(DEFAULTS.provider);
    setVersion(DEFAULTS.version);
    setRefreshed({});
    setCaptions(DEFAULTS.captions);
    setWhisper(DEFAULTS.whisper);
    setPublish(DEFAULTS.publish);
    setStorage(DEFAULTS.storage);
    setBufferAccount("");
    setDisplayNameInput(user?.display_name || user?.username || "");
    setSaved(false);
    setFormKey((k) => k + 1);
  };

  return (
    <>
      <div className="flex flex-col w-full">
        <div className="relative w-full max-w-7xl mx-auto px-space-md sm:px-space-lg lg:px-space-xl py-space-lg flex flex-col gap-space-lg">
          <section className="flex flex-col lg:flex-row lg:items-center justify-between gap-space-md pb-space-xs">
            <div className="flex flex-col gap-1 min-w-0">
              <div className="flex items-center gap-space-xs">
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-secondary-container text-on-secondary-container font-label-sm text-label-sm">
                  <span className="material-symbols-outlined text-[14px]">tune</span> System
                  Preferences{" "}
                </span>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-surface-container-high text-on-surface-variant font-label-sm text-label-sm">
                  v3.4.2 Production{" "}
                </span>
              </div>
              <h1 className="font-headline-lg text-headline-lg text-on-surface font-normal tracking-tight">
                {"Studio Settings & Preferences"}
              </h1>
              <p className="font-body-md text-body-md text-on-surface-variant max-w-3xl">
                {" "}
                Manage your creator profile, configure custom AI model API keys, and default
                rendering engine preferences.{" "}
              </p>
            </div>
            <div className="flex items-center gap-space-sm self-start lg:self-center shrink-0">
              <button
                className="px-space-md py-2.5 rounded-full text-primary hover:bg-primary-fixed/30 font-label-lg text-label-lg transition-colors flex items-center gap-1.5 cursor-pointer"
                type="button"
                onClick={discard}
              >
                <span className="material-symbols-outlined text-[18px]">replay</span> Discard{" "}
              </button>
              <button
                className="px-space-lg py-2.5 rounded-full bg-primary hover:bg-primary/90 text-on-primary font-label-lg text-label-lg shadow-xs hover:shadow-md transition-all flex items-center gap-2 cursor-pointer"
                id="save-btn"
                type="button"
                onClick={saveAll}
              >
                <span className="material-symbols-outlined text-[18px]">check</span>
                <span>Save Changes</span>
              </button>
            </div>
          </section>

          {saved && (
            <div
              className="flex transition-all duration-300 w-full p-space-sm rounded-xl bg-secondary-container text-on-secondary-container items-center justify-between shadow-xs"
              id="save-banner"
            >
              <div className="flex items-center gap-space-xs">
                <span
                  className="material-symbols-outlined text-primary text-[20px]"
                  style={{ fontVariationSettings: "'FILL' 1" }}
                >
                  check_circle
                </span>
                <span className="font-body-md text-body-md font-medium">
                  All settings updated successfully. AI pipeline will use selected credentials on
                  next job.
                </span>
              </div>
              <button
                className="p-1 rounded-full hover:bg-surface-container/50 cursor-pointer"
                type="button"
                aria-label="Dismiss"
                onClick={() => setSaved(false)}
              >
                <span className="material-symbols-outlined text-[18px]">close</span>
              </button>
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg" key={formKey}>
            {/* Left Column: Profile & Pipeline Rules */}
            <div className="lg:col-span-7 flex flex-col gap-space-lg">
              <article className="bg-surface-container-low rounded-2xl p-space-lg shadow-xs flex flex-col gap-space-md">
                <div className="flex items-center justify-between pb-space-xs">
                  <div className="flex items-center gap-space-sm">
                    <div className="w-10 h-10 rounded-xl bg-primary-fixed flex items-center justify-center text-on-primary-fixed">
                      <span className="material-symbols-outlined text-[22px]">badge</span>
                    </div>
                    <div>
                      <h2 className="font-title-lg text-title-lg text-on-surface font-medium">
                        {"User Profile & Creator Identity"}
                      </h2>{" "}
                      <p className="font-body-sm text-body-sm text-on-surface-variant">
                        Configure export branding, account details, and credential token.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="flex flex-col sm:flex-row items-center sm:items-center gap-space-md p-space-md rounded-xl bg-surface-container">
                  <div className="relative shrink-0">
                    <img
                      alt={user?.display_name || user?.username || "Creator Profile"}
                      className="w-20 h-20 rounded-2xl object-cover shadow-xs"
                      src={user?.avatar_url || PROFILE_URL}
                    />
                    <span
                      className="absolute -bottom-1 -right-1 w-6 h-6 rounded-full bg-primary flex items-center justify-center text-on-primary shadow-xs"
                      title="Pro Verified"
                    >
                      <span className="material-symbols-outlined text-[14px]">star</span>
                    </span>
                  </div>
                  <div className="flex flex-col sm:flex-1 gap-1 text-center sm:text-left">
                    <div className="flex items-center justify-center sm:justify-start gap-2">
                      <span className="font-title-md text-title-md text-on-surface font-medium">
                        {displayNameInput || "Creator"}
                      </span>
                      <span className="font-label-sm text-label-sm px-2 py-0.5 rounded-full bg-surface-container-highest text-on-surface-variant font-mono">
                        @{user?.username || "handle"}
                      </span>
                    </div>
                    <p className="font-body-sm text-body-sm text-on-surface-variant">
                      {user?.email || "JPG, PNG or WebP up to 5MB."}
                    </p>
                    <div className="flex items-center justify-center sm:justify-start gap-space-xs pt-1">
                      <button
                        className="px-space-sm py-1.5 rounded-full bg-primary-fixed hover:bg-primary-fixed-dim text-on-primary-fixed font-label-md text-label-md transition-colors flex items-center gap-1.5 cursor-pointer"
                        type="button"
                        onClick={() => avatarInput.current?.click()}
                      >
                        <span className="material-symbols-outlined text-[16px]">photo_camera</span>{" "}
                        Change Avatar{" "}
                      </button>
                      <input
                        ref={avatarInput}
                        type="file"
                        accept="image/png,image/jpeg,image/webp"
                        className="sr-only"
                        onChange={handleAvatarChange}
                      />
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-space-md pt-space-xs">
                  <div className="flex flex-col gap-1.5">
                    <label className="font-label-md text-label-md text-on-surface-variant font-medium">
                      Display Name
                    </label>
                    <div className="relative flex items-center rounded-lg bg-surface-container px-space-sm py-2.5 transition-colors focus-within:ring-2 focus-within:ring-primary">
                      <span className="material-symbols-outlined text-outline text-[20px] mr-2">
                        person
                      </span>
                      <input
                        className="bg-transparent w-full text-on-surface font-body-md text-body-md outline-hidden focus:outline-hidden"
                        value={displayNameInput}
                        onChange={(e) => setDisplayNameInput(e.target.value)}
                        placeholder="Alex Vance"
                      />
                    </div>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <label className="font-label-md text-label-md text-on-surface-variant font-medium">
                      Email Address
                    </label>
                    <div className="relative flex items-center rounded-lg bg-surface-container px-space-sm py-2.5 opacity-80">
                      <span className="material-symbols-outlined text-outline text-[20px] mr-2">
                        mail
                      </span>
                      <input
                        className="bg-transparent w-full text-on-surface font-body-md text-body-md outline-hidden cursor-not-allowed"
                        readOnly
                        value={user?.email || "alex@creativestudio.ai"}
                      />
                    </div>
                  </div>
                </div>

                <div className="flex flex-col sm:flex-row items-center justify-between gap-space-sm pt-space-xs border-t border-outline-variant/30">
                  <div className="flex flex-col">
                    <span className="font-label-md text-label-md text-on-surface font-medium">
                      Security &amp; Password
                    </span>
                    <span className="font-body-sm text-body-sm text-on-surface-variant">
                      Update your account login password anytime.
                    </span>
                  </div>
                  <button
                    className="px-4 py-2 rounded-full bg-surface-container hover:bg-surface-container-high text-on-surface font-label-md text-label-md transition-colors cursor-pointer"
                    type="button"
                    onClick={() => setPasswordOpen(true)}
                  >
                    Change Password
                  </button>
                </div>

                {user?.credential_token && (
                  <div className="flex flex-col gap-1.5 pt-space-xs border-t border-outline-variant/30">
                    <div className="flex items-center justify-between">
                      <label className="font-label-md text-label-md text-on-surface font-medium">
                        Account Credential Token
                      </label>
                      <button
                        type="button"
                        onClick={handleRegenerateToken}
                        className="text-xs text-primary font-medium hover:underline cursor-pointer"
                      >
                        Regenerate Token
                      </button>
                    </div>
                    <div className="relative flex items-center rounded-lg bg-surface-container px-space-sm py-2">
                      <span className="material-symbols-outlined text-outline text-[18px] mr-2">
                        vpn_key
                      </span>
                      <span className="font-mono text-xs text-on-surface-variant truncate flex-1">
                        {user.credential_token.slice(0, 12)}••••••••••••••••••••
                      </span>
                    </div>
                  </div>
                )}
              </article>

              {/* Pipeline Engine Configuration */}
              <article className="bg-surface-container-low rounded-2xl p-space-lg shadow-xs flex flex-col gap-space-md">
                <div className="flex items-center gap-space-sm pb-space-xs">
                  <div className="w-10 h-10 rounded-xl bg-secondary-container flex items-center justify-center text-on-secondary-container">
                    <span className="material-symbols-outlined text-[22px]">tune</span>
                  </div>
                  <div>
                    <h2 className="font-title-lg text-title-lg text-on-surface font-medium">
                      {"Default Pipeline Preferences"}
                    </h2>
                    <p className="font-body-sm text-body-sm text-on-surface-variant">
                      Global defaults applied automatically when new video sources are ingested.
                    </p>
                  </div>
                </div>

                <div className="flex flex-col gap-space-sm">
                  <RuleCard
                    icon="hd"
                    title="Default Resolution & Export Quality"
                    description="Standard canvas dimension for vertical & square exports."
                  >
                    <div className="grid grid-cols-3 gap-2">
                      {RES_OPTIONS.map((r) => (
                        <button
                          key={r.id}
                          type="button"
                          onClick={() => setResolution(r.id)}
                          className={`p-2.5 rounded-xl flex flex-col items-center gap-1 cursor-pointer transition-colors ${
                            resolution === r.id
                              ? "bg-primary-fixed text-on-primary-fixed font-bold shadow-xs"
                              : "bg-surface-container-highest hover:bg-surface-container text-on-surface font-medium"
                          }`}
                        >
                          <span className="material-symbols-outlined text-[20px]">{r.icon}</span>
                          <span className="text-xs">{r.label}</span>
                        </button>
                      ))}
                    </div>
                  </RuleCard>

                  <RuleCard
                    icon="mic"
                    title="Whisper Speech-to-Text Model"
                    description="Engine model tier utilized for audio transcription and karaoke subtitles."
                  >
                    <div className="grid grid-cols-3 gap-2">
                      {WHISPER_MODELS.map((m) => (
                        <button
                          key={m}
                          type="button"
                          onClick={() => setWhisper(m)}
                          className={`p-2 rounded-xl text-center text-xs capitalize cursor-pointer transition-colors ${
                            whisper === m
                              ? "bg-primary text-on-primary font-bold shadow-xs"
                              : "bg-surface-container-highest hover:bg-surface-container text-on-surface font-medium"
                          }`}
                        >
                          {m}
                        </button>
                      ))}
                    </div>
                  </RuleCard>

                  <RuleCard
                    icon="subtitles"
                    title="Automatic Subtitle Burning"
                    description="Burn synchronized animated subtitles directly onto exported video renders."
                    action={
                      <SettingSwitch
                        checked={captions}
                        onChange={setCaptions}
                        label="Automatic Subtitles"
                      />
                    }
                  >
                    <span className="text-xs text-on-surface-variant">
                      Uses word-level timestamp boundaries derived from Whisper transcripts.
                    </span>
                  </RuleCard>

                  <RuleCard
                    icon="send"
                    title="Auto-Publish via Buffer"
                    description="Automatically queue approved clips to your social channels."
                    action={
                      <SettingSwitch
                        checked={publish}
                        onChange={setPublish}
                        label="Auto-publish via Buffer"
                      />
                    }
                  >
                    <fieldset
                      disabled={!publish}
                      className="grid grid-cols-1 sm:grid-cols-2 gap-space-sm disabled:opacity-50"
                    >
                      <Field label="Buffer Account Name" htmlFor="buffer-account">
                        <TextBox
                          id="buffer-account"
                          icon="account_circle"
                          placeholder="@clippingstudio"
                          value={bufferAccount}
                          onChange={(e) => setBufferAccount(e.target.value)}
                        />
                      </Field>
                      <Field label="Buffer API Key *" htmlFor="buffer-key">
                        <SecretInput
                          id="buffer-key"
                          icon="key"
                          value={apiKeys.buffer}
                          onChange={(v) => {
                            setApiKeys((k) => ({ ...k, buffer: v }));
                            setKeyStatus((s) => ({ ...s, buffer: "idle" }));
                          }}
                          placeholder="1/abc123..."
                          shown={!!shownKeys["buffer-key"]}
                          onToggle={() => toggleKey("buffer-key")}
                        />
                      </Field>
                      <div className="sm:col-span-2 flex justify-end">
                        <TestButton
                          status={keyStatus.buffer}
                          disabled={!apiKeys.buffer && !bufferAccount}
                          onClick={() => runTest("buffer")}
                        />
                      </div>
                    </fieldset>
                  </RuleCard>

                  <RuleCard
                    icon="cloud_sync"
                    title="Cloud Storage"
                    description="Where source masters and rendered clips are kept."
                  >
                    <div
                      className="grid grid-cols-3 p-1 rounded-lg bg-surface-container-lowest gap-1"
                      role="radiogroup"
                      aria-label="Storage provider"
                    >
                      {(Object.keys(STORAGE_PROVIDERS) as StorageProvider[]).map((p) => (
                        <button
                          key={p}
                          type="button"
                          role="radio"
                          aria-checked={storage === p}
                          onClick={() => setStorage(p)}
                          className={`flex items-center justify-center gap-1.5 py-2 px-2 rounded-md font-label-md text-label-md font-medium transition-all cursor-pointer ${
                            storage === p
                              ? "bg-secondary-container text-on-secondary-container shadow-xs font-semibold"
                              : "text-on-surface-variant hover:text-on-surface"
                          }`}
                        >
                          <span className="material-symbols-outlined text-[18px]">
                            {STORAGE_PROVIDERS[p].icon}
                          </span>
                          <span className="truncate">{STORAGE_PROVIDERS[p].label}</span>
                        </button>
                      ))}
                    </div>

                    {canCustomizeRetention(storage) ? (
                      <div className="flex flex-col gap-space-sm" key={storage}>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-space-sm">
                          {STORAGE_PROVIDERS[storage].fields.map((f) => {
                            const fieldKey = `${storage}-${f.id}`;
                            return (
                              <Field
                                key={fieldKey}
                                label={`${f.label}${f.secret ? " *" : ""}`}
                                htmlFor={fieldKey}
                              >
                                {f.secret ? (
                                  <SecretInput
                                    id={fieldKey}
                                    icon="lock"
                                    placeholder={f.placeholder}
                                    value={storageCreds[fieldKey] || ""}
                                    onChange={(val) =>
                                      setStorageCreds((prev) => ({
                                        ...prev,
                                        [fieldKey]: val,
                                      }))
                                    }
                                    shown={!!shownKeys[fieldKey]}
                                    onToggle={() => toggleKey(fieldKey)}
                                  />
                                ) : (
                                  <TextBox
                                    id={fieldKey}
                                    icon="tag"
                                    placeholder={f.placeholder}
                                    value={storageCreds[fieldKey] || ""}
                                    onChange={(e) =>
                                      setStorageCreds((prev) => ({
                                        ...prev,
                                        [fieldKey]: e.target.value,
                                      }))
                                    }
                                  />
                                )}
                              </Field>
                            );
                          })}
                        </div>
                        <Field
                          label="Storage Retention"
                          htmlFor="retention-value"
                          hint={`Files older than this are deleted from your ${STORAGE_PROVIDERS[storage].label} storage.`}
                        >
                          <div className="flex items-center gap-space-xs">
                            <div className="w-28">
                              <TextBox
                                id="retention-value"
                                icon="schedule"
                                type="number"
                                min={1}
                                value={storageRetention}
                                onChange={(e) => setStorageRetention(e.target.value)}
                              />
                            </div>
                            <div className="w-36">
                              <Dropdown
                                id="retention-unit"
                                aria-label="Retention unit"
                                value={retentionUnit}
                                onValueChange={setRetentionUnit}
                                options={RETENTION_UNITS}
                              />
                            </div>
                          </div>
                        </Field>
                      </div>
                    ) : (
                      <div className="flex items-start gap-space-xs text-on-surface-variant p-2.5 rounded-lg bg-surface-container-lowest">
                        <span className="material-symbols-outlined text-[18px] text-primary mt-0.5">
                          info
                        </span>
                        <span className="font-body-sm text-body-sm">
                          Standard storage keeps files on server for {STANDARD_RETENTION_HOURS}{" "}
                          hours, then deletes them. Download your clips before they expire, or
                          connect Cloudinary or Cloudflare R2 to choose your own retention.
                        </span>
                      </div>
                    )}
                  </RuleCard>
                </div>
              </article>
            </div>

            {/* Right Column: AI Model API Keys & BYOK */}
            <div className="lg:col-span-5 flex flex-col gap-space-lg">
              <article className="bg-surface-container-low rounded-2xl p-space-lg shadow-xs flex flex-col gap-space-md">
                <div className="flex items-center justify-between pb-space-xs">
                  <div className="flex items-center gap-space-sm">
                    <div className="w-10 h-10 rounded-xl bg-tertiary-fixed flex items-center justify-center text-on-tertiary-fixed">
                      <span className="material-symbols-outlined text-[22px]">smart_toy</span>
                    </div>
                    <div>
                      <h2 className="font-title-lg text-title-lg text-on-surface font-medium">
                        {"AI Model API Keys"}
                      </h2>
                      <p className="font-body-sm text-body-sm text-on-surface-variant">
                        Bring Your Own Key (BYOK) for LLM reasoning and hook analysis.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="p-space-sm rounded-xl bg-surface-container text-on-surface-variant font-body-sm text-body-sm relative">
                  Connect your own Gemini, OpenAI, or Anthropic API key to unlock custom models with
                  zero data retention.
                </div>

                <div className="flex flex-col gap-space-sm pt-space-xs">
                  <Field label="Preferred Hook Detection Model" htmlFor="hook-provider">
                    <Dropdown
                      id="hook-provider"
                      icon={providerInfo.icon}
                      iconClassName="text-primary text-[20px]"
                      tone="container"
                      size="md"
                      value={provider}
                      onValueChange={changeProvider}
                      options={(Object.keys(HOOK_PROVIDERS) as HookProviderId[]).map((id) => ({
                        value: id,
                        label: HOOK_PROVIDERS[id].label,
                        icon: HOOK_PROVIDERS[id].icon,
                        description: HOOK_PROVIDERS[id].keyProvider
                          ? "Uses your own API key"
                          : "Runs on Clipping Studio GPUs",
                      }))}
                    />
                  </Field>

                  <Field label="Version" htmlFor="hook-version">
                    <div className="flex items-center gap-space-xs">
                      <div className="flex-1 min-w-0">
                        <Dropdown
                          key={provider}
                          id="hook-version"
                          icon="neurology"
                          iconClassName="text-primary text-[20px]"
                          tone="container"
                          size="md"
                          value={versionInfo.id}
                          onValueChange={setVersion}
                          options={versions.map((v) => ({
                            value: v.id,
                            label: v.label,
                            description: v.hint,
                          }))}
                        />
                      </div>
                      <button
                        type="button"
                        onClick={refreshVersions}
                        disabled={refreshing}
                        aria-label="Check available versions"
                        className="shrink-0 h-11 w-11 rounded-lg bg-secondary-container text-on-secondary-container flex items-center justify-center transition-colors hover:bg-secondary-fixed cursor-pointer disabled:opacity-50"
                      >
                        <span
                          className={`material-symbols-outlined text-[20px] ${refreshing ? "animate-spin" : ""}`}
                        >
                          {refreshing ? "progress_activity" : "refresh"}
                        </span>
                      </button>
                    </div>
                  </Field>

                  <div className="flex items-start justify-between gap-space-sm font-label-sm text-label-sm text-on-surface-variant">
                    <span>{versionInfo.hint}</span>
                  </div>
                </div>

                {keyProvider && (
                  <div className="flex flex-col gap-1.5 pt-space-xs" key={keyProvider}>
                    <div className="flex items-center justify-between">
                      <label
                        className="font-label-md text-label-md text-on-surface-variant font-medium"
                        htmlFor={`key-${keyProvider}`}
                      >
                        {PROVIDER_KEYS[keyProvider].label}
                      </label>
                      {keyStatus[keyProvider] === "ok" ? (
                        <span className="inline-flex items-center gap-1 font-label-sm text-label-sm text-primary font-medium">
                          <span className="w-1.5 h-1.5 rounded-full bg-primary"></span> Connected
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 font-label-sm text-label-sm text-outline font-medium">
                          <span className="w-1.5 h-1.5 rounded-full bg-outline"></span> Unchecked
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-space-xs">
                      <div
                        className={`${boxClass("container")} flex-1 min-w-0`}
                        id={`key-${keyProvider}`}
                      >
                        <span className="material-symbols-outlined text-outline text-[18px] mr-2">
                          key
                        </span>
                        <span
                          className={`truncate font-body-sm text-body-sm ${providerKey ? "text-on-surface tracking-wider" : "text-outline"}`}
                        >
                          {providerKey ? maskApiKey(providerKey) : "No key set"}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={() => setKeyDialogOpen(true)}
                        className="shrink-0 h-10 px-space-sm rounded-lg bg-primary-container text-on-primary font-label-lg text-label-lg flex items-center gap-1.5 transition-colors hover:bg-primary cursor-pointer"
                      >
                        <span className="material-symbols-outlined text-[18px]">
                          {providerKey ? "edit" : "add"}
                        </span>
                        {providerKey ? "Change Key" : "Set API Key"}
                      </button>
                    </div>
                    <div className="flex items-center justify-between text-on-surface-variant font-label-sm text-label-sm">
                      <span>Required for {versionInfo.label}</span>
                      <TestButton
                        status={keyStatus[keyProvider]}
                        disabled={!providerKey}
                        onClick={() => runTest(keyProvider)}
                      />
                    </div>
                  </div>
                )}

                <div className="mt-space-xs p-space-md rounded-xl bg-surface-container flex items-start gap-space-sm">
                  <span className="material-symbols-outlined text-primary text-[22px] mt-0.5">
                    lock_clock
                  </span>
                  <div className="flex flex-col gap-1">
                    <span className="font-title-sm text-title-sm text-on-surface font-medium">
                      Zero Data Training Guarantee
                    </span>
                    <p className="font-body-sm text-body-sm text-on-surface-variant">
                      When using your own API credentials, all video frames and transcript moments
                      are strictly evaluated with zero retention by AI providers.
                    </p>
                  </div>
                </div>
              </article>
            </div>
          </div>
        </div>
      </div>

      <ChangePasswordDialog open={passwordOpen} onOpenChange={setPasswordOpen} />

      {keyProvider && (
        <ApiKeyDialog
          open={keyDialogOpen}
          onOpenChange={setKeyDialogOpen}
          title={providerKey ? "Change API Key" : "Set API Key"}
          providerLabel={providerInfo.label}
          placeholder={PROVIDER_KEYS[keyProvider].placeholder}
          hasKey={!!providerKey}
          onSave={async (key) => {
            try {
              await apiConfig.saveAiCredentials({
                provider: keyProvider,
                key,
                model: version,
              });
              setApiKeys((k) => ({ ...k, [keyProvider]: key }));
              setKeyStatus((st) => ({ ...st, [keyProvider]: "idle" }));
              toast.success(`${providerInfo.label} API key tersimpan.`);
            } catch (err: unknown) {
              toast.error(err instanceof Error ? err.message : "Gagal menyimpan API key.");
            }
          }}
          onRemove={async () => {
            try {
              await apiConfig.deleteAiCredentials(keyProvider);
              setApiKeys((k) => ({ ...k, [keyProvider]: "" }));
              setKeyStatus((st) => ({ ...st, [keyProvider]: "idle" }));
              toast.info(`${providerInfo.label} API key dihapus.`);
            } catch (err: unknown) {
              toast.error(err instanceof Error ? err.message : "Gagal menghapus API key.");
            }
          }}
        />
      )}
    </>
  );
}
