import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useState } from "react";
import { toast } from "sonner";

import {
  PASSWORD_MIN_LENGTH,
  validatePasswordChange,
  type PasswordChange,
  type PasswordErrors,
} from "@/lib/settings";
import { useAuth } from "@/lib/auth-context";

const FIELDS: { key: keyof PasswordChange; label: string; icon: string; autoComplete: string }[] = [
  { key: "current", label: "Old Password", icon: "lock", autoComplete: "current-password" },
  { key: "next", label: "New Password", icon: "lock_reset", autoComplete: "new-password" },
  {
    key: "confirm",
    label: "Confirm New Password",
    icon: "verified_user",
    autoComplete: "new-password",
  },
];

const EMPTY: PasswordChange = { current: "", next: "", confirm: "" };

export function ChangePasswordDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { updatePassword } = useAuth();
  const [values, setValues] = useState<PasswordChange>(EMPTY);
  const [shown, setShown] = useState<Partial<Record<keyof PasswordChange, boolean>>>({});
  const [errors, setErrors] = useState<PasswordErrors>({});
  const [saving, setSaving] = useState(false);

  const reset = () => {
    setValues(EMPTY);
    setShown({});
    setErrors({});
    setSaving(false);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const found = validatePasswordChange(values);
    setErrors(found);
    if (Object.keys(found).length) return;

    setSaving(true);
    try {
      await updatePassword(values.current, values.next);
      toast.success("Kata sandi berhasil diperbarui", {
        description: "Gunakan kata sandi baru Anda saat masuk berikutnya.",
      });
      onOpenChange(false);
      reset();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Gagal memperbarui kata sandi.";
      setErrors({ current: msg });
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <DialogPrimitive.Root
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (!o) reset();
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-on-surface/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <DialogPrimitive.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-3xl bg-surface-container-low p-space-lg shadow-xl outline-hidden data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
          <div className="flex items-start justify-between gap-space-md pb-space-md">
            <div className="flex items-center gap-space-sm">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary-fixed text-on-primary-fixed">
                <span className="material-symbols-outlined text-[22px]">password</span>
              </div>
              <div>
                <DialogPrimitive.Title className="font-title-lg text-title-lg font-medium text-on-surface">
                  Change Password
                </DialogPrimitive.Title>
                <DialogPrimitive.Description className="font-body-sm text-body-sm text-on-surface-variant">
                  At least {PASSWORD_MIN_LENGTH} characters with numbers &amp; symbols.
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
            {FIELDS.map((f) => {
              const id = `pw-${f.key}`;
              const err = errors[f.key];
              return (
                <div key={f.key} className="flex flex-col gap-1.5">
                  <label
                    htmlFor={id}
                    className="font-label-md text-label-md font-medium text-on-surface-variant"
                  >
                    {f.label}
                  </label>
                  <div
                    className={`flex h-11 items-center rounded-lg bg-surface-container-lowest px-space-sm focus-within:ring-2 ${err ? "ring-2 ring-error focus-within:ring-error" : "focus-within:ring-primary"}`}
                  >
                    <span className="material-symbols-outlined mr-2 text-[18px] text-outline">
                      {f.icon}
                    </span>
                    <input
                      id={id}
                      type={shown[f.key] ? "text" : "password"}
                      autoComplete={f.autoComplete}
                      value={values[f.key]}
                      aria-invalid={!!err}
                      aria-describedby={err ? `${id}-err` : undefined}
                      onChange={(e) => {
                        setValues((v) => ({ ...v, [f.key]: e.target.value }));
                        if (err) setErrors((x) => ({ ...x, [f.key]: undefined }));
                      }}
                      className="w-full min-w-0 bg-transparent font-body-md text-body-md text-on-surface outline-hidden"
                    />
                    <button
                      type="button"
                      className="rounded-full p-1 text-outline hover:text-on-surface cursor-pointer"
                      aria-label={shown[f.key] ? `Hide ${f.label}` : `Show ${f.label}`}
                      onClick={() => setShown((s) => ({ ...s, [f.key]: !s[f.key] }))}
                    >
                      <span className="material-symbols-outlined text-[18px]">
                        {shown[f.key] ? "visibility_off" : "visibility"}
                      </span>
                    </button>
                  </div>
                  {err && (
                    <span
                      id={`${id}-err`}
                      className="flex items-center gap-1 font-label-sm text-label-sm text-error"
                    >
                      <span className="material-symbols-outlined text-[14px]">error</span>
                      {err}
                    </span>
                  )}
                </div>
              );
            })}
            <div className="flex items-center justify-end gap-space-sm pt-space-xs">
              <DialogPrimitive.Close
                type="button"
                className="rounded-full px-space-md py-2.5 font-label-lg text-label-lg text-primary transition-colors hover:bg-primary-fixed/30 cursor-pointer"
              >
                Cancel
              </DialogPrimitive.Close>
              <button
                type="submit"
                disabled={saving}
                className="flex items-center gap-2 rounded-full bg-primary px-space-lg py-2.5 font-label-lg text-label-lg text-on-primary shadow-xs transition-all hover:bg-primary/90 hover:shadow-md disabled:opacity-70 cursor-pointer"
              >
                <span
                  className={`material-symbols-outlined text-[18px] ${saving ? "animate-spin" : ""}`}
                >
                  {saving ? "progress_activity" : "check"}
                </span>
                {saving ? "Updating..." : "Update Password"}
              </button>
            </div>
          </form>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
