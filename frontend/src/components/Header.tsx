import type { Health } from "../types";
import { FilmIcon, MenuIcon, MoonIcon, PlusIcon, SunIcon } from "./icons";

interface Props {
  health: Health | null | undefined;
  theme: "light" | "dark";
  onToggleTheme: () => void;
  onOpenHistory: () => void;
  onNewConversation: () => void;
}

const iconButton =
  "grid h-9 w-9 place-items-center rounded-lg text-slate-500 transition hover:bg-brand-50 hover:text-brand-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-brand-200";

function Status({ health }: { health: Health | null | undefined }) {
  const online = Boolean(health);
  const label = health === undefined ? "Conectando..." : health ? health.models[0] : "API offline";
  return (
    <span className="hidden items-center gap-2 rounded-full border border-slate-200 bg-white/70 px-3 py-1 text-xs text-slate-600 sm:flex dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-300">
      <span className={`h-2 w-2 rounded-full ${online ? "bg-emerald-500" : "bg-rose-500"}`} />
      {label}
    </span>
  );
}

export function Header({ health, theme, onToggleTheme, onOpenHistory, onNewConversation }: Props) {
  return (
    <header className="sticky top-0 z-20 flex items-center justify-between border-b border-brand-100/70 bg-white/80 px-4 py-3 shadow-soft backdrop-blur-md dark:border-brand-900/40 dark:bg-slate-950/80 sm:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <button className={iconButton} onClick={onOpenHistory} aria-label="Histórico de conversas">
          <MenuIcon className="h-5 w-5" />
        </button>
        <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-800 text-white shadow-sm shadow-brand-700/30">
          <FilmIcon className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <h1 className="truncate text-base font-semibold leading-tight">CineData Analyst</h1>
          <p className="hidden text-xs text-slate-500 dark:text-slate-400 sm:block">
            Perguntas em linguagem natural sobre o catálogo de filmes
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Status health={health} />
        <button className={iconButton} onClick={onToggleTheme} aria-label="Alternar tema">
          {theme === "dark" ? <SunIcon className="h-5 w-5" /> : <MoonIcon className="h-5 w-5" />}
        </button>
        <button
          onClick={onNewConversation}
          className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700"
        >
          <PlusIcon />
          <span className="hidden sm:inline">Nova conversa</span>
        </button>
      </div>
    </header>
  );
}
