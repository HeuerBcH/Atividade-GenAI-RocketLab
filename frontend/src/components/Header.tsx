import type { Health } from "../types";
import { MenuIcon, MoonIcon, PlusIcon, SunIcon } from "./icons";

interface Props {
  title: string;
  health: Health | null | undefined;
  theme: "light" | "dark";
  onToggleTheme: () => void;
  onOpenMenu: () => void;
  onNewConversation: () => void;
}

const iconButton =
  "grid h-9 w-9 place-items-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-brand-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-brand-200";

function Status({ health }: { health: Health | null | undefined }) {
  const state = health === undefined ? "connecting" : health ? "online" : "offline";
  const label = { connecting: "Conectando...", online: health?.models[0], offline: "API offline" }[state];
  const dot = { connecting: "bg-amber-400 animate-pulse", online: "bg-emerald-500", offline: "bg-rose-500" }[state];
  return (
    <span
      title={health ? `Provedor: ${health.provider}` : undefined}
      className="hidden items-center gap-2 rounded-full border border-slate-200 bg-white/70 px-3 py-1 text-xs text-slate-600 sm:flex dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-300"
    >
      <span className={`h-2 w-2 rounded-full ${dot}`} />
      {label}
    </span>
  );
}

export function Header({ title, health, theme, onToggleTheme, onOpenMenu, onNewConversation }: Props) {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-white/70 px-3 backdrop-blur-md sm:px-5 dark:border-slate-800 dark:bg-slate-950/70">
      <div className="flex min-w-0 items-center gap-2">
        <button className={`${iconButton} lg:hidden`} onClick={onOpenMenu} aria-label="Abrir conversas">
          <MenuIcon className="h-5 w-5" />
        </button>
        <h1 className="truncate text-sm font-medium text-slate-700 dark:text-slate-200">{title}</h1>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        <Status health={health} />
        <button className={iconButton} onClick={onToggleTheme} aria-label="Alternar tema claro/escuro">
          {theme === "dark" ? <SunIcon className="h-5 w-5" /> : <MoonIcon className="h-5 w-5" />}
        </button>
        <button className={`${iconButton} lg:hidden`} onClick={onNewConversation} aria-label="Nova conversa">
          <PlusIcon className="h-5 w-5" />
        </button>
      </div>
    </header>
  );
}
