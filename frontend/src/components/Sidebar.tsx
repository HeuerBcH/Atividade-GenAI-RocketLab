import type { Conversation } from "../types";
import { ChatIcon, FilmIcon, PlusIcon, TrashIcon, XIcon } from "./icons";

interface Props {
  open: boolean;
  conversations: Conversation[];
  currentId: string;
  onClose: () => void;
  onPick: (id: string) => void;
  onDelete: (id: string) => void;
  onNew: () => void;
}

const DAY = 86_400_000;

function groupOf(timestamp: number): string {
  const today = new Date().setHours(0, 0, 0, 0);
  const day = new Date(timestamp).setHours(0, 0, 0, 0);
  const days = Math.round((today - day) / DAY);
  if (days <= 0) return "Hoje";
  if (days === 1) return "Ontem";
  if (days < 7) return "Últimos 7 dias";
  return "Anteriores";
}

function grouped(conversations: Conversation[]): [string, Conversation[]][] {
  const groups = new Map<string, Conversation[]>();
  for (const c of conversations) {
    const label = groupOf(c.createdAt);
    groups.set(label, [...(groups.get(label) ?? []), c]);
  }
  return [...groups];
}

// fixa no desktop; no celular vira uma gaveta aberta pelo botão do cabeçalho
export function Sidebar({ open, conversations, currentId, onClose, onPick, onDelete, onNew }: Props) {
  const pick = (id: string) => {
    onPick(id);
    onClose();
  };

  return (
    <>
      {open && (
        <button
          className="fixed inset-0 z-40 bg-slate-900/40 backdrop-blur-sm lg:hidden dark:bg-black/50"
          onClick={onClose}
          aria-label="Fechar menu"
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-72 shrink-0 flex-col border-r border-slate-200 bg-white/95 shadow-2xl backdrop-blur-md transition-transform duration-200 lg:static lg:z-auto lg:translate-x-0 lg:shadow-none dark:border-slate-800 dark:bg-slate-950/95 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-4 pb-3 pt-4">
          <div className="flex items-center gap-2.5">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-800 text-white shadow-sm shadow-brand-700/30">
              <FilmIcon className="h-5 w-5" />
            </div>
            <div className="leading-tight">
              <p className="text-sm font-semibold">CineData Analyst</p>
              <p className="text-[11px] text-slate-500 dark:text-slate-400">Catálogo de filmes · camada Gold</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 lg:hidden dark:hover:bg-slate-800"
            aria-label="Fechar menu"
          >
            <XIcon />
          </button>
        </div>

        <div className="px-3 pb-3">
          <button
            onClick={() => {
              onNew();
              onClose();
            }}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand-600 px-3 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700"
          >
            <PlusIcon /> Nova conversa
          </button>
        </div>

        <nav className="scrollbar-soft flex-1 overflow-y-auto px-2 pb-3" aria-label="Conversas">
          {conversations.length === 0 && (
            <div className="mx-2 mt-4 rounded-xl border border-dashed border-slate-200 px-4 py-6 text-center text-xs text-slate-400 dark:border-slate-800">
              Suas conversas aparecem aqui.
            </div>
          )}
          {grouped(conversations).map(([label, items]) => (
            <section key={label} className="mt-3 first:mt-0">
              <h3 className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">{label}</h3>
              <ul className="space-y-0.5">
                {items.map((c) => {
                  const active = c.id === currentId;
                  const questions = c.messages.filter((m) => m.role === "user").length;
                  return (
                    <li key={c.id} className="group relative">
                      <button
                        onClick={() => pick(c.id)}
                        aria-current={active ? "page" : undefined}
                        className={`flex w-full items-start gap-2.5 rounded-lg px-3 py-2 pr-9 text-left transition ${
                          active
                            ? "bg-brand-50 text-brand-900 dark:bg-brand-950/60 dark:text-brand-100"
                            : "text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800/70"
                        }`}
                      >
                        <ChatIcon
                          className={`mt-0.5 h-4 w-4 shrink-0 ${active ? "text-brand-600 dark:text-brand-300" : "text-slate-400"}`}
                        />
                        <span className="min-w-0">
                          <span className="block truncate text-sm">{c.title}</span>
                          <span className="block text-[11px] text-slate-400">
                            {questions} {questions === 1 ? "pergunta" : "perguntas"}
                          </span>
                        </span>
                      </button>
                      <button
                        onClick={() => onDelete(c.id)}
                        className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-slate-400 opacity-0 transition hover:text-rose-500 focus:opacity-100 group-hover:opacity-100"
                        aria-label={`Apagar conversa "${c.title}"`}
                      >
                        <TrashIcon />
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </nav>

        <p className="border-t border-slate-200 px-4 py-3 text-[11px] text-slate-400 dark:border-slate-800">
          Conversas salvas apenas neste navegador.
        </p>
      </aside>
    </>
  );
}
