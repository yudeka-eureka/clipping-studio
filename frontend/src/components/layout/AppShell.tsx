import { Link, useNavigate } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/lib/auth-context";
import { useJobs } from "@/lib/jobs-context";
import { useI18n } from "@/lib/i18n";

const LOGO_URL =
  "https://lh3.googleusercontent.com/aida-public/AB6AXuB_4ixaIKCMdQQcA2JHfhW95G58sBrYen__FvQrmBWsrb3DXEHGqUaSkn-KiqEATpNdil_gIGY8PNtPNV6ifKesRUWDHagysr3e7jJxymcugqP8jbEGH4XiWgHoRjJ2NXo7zOsCUxH8rkj_QT5am9TNX3lJDITMqwnmL7XcmVwB-p_nbLPSeQjilw09upVkMZdVSQrxWN3TuzHx0jNTABeVByj6SM3vBs1FyUFN6OsJ";
export const PROFILE_URL =
  "https://lh3.googleusercontent.com/aida-public/AB6AXuDbF9oYmtvNImP3MhYMJS1zUvoiGJGUh6kzqHC0bqyafAkh3aKb6Gq9GSOP_Av-sZ2EkOVmvdNaM_zHrhAHgPVzFyFUy9RQ-8cw6h_kRTsHObkZQ8P9OpLRhEWvEyhldNxIHxpK0Fv0aWQyemvph8nUyjuwEStD9K3O1zNT0pQ5uK9a6DlAiNwwTyk9RZ8EWRYpEn38adCHB40IDUUXxkB3569-WeVMwZit2EqAiD9D";

const navBase =
  "group flex items-center gap-2 w-full px-2 py-2 rounded-full transition-all relative";
const navInactive = "text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface";
const navActive = "bg-primary-fixed text-on-primary-fixed";

function NavItem({
  to,
  icon,
  label,
  dot,
}: {
  to: "/app" | "/app/clips" | "/app/settings";
  icon: string;
  label: string;
  dot?: boolean;
}) {
  return (
    <Link
      to={to}
      activeOptions={{ exact: to === "/app" }}
      className={navBase}
      activeProps={{ className: navActive, "aria-current": "page" }}
      inactiveProps={{ className: navInactive }}
    >
      <div className="relative flex items-center justify-center w-8 h-8 shrink-0 rounded-full transition-colors">
        <span className="material-symbols-outlined text-[24px]">{icon}</span>
        {dot && (
          <span className="absolute top-1 right-2 w-2 h-2 rounded-full bg-primary ring-2 ring-surface-container-low"></span>
        )}
      </div>
      <span className="font-label-sm text-label-sm text-left font-medium leading-none">
        {label}
      </span>
    </Link>
  );
}

