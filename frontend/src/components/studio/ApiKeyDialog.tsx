import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useState } from "react";

/** Pop-up for setting or replacing a provider API key. The key is never prefilled. */
export function ApiKeyDialog({
  open,
  onOpenChange,
  title,
  providerLabel,
  placeholder,
  hasKey,
  onSave,
  onRemove,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  providerLabel: string;
  placeholder: string;
  hasKey: boolean;
  onSave: (key: string) => void;
  onRemove?: () => void;
}) {
  const [value, setValue] = useState("");
  const [shown, setShown] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const reset = () => {
    setValue("");
    setShown(false);
    setError(null);
    setSaving(false);
  };

  const close = (o: boolean) => {
    onOpenChange(o);
    if (!o) reset();
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!value.trim()) {
      setError(`Paste your ${providerLabel} API key.`);
      return;
    }
    setSaving(true);
    setTimeout(() => {
      onSave(value.trim());
      close(false);
    }, 500);
  };

  return (
    <DialogPrimitive.Root open={open} onOpenChange={close}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-on-surface/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <DialogPrimitive.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-3xl bg-surface-container-low p-space-lg shadow-xl outline-hidden data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
          <div className="flex items-start justify-between gap-space-md pb-space-md">
            <div className="flex items-center gap-space-sm">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary-fixed text-on-primary-fixed">
                <span className="material-symbols-outlined text-[22px]">key</span>
              </div>
              <div>
                <DialogPrimitive.Title className="font-title-lg text-title-lg font-medium text-on-surface">
                  {title}
                </DialogPrimitive.Title>
                <DialogPrimitive.Description className="font-body-sm text-body-sm text-on-surface-variant">
                  {hasKey
                    ? `The new key replaces your saved ${providerLabel} key.`
                    : `Used for hook detection with ${providerLabel}.`}
                </DialogPrimitive.Description>
              </div>
            </div>
            <DialogPrimitive.Close
              className="rounded-full p-1.5 text-outline transition-colors hover:bg-surface-container-high hover:text-on-surface"
              aria-label="Close"
            >
              <span className="material-symbols-outlined text-[20px]">close</span>
            </DialogPrimitive.Close>
          </div>
          <form className="flex flex-col gap-space-md" onSubmit={submit} noValidate>
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="api-key-input"
                className="font-label-md text-label-md font-medium text-on-surface-variant"
              >
                {providerLabel} API Key
              </label>
              <div
                className={`flex h-11 items-center rounded-lg bg-surface-container-lowest px-space-sm focus-within:ring-2 ${error ? "ring-2 ring-error focus-within:ring-error" : "focus-within:ring-primary"}`}
              >
                <span className="material-symbols-outlined mr-2 text-[18px] text-outline">key</span>
                <input
                  id="api-key-input"
                  type={shown ? "text" : "password"}
                  autoComplete="off"
                  autoFocus
                  placeholder={placeholder}
                  value={value}
                  aria-invalid={!!error}
                  aria-describedby={error ? "api-key-err" : undefined}
                  onChange={(e) => {
                    setValue(e.target.value);
                    if (error) setError(null);
                  }}
                  className="w-full min-w-0 bg-transparent font-body-md text-body-md text-on-surface placeholder:text-outline outline-hidden"
                />
                <button
                  type="button"
                  className="rounded-full p-1 text-outline hover:text-on-surface"
                  aria-label={shown ? "Hide key" : "Show key"}
                  onClick={() => setShown((s) => !s)}
                >
                  <span className="material-symbols-outlined text-[18px]">
                    {shown ? "visibility_off" : "visibility"}
                  </span>
                </button>
              </div>
              {error ? (
                <span
                  id="api-key-err"
                  className="flex items-center gap-1 font-label-sm text-label-sm text-error"
                >
                  <span className="material-symbols-outlined text-[14px]">error</span>
                  {error}
                </span>
              ) : (
                <span className="font-label-sm text-label-sm text-on-surface-variant">
                  Stored encrypted. Only the last 4 characters are shown after saving.
                </span>
              )}
            </div>
            <div className="flex items-center justify-between gap-space-sm pt-space-xs">
              {hasKey && onRemove ? (
                <button
                  type="button"
                  className="rounded-full px-space-sm py-2.5 font-label-lg text-label-lg text-error transition-colors hover:bg-error-container/40"
                  onClick={() => {
                    onRemove();
                    close(false);
                  }}
                >
                  Remove key
                </button>
              ) : (
                <span />
              )}
              <div className="flex items-center gap-space-sm">
                <DialogPrimitive.Close
                  type="button"
                  className="rounded-full px-space-md py-2.5 font-label-lg text-label-lg text-primary transition-colors hover:bg-primary-fixed/30"
                >
                  Cancel
                </DialogPrimitive.Close>
                <button
                  type="submit"
                  disabled={saving}
                  className="flex items-center gap-2 rounded-full bg-primary-container px-space-lg py-2.5 font-label-lg text-label-lg text-on-primary shadow-xs transition-all hover:bg-primary hover:shadow-md disabled:opacity-70"
                >
                  <span
                    className={`material-symbols-outlined text-[18px] ${saving ? "animate-spin" : ""}`}
                  >
                    {saving ? "progress_activity" : "check"}
                  </span>
                  {saving ? "Saving..." : "Save Key"}
                </button>
              </div>
            </div>
          </form>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
