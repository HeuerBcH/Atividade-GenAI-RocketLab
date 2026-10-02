import { useLayoutEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { SendIcon } from "./icons";

const MAX_LENGTH = 500;

export function ChatInput({ disabled, onSend }: { disabled: boolean; onSend: (q: string) => void }) {
  const [text, setText] = useState("");
  const area = useRef<HTMLTextAreaElement>(null);

  // a caixa cresce com o texto até o max-h
  useLayoutEffect(() => {
    const el = area.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [text]);

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!text.trim() || disabled) return;
    onSend(text);
    setText("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) submit(event);
  }

  const nearLimit = text.length > MAX_LENGTH * 0.8;
  return (
    <form onSubmit={submit} className="mx-auto max-w-3xl">
      <div className="flex items-end gap-2 rounded-2xl border border-slate-200 bg-white p-2 shadow-soft transition focus-within:border-brand-400 focus-within:ring-4 focus-within:ring-brand-500/10 dark:border-slate-700 dark:bg-slate-900">
        <textarea
          ref={area}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          maxLength={MAX_LENGTH}
          aria-label="Sua pergunta"
          placeholder="Pergunte sobre receita, popularidade, elenco, gêneros ou avaliações..."
          className="scrollbar-soft max-h-40 min-h-[44px] flex-1 resize-none bg-transparent px-3 py-2.5 text-sm outline-none placeholder:text-slate-400"
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
      <div className="mt-2 flex justify-between gap-3 px-1 text-[11px] text-slate-400">
        <span className="hidden sm:inline">
          <kbd className="font-sans font-semibold">Enter</kbd> envia ·{" "}
          <kbd className="font-sans font-semibold">Shift+Enter</kbd> quebra a linha
        </span>
        <span className={`ml-auto ${nearLimit ? "text-amber-600 dark:text-amber-400" : ""}`}>
          {nearLimit ? `${text.length}/${MAX_LENGTH}` : "As respostas podem levar até um minuto"}
        </span>
      </div>
    </form>
  );
}