function Sidebar() {
  const { user, logout, openAuthModal } = useAuth();
  const { jobs, setActiveJobId } = useJobs();
  const { t, locale } = useI18n();
  const navigate = useNavigate();

  const displayName = user?.display_name || user?.username || "Guest User";
  const userAvatar = user?.avatar_url || PROFILE_URL;
  const recentJobs = jobs.slice(0, 6);

  const handleLogout = async () => {
    await logout();
    navigate({ to: "/" });
  };

  return (
    <aside
      aria-label="Studio sidebar"
      className="fixed left-0 top-0 h-dvh w-(--studio-sidebar-width) bg-surface-container-low border-r border-outline-variant/40 z-50 flex flex-col px-3 py-space-md"
    >
      <Link to="/app" className="flex items-center gap-2 px-2 pb-space-lg shrink-0">
        <img alt="Clipping Studio Logo" className="h-8 w-8 object-contain" src={LOGO_URL} />
        <span className="text-title-sm font-semibold text-primary">
          Clipping <span className="hidden sm:inline">Studio</span>
        </span>
      </Link>
      <nav aria-label="Studio navigation" className="flex flex-col gap-2 shrink-0">
        <NavItem to="/app" icon="movie_creation" label={t.sidebar.studio} />
        <NavItem
          to="/app/clips"
          icon="video_library"
          label={t.sidebar.clips}
          dot={jobs.some((j) => j.status === "rendering" || j.status === "queued")}
        />
      </nav>
      <section
        aria-label="Projects by video source"
        className="flex-1 min-h-0 overflow-y-auto mt-space-lg"
      >
        <div className="flex items-center justify-between px-2 mb-3 text-on-surface-variant">
          <span className="text-label-sm font-medium">{t.sidebar.recents}&nbsp;</span>
          <span className="text-label-sm">{jobs.length}</span>
        </div>
        <div className="space-y-3">
          {recentJobs.length === 0 ? (
            <div className="px-2 py-4 text-center">
              <span className="material-symbols-outlined text-outline text-[24px]">video_file</span>
              <p className="text-label-sm text-outline mt-1">{t.sidebar.noProjects}</p>
              <p className="text-[11px] text-outline">{t.sidebar.uploadToStart}</p>
            </div>
          ) : (
            recentJobs.map((job) => {
              const clipCount = job.clips ? job.clips.length : 0;
              const subtitle =
                job.status === "done"
                  ? locale === "id"
                    ? `${clipCount} klip siap`
                    : `${clipCount} ${clipCount === 1 ? "clip" : "clips"} ready`
                  : job.status === "error"
                    ? locale === "id"
                      ? "Gagal diproses"
                      : "Processing failed"
                    : job.stage ||
                      (job.status === "queued"
                        ? locale === "id"
                          ? "Antrean..."
                          : "Queued..."
                        : t.common.processing);

              return (
                <Button
                  key={job.id}
                  asChild
                  variant="ghost"
                  className="w-full h-auto justify-start gap-2 px-2 py-2 whitespace-normal text-left hover:bg-surface-container-high hover:text-on-surface"
                  onClick={() => setActiveJobId(job.id)}
                >
                  <Link to="/app/clips">
                    <span className="hidden sm:block material-symbols-outlined text-primary text-[20px] shrink-0">
                      smart_display
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-label-md font-medium break-words truncate">
                        {job.name || "Untitled Video"}
                      </span>
                      <span className="block text-label-sm text-outline mt-1 truncate">
                        {subtitle}
                      </span>
                    </span>
                    <span className="hidden sm:block material-symbols-outlined text-[16px] shrink-0 text-on-surface-variant">
                      chevron_right
                    </span>
                  </Link>
                </Button>
              );
            })
          )}
        </div>
      </section>
      <div className="shrink-0 pt-space-md border-t border-outline-variant/40">
        <div className="flex items-center justify-between gap-1 px-2 py-2 mb-3 rounded-md bg-secondary-container text-on-secondary-container">
          <span className="text-label-md font-semibold">
            {user ? `@${user.username}` : "Clipping"}
          </span>
          <span className="text-label-sm">{user ? t.common.active : t.common.guest}</span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                aria-label="Open account menu"
                className="h-11 flex-1 min-w-0 justify-start px-1 gap-2 hover:bg-surface-container-high hover:text-on-surface"
              >
                <img
                  alt={displayName}
                  className="w-8 h-8 shrink-0 rounded-full object-cover"
                  src={userAvatar}
                />
                <span className="hidden sm:block truncate text-label-md">{displayName}</span>
                <span className="material-symbols-outlined text-[16px]">expand_less</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent side="top" align="start" sideOffset={8} className="w-52 z-[60]">
              <DropdownMenuLabel>
                <div className="font-semibold text-sm">{displayName}</div>
                {user?.email && (
                  <div className="text-xs text-on-surface-variant font-normal truncate">
                    {user.email}
                  </div>
                )}
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              {user ? (
                <>
                  <DropdownMenuItem asChild>
                    <Link to="/app/settings">
                      <span className="material-symbols-outlined text-[18px]">settings</span>
                      {t.sidebar.settings}
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={handleLogout} className="text-red-500 cursor-pointer">
                    <span className="material-symbols-outlined text-[18px]">logout</span>
                    {t.sidebar.signOut}
                  </DropdownMenuItem>
                </>
              ) : (
                <DropdownMenuItem
                  onClick={() => openAuthModal("signin")}
                  className="cursor-pointer"
                >
                  <span className="material-symbols-outlined text-[18px]">login</span>
                  {t.sidebar.signIn}
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
          <Button
            asChild
            variant="ghost"
            size="icon"
            className="shrink-0 text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface"
          >
            <Link to="/app/settings" aria-label={t.sidebar.settings} title={t.sidebar.settings}>
              <span className="material-symbols-outlined text-[22px]">settings</span>
            </Link>
          </Button>
        </div>
      </div>
    </aside>
  );
}

function Header() {
  const { t, locale, toggleLocale } = useI18n();

  return (
    <header className="fixed top-0 left-(--studio-sidebar-width) right-0 h-16 bg-surface/85 backdrop-blur-xl z-40 shadow-[0_1px_8px_rgba(0,0,0,0.04)]">
      <div className="w-full h-full px-space-md flex items-center justify-between gap-2">
        <div className="flex items-center gap-space-xs">
          <span className="material-symbols-outlined text-outline text-[20px]">auto_awesome</span>
          <span className="font-title-sm text-title-sm text-on-surface font-medium">
            {t.header.studio}
          </span>
          <span className="text-outline text-body-sm font-body-sm">/</span>
          <span className="hidden xl:inline font-body-sm text-body-sm text-on-surface-variant font-normal">
            {t.header.pipelineSubtitle}
          </span>
        </div>
        <div className="flex items-center gap-space-sm">
          <Link
            to="/app/settings"
            className="hidden md:flex items-center gap-space-xs px-space-sm py-1.5 rounded-full bg-surface-container hover:bg-surface-container-high text-on-surface text-label-md font-label-md transition-colors"
          >
            <span className="material-symbols-outlined text-[18px] text-primary">tune</span>
            <span>{t.header.exportPresets}</span>
          </Link>
          <button
            type="button"
            className="hidden lg:flex items-center gap-1.5 px-space-sm py-1.5 rounded-full bg-surface-container-low hover:bg-surface-container text-on-surface font-label-md text-label-md transition-colors"
          >
            <span className="font-medium">{t.header.personalWorkspace}</span>
            <span className="material-symbols-outlined text-[16px] text-on-surface-variant">
              arrow_drop_down
            </span>
          </button>

          {/* Language Switcher button - replacing the prototype appearance button */}
          <button
            onClick={toggleLocale}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full border border-outline-variant/60 bg-surface-container-low hover:bg-surface-container text-on-surface transition-all cursor-pointer shadow-2xs group"
            type="button"
            title={t.header.switchLang}
            aria-label={t.header.switchLang}
          >
            <span className="material-symbols-outlined text-[18px] text-primary group-hover:rotate-12 transition-transform">
              translate
            </span>
            <span className="font-label-sm text-[12px] font-bold tracking-wider text-on-surface uppercase">
              {locale.toUpperCase()}
            </span>
          </button>

          <button
            className="w-9 h-9 rounded-full flex items-center justify-center text-on-surface-variant hover:text-on-surface hover:bg-surface-container transition-colors"
            type="button"
            aria-label={t.header.notifications}
            title={t.header.notifications}
          >
            <span className="material-symbols-outlined text-[20px]">notifications</span>
          </button>
        </div>
      </div>
    </header>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="bg-surface font-body-md text-on-surface antialiased min-h-screen">
      <Sidebar />
      <div className="pl-(--studio-sidebar-width) min-h-screen flex flex-col">
        <Header />
        <main className="w-full pt-16 bg-surface flex-1">{children}</main>
      </div>
    </div>
  );
}
