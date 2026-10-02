import type { Conversation } from "../types";
import { PlusIcon, TrashIcon, XIcon } from "./icons";

interface Props {
  open: boolean;
  conversations: Conversation[];
  currentId: string;
  onClose: () => void;
  onPick: (id: string) => void;
  onDelete: (id: string) => void;
  onNew: () => void;
}

const dateFormat = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });

export function HistoryDrawer({ open, conversations, currentId, onClose, onPick, onDelete, onNew }: Props) {
  return (
    <>
      {open && (
        <button
          className="fixed inset-0 z-40 bg-slate-900/40 backdrop-blur-sm dark:bg-black/50"
          onClick={onClose}
          aria-label="Fechar histórico"
        />
      )}
      <aside
        className={`fixed left-0 top-0 z-50 flex h-full w-80 flex-col border-r border-brand-100 bg-white shadow-2xl transition-transform duration-200 dark:border-brand-900/50 dark:bg-slate-900 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between border-b border-brand-100 bg-gradient-to-r from-brand-50 to-white px-4 py-4 dark:border-brand-900/50 dark:from-brand-950/50 dark:to-slate-900">
          <div>
            <h2 className="text-sm font-semibold text-brand-900 dark:text-brand-100">Histórico</h2>
            <p className="text-[11px] text-brand-700/80 dark:text-brand-300/80">Conversas salvas neste navegador</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-500 hover:bg-brand-50 hover:text-brand-700 dark:hover:bg-slate-800"
            aria-label="Fechar histórico"
          >
            <XIcon />
          </button>
        </div>

        <div className="border-b border-brand-100 p-3 dark:border-brand-900/50">
          <button
            onClick={() => {
              onNew();
              onClose();
            }}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700"
          >
            <PlusIcon /> Nova conversa
          </button>
        </div>

        <ul className="scrollbar-soft flex-1 space-y-1 overflow-y-auto p-2">
          {conversations.length === 0 && (
            <li className="px-3 py-6 text-center text-sm text-slate-400">Nenhuma conversa ainda.</li>
          )}
          {conversations.map((c) => (
            <li key={c.id} className="group relative">
              <button
                onClick={() => {
                  onPick(c.id);
                  onClose();
                }}
                className={`w-full rounded-lg px-3 py-2 pr-9 text-left transition ${
                  c.id === currentId
                    ? "bg-brand-50 text-brand-900 dark:bg-brand-950/60 dark:text-brand-100"
                    : "hover:bg-slate-50 dark:hover:bg-slate-800"
                }`}
              >
                <p className="truncate text-sm font-medium">{c.title}</p>
                <p className="text-[11px] text-slate-400">
                  {dateFormat.format(c.createdAt)} · {c.messages.filter((m) => m.role === "user").length} pergunta(s)
                </p>
              </button>
              <button
                onClick={() => onDelete(c.id)}
                className="absolute right-2 top-1/2 hidden -translate-y-1/2 rounded p-1 text-slate-400 hover:text-rose-500 group-hover:block"
                aria-label="Apagar conversa"
              >
                <TrashIcon />
              </button>
            </li>
          ))}
        </ul>
      </aside>
    </>
  );
}
