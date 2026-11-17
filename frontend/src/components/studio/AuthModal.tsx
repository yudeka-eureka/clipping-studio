import { useState, useEffect, type FormEvent } from "react";
import { toast } from "sonner";
import { useAuth, type AuthModalMode } from "@/lib/auth-context";

interface AuthModalProps {
  isOpen?: boolean;
  onClose?: () => void;
  onSuccess?: () => void;
  initialMode?: AuthModalMode;
  /**
   * If true, prevents closing the modal without authenticating (e.g. for strictly guarded pages)
   */
  forced?: boolean;
}

const tabActive =
  "flex-1 py-2 text-center rounded-full font-label-lg text-label-lg font-semibold bg-surface-container-lowest text-primary shadow-xs transition-all duration-200 cursor-pointer";
const tabIdle =
  "flex-1 py-2 text-center rounded-full font-label-lg text-label-lg text-on-surface-variant transition-all duration-200 hover:text-on-surface cursor-pointer";

export function AuthModal({
  isOpen,
  onClose,
  onSuccess,
  initialMode,
  forced = false,
}: AuthModalProps) {
  const {
    isAuthModalOpen: contextOpen,
    authModalMode: contextMode,
    closeAuthModal,
    login,
    register,
  } = useAuth();

  const show = isOpen !== undefined ? isOpen : contextOpen;
  const activeMode = initialMode || contextMode;

  const [mode, setMode] = useState<AuthModalMode>(activeMode);
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [agreeTerms, setAgreeTerms] = useState(true);

  useEffect(() => {
    if (activeMode) {
      setMode(activeMode);
    }
  }, [activeMode]);

  useEffect(() => {
    if (show) {
      setErrorMsg(null);
    }
  }, [show]);

  if (!show) return null;

  const isRegister = mode === "register";

  const handleClose = () => {
    if (forced) return;
    if (onClose) {
      onClose();
    } else {
      closeAuthModal();
    }
  };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErrorMsg(null);

    if (isRegister) {
      if (!username.trim()) {
        setErrorMsg("Username wajib diisi.");
        return;
      }
      if (username.trim().length < 3) {
        setErrorMsg("Username minimal 3 karakter.");
        return;
      }
      if (!agreeTerms) {
        setErrorMsg("Anda harus menyetujui Ketentuan Layanan.");
        return;
      }
    }

    if (password.length < 8) {
      setErrorMsg("Kata sandi minimal 8 karakter.");
      return;
    }

    setSubmitting(true);
    try {
      if (isRegister) {
        await register(username.trim(), email.trim(), password);
        toast.success("Akun berhasil dibuat!", {
          description: "Selamat datang di Clipping Studio.",
        });
      } else {
        await login(email.trim(), password);
        toast.success("Berhasil masuk!", {
          description: "Selamat datang kembali ke Clipping Studio.",
        });
      }
      if (onSuccess) {
        onSuccess();
      } else {
        closeAuthModal();
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Terjadi kesalahan saat autentikasi.";
      setErrorMsg(msg);
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      aria-labelledby="modal-title"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 overflow-y-auto animate-in fade-in duration-200"
      role="dialog"
    >
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/65 backdrop-blur-xs transition-opacity"
        onClick={handleClose}
        aria-hidden="true"
      />

      <div className="relative w-full max-w-[480px] my-auto z-10">
        <div className="absolute -top-12 -left-12 w-64 h-64 rounded-full bg-gradient-to-tr from-primary-fixed via-secondary-container to-transparent blur-3xl opacity-50 pointer-events-none" />
        <div className="absolute -bottom-12 -right-12 w-64 h-64 rounded-full bg-gradient-to-bl from-tertiary-fixed via-primary-fixed-dim to-transparent blur-3xl opacity-40 pointer-events-none" />

        <div className="relative bg-surface-container-lowest rounded-[28px] shadow-2xl shadow-on-surface/30 border border-outline-variant/40 px-space-lg py-space-lg sm:p-space-xl transition-all duration-300">
          {!forced && (
            <button
              aria-label="Close modal"
              onClick={handleClose}
              className="absolute top-4 right-4 w-9 h-9 rounded-full bg-surface-container-low hover:bg-surface-container text-on-surface-variant hover:text-on-surface flex items-center justify-center transition-colors focus:outline-hidden focus:ring-2 focus:ring-primary cursor-pointer"
              type="button"
            >
              <span className="material-symbols-outlined text-[20px]">close</span>
            </button>
          )}

          <div className="flex flex-col items-center text-center space-y-space-xs mt-1">
            <div className="relative w-16 h-16 rounded-2xl bg-surface-container flex items-center justify-center p-space-xs shadow-xs">
              <img
                alt="Clipping Studio Logo"
                className="w-12 h-12 object-contain"
                src="https://lh3.googleusercontent.com/aida-public/AB6AXuB_4ixaIKCMdQQcA2JHfhW95G58sBrYen__FvQrmBWsrb3DXEHGqUaSkn-KiqEATpNdil_gIGY8PNtPNV6ifKesRUWDHagysr3e7jJxymcugqP8jbEGH4XiWgHoRjJ2NXo7zOsCUxH8rkj_QT5am9TNX3lJDITMqwnmL7XcmVwB-p_nbLPSeQjilw09upVkMZdVSQrxWN3TuzHx0jNTABeVByj6SM3vBs1FyUFN6OsJ"
              />
              <div className="absolute -bottom-1 -right-1 bg-primary text-on-primary rounded-full p-1 shadow-xs flex items-center justify-center">
                <span
                  className="material-symbols-outlined text-[12px]"
                  style={{ fontVariationSettings: "'FILL' 1" }}
                >
                  auto_videocam
                </span>
              </div>
            </div>
            <div className="pt-space-xs">
              <h1
                className="font-headline-sm text-headline-sm text-on-surface font-semibold tracking-tight"
                id="modal-title"
              >
                {isRegister ? "Welcome to Clipping Studio" : "Welcome back"}
              </h1>
              <p className="font-body-md text-body-md text-on-surface-variant max-w-[340px] mt-1">
                {isRegister
                  ? "Transform long-form videos into viral clips in seconds."
                  : "Sign in to pick up where your clip queue left off."}
              </p>
            </div>
          </div>

          <div className="mt-space-lg">
            <div
              className="bg-surface-container-high p-1 rounded-full flex relative items-center"
              role="tablist"
            >
              <button
                aria-selected={!isRegister}
                className={isRegister ? tabIdle : tabActive}
                onClick={() => {
                  setMode("signin");
                  setErrorMsg(null);
                }}
                id="tab-signin"
                role="tab"
                type="button"
              >
                Sign In
              </button>
              <button
                aria-selected={isRegister}
                className={isRegister ? tabActive : tabIdle}
                onClick={() => {
                  setMode("register");
                  setErrorMsg(null);
                }}
                id="tab-register"
                role="tab"
                type="button"
              >
                Create Account
              </button>
            </div>
          </div>

          {errorMsg && (
            <div className="mt-3 p-3 rounded-xl bg-error-container text-on-error-container text-xs flex items-center gap-2">
              <span className="material-symbols-outlined text-[18px] shrink-0 text-red-500">
                error
              </span>
              <span>{errorMsg}</span>
            </div>
          )}

          <form className="mt-space-lg space-y-space-md" id="auth-form" onSubmit={handleSubmit}>
            {isRegister && (
              <div className="relative group transition-all duration-200" id="username-field-group">
                <div className="relative flex items-center">
                  <input
                    className="peer w-full h-14 bg-surface-container-low text-on-surface font-body-md text-body-md rounded-xl pl-12 pr-4 outline-hidden focus:bg-surface-container-lowest focus:ring-2 focus:ring-primary transition-all duration-150"
                    id="username-input"
                    name="username"
                    placeholder="alex_creator"
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    required
                  />
                  <span className="material-symbols-outlined absolute left-3.5 text-on-surface-variant peer-focus:text-primary transition-colors text-[22px]">
                    person_outline
                  </span>
                </div>
                <div className="flex items-center justify-between px-space-xs pt-1">
                  <span className="font-label-sm text-label-sm text-on-surface-variant">
                    Unique creator handle
                  </span>
                  <span className="font-label-sm text-label-sm text-primary font-medium tracking-wide">
                    @{username || "handle"}
                  </span>
                </div>
              </div>
            )}
            <div className="relative group">
              <div className="relative flex items-center">
                <input
                  className="peer w-full h-14 bg-surface-container-low text-on-surface font-body-md text-body-md rounded-xl pl-12 pr-4 outline-hidden focus:bg-surface-container-lowest focus:ring-2 focus:ring-primary transition-all duration-150"
                  id="email-input"
                  name="email"
                  placeholder={isRegister ? "alex@creativestudio.ai" : "Username or Email"}
                  required
                  type={isRegister ? "email" : "text"}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
                <span className="material-symbols-outlined absolute left-3.5 text-on-surface-variant peer-focus:text-primary transition-colors text-[22px]">
                  mail_outline
                </span>
              </div>
            </div>
            <div className="relative group">
              <div className="relative flex items-center">
                <input
                  className="peer w-full h-14 bg-surface-container-low text-on-surface font-body-md text-body-md rounded-xl pl-12 pr-12 outline-hidden focus:bg-surface-container-lowest focus:ring-2 focus:ring-primary transition-all duration-150"
                  id="password-input"
                  name="password"
                  placeholder="••••••••••••"
                  required
                  minLength={8}
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <span className="material-symbols-outlined absolute left-3.5 text-on-surface-variant peer-focus:text-primary transition-colors text-[22px]">
                  lock_outline
                </span>
                <button
                  aria-label="Toggle password visibility"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-3.5 p-1 text-on-surface-variant hover:text-primary transition-colors rounded-full focus:outline-hidden cursor-pointer"
                  type="button"
                >
                  <span className="material-symbols-outlined text-[20px]" id="password-eye-icon">
                    {showPassword ? "visibility" : "visibility_off"}
                  </span>
                </button>
              </div>
              <p
                className="font-label-sm text-label-sm text-on-surface-variant px-space-xs pt-1"
                id="password-helper-text"
              >
                {isRegister
                  ? "At least 8 characters with numbers & symbols"
                  : "Enter your account password."}
              </p>
            </div>
            {isRegister && (
              <div
                className="flex items-start gap-space-xs pt-space-xs cursor-pointer select-none"
                id="terms-group"
              >
                <label className="relative flex items-center p-0.5 cursor-pointer rounded-xs">
                  <input
                    checked={agreeTerms}
                    onChange={(e) => setAgreeTerms(e.target.checked)}
                    className="peer relative appearance-none w-5 h-5 rounded-md bg-surface-container checked:bg-primary transition-all duration-150 cursor-pointer"
                    id="terms-checkbox"
                    required
                    type="checkbox"
                  />
                  <span
                    className="material-symbols-outlined absolute text-[16px] text-on-primary opacity-0 peer-checked:opacity-100 pointer-events-none left-0.5 top-0.5"
                    style={{ fontVariationSettings: "'FILL' 1" }}
                  >
                    check
                  </span>
                </label>
                <label
                  className="font-body-sm text-body-sm text-on-surface-variant leading-tight cursor-pointer pt-0.5"
                  htmlFor="terms-checkbox"
                >
                  I agree to Clipping Studio{" "}
                  <span className="text-primary hover:underline font-medium">Terms of Service</span>{" "}
                  and{" "}
                  <span className="text-primary hover:underline font-medium">Privacy Policy</span>
                </label>
              </div>
            )}
            <button
              className="w-full h-12 bg-primary hover:bg-primary/95 text-on-primary rounded-full font-label-lg text-label-lg font-semibold flex items-center justify-center gap-space-xs shadow-md shadow-primary/20 hover:shadow-lg hover:shadow-primary/30 active:scale-[0.99] transition-all duration-150 cursor-pointer disabled:opacity-60"
              id="submit-button"
              type="submit"
              disabled={submitting}
            >
              <span id="submit-button-text">
                {submitting ? "Processing..." : isRegister ? "Create Free Account" : "Sign In"}
              </span>
              <span
                className={`material-symbols-outlined text-[18px] ${submitting ? "animate-spin" : ""}`}
              >
                {submitting ? "progress_activity" : "arrow_forward"}
              </span>
            </button>
          </form>

          <div className="mt-space-lg text-center space-y-1">
            <p className="font-body-sm text-body-sm text-on-surface-variant">
              <span id="footer-lead-text">
                {isRegister ? "Already have an account?" : "New to Clipping Studio?"}
              </span>{" "}
              <button
                className="text-primary font-medium hover:underline ml-1 cursor-pointer"
                id="footer-switch-btn"
                type="button"
                onClick={() => {
                  setMode(isRegister ? "signin" : "register");
                  setErrorMsg(null);
                }}
              >
                {isRegister ? "Sign in" : "Create account"}
              </button>
            </p>
          </div>
        </div>

        <div className="mt-space-xs flex items-center justify-center gap-space-xs text-on-surface-variant/70 pt-3">
          <span
            className="material-symbols-outlined text-[16px]"
            style={{ fontVariationSettings: "'FILL' 1" }}
          >
            verified_user
          </span>
          <span className="font-label-sm text-label-sm">
            Enterprise 256-bit encryption • Secure Authentication
          </span>
        </div>
      </div>
    </div>
  );
}
