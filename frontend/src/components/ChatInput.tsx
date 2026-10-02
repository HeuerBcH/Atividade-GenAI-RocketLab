import { useState, type FormEvent, type KeyboardEvent } from "react";
import { SendIcon } from "./icons";

export function ChatInput({ disabled, onSend }: { disabled: boolean; onSend: (q: string) => void }) {
  const [text, setText] = useState("");

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!text.trim() || disabled) return;
    onSend(text);
    setText("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) submit(event);
  }

  return (
    <form onSubmit={submit} className="mx-auto max-w-4xl">
      <div className="flex items-end gap-2 rounded-2xl border border-brand-100 bg-white p-2 shadow-soft transition focus-within:border-brand-400 focus-within:ring-4 focus-within:ring-brand-500/10 dark:border-brand-900/50 dark:bg-slate-900">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          maxLength={500}
          placeholder="Pergunte sobre receita, popularidade, elenco, gêneros ou avaliações..."
          className="max-h-40 min-h-[44px] flex-1 resize-none bg-transparent px-3 py-2.5 text-sm outline-none placeholder:text-slate-400"
        />
        <button
          type="submit"
          disabled={disabled || !text.trim()}
          aria-label="Enviar pergunta"
          className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-brand-600 text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <SendIcon />
        </button>
      </div>
      <p className="mt-2 text-center text-[11px] text-slate-400">
        Enter envia · Shift+Enter quebra a linha · as respostas vêm direto do banco e podem levar até um minuto
      </p>
    </form>
  );
}
