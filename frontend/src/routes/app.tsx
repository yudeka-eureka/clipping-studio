import { createFileRoute, Outlet, useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { useAuth } from "@/lib/auth-context";
import { AuthModal } from "@/components/studio/AuthModal";

export const Route = createFileRoute("/app")({
  component: AppLayout,
});

function AppLayout() {
  const { user, loading, openAuthModal, isAuthModalOpen } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!loading && !user && !isAuthModalOpen) {
      openAuthModal("signin");
    }
  }, [loading, user, isAuthModalOpen, openAuthModal]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
          <p className="text-sm text-on-surface-variant font-medium">Memuat workspace...</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen bg-surface flex flex-col items-center justify-center relative px-4">
        <div className="text-center max-w-md">
          <div className="w-14 h-14 rounded-2xl bg-surface-container flex items-center justify-center text-primary shadow-xs mx-auto mb-4">
            <span className="material-symbols-outlined text-[32px]">lock</span>
          </div>
          <h2 className="text-xl font-bold text-on-surface">Autentikasi Diperlukan</h2>
          <p className="text-sm text-on-surface-variant mt-2">
            Silakan masuk atau buat akun untuk mengakses Clipping Studio workspace.
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-3">
            <button
              onClick={() => openAuthModal("signin")}
              className="inline-flex items-center justify-center rounded-full bg-primary px-6 py-2.5 text-sm font-semibold text-on-primary shadow-xs hover:bg-primary/90 transition-colors cursor-pointer"
            >
              Masuk ke Akun
            </button>
            <button
              onClick={() => navigate({ to: "/" })}
              className="inline-flex items-center justify-center rounded-full border border-outline-variant bg-surface-container-low px-6 py-2.5 text-sm font-semibold text-on-surface hover:bg-surface-container transition-colors cursor-pointer"
            >
              Kembali ke Beranda
            </button>
          </div>
        </div>
        <AuthModal isOpen={true} onClose={() => navigate({ to: "/" })} onSuccess={() => {}} />
      </div>
    );
  }

  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}
