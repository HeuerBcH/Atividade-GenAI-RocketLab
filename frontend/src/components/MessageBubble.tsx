import { useEffect, useState } from "react";
import type { AskResponse, ChatMessage } from "../types";
import { AnswerDetails } from "./AnswerDetails";
import { AnswerText } from "./AnswerText";
import { AlertIcon, BulbIcon, CheckIcon, CopyIcon, RefreshIcon, SparkIcon } from "./icons";

interface Props {
  message: ChatMessage;
  onRetry: (answerId: string) => void;
}

function Avatar() {
  return (
    <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-sm shadow-brand-700/20">
      <SparkIcon />
    </div>
  );
}

const THINKING = ["Pensando...", "Entendendo a pergunta...", "Analisando os dados...", "Organizando a resposta..."];
const PHASE_SECONDS = 5;

function Thinking({ startedAt }: { startedAt?: number }) {
  const [start] = useState(() => startedAt ?? Date.now());
  const [elapsed, setElapsed] = useState(() => Math.floor((Date.now() - start) / 1000));

  useEffect(() => {
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [start]);

  // a frase avança com o tempo e para na última; volta a "Pensando..." só numa nova pergunta
  const phase = THINKING[Math.min(Math.floor(elapsed / PHASE_SECONDS), THINKING.length - 1)];
  return (
    <div className="flex items-center gap-3 py-1 text-sm" role="status" aria-live="polite">
      <span className="flex gap-1">
        {[0, 150, 300].map((delay) => (
          <span
            key={delay}
            className="h-2 w-2 animate-bounce rounded-full bg-brand-500"
            style={{ animationDelay: `${delay}ms` }}
          />
        ))}
      </span>
      <span key={phase} className="animate-fade-in font-medium text-slate-600 dark:text-slate-300">
        {phase}
      </span>
      {elapsed >= 3 && <span className="text-xs tabular-nums text-slate-400">{elapsed} s</span>}
    </div>
  );
}

function Assumptions({ items }: { items: string[] }) {
  return (
    <div className="rounded-xl border border-brand-100 bg-brand-50/50 px-4 py-3 dark:border-brand-900/50 dark:bg-brand-950/30">
      <p className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-brand-800 dark:text-brand-200">
        <BulbIcon className="h-3.5 w-3.5" />
        Como interpretei a pergunta
      </p>
      <ul className="space-y-1 text-xs text-slate-600 dark:text-slate-300">
        {items.map((a) => (
          <li key={a} className="flex gap-2">
            <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-brand-400" />
            {a}
          </li>
        ))}
      </ul>
    </div>
  );
}

function CopyAnswer({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() =>
        void navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        })
      }
      className="flex items-center gap-1 rounded-md px-2 py-1 text-slate-500 transition hover:bg-slate-100 hover:text-brand-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-brand-300"
    >
      {copied ? <CheckIcon className="h-3.5 w-3.5" /> : <CopyIcon className="h-3.5 w-3.5" />}
      {copied ? "Copiado" : "Copiar resposta"}
    </button>
  );
}

function Footer({ response }: { response: AskResponse }) {
  const meta = response.cached
    ? ["resposta em cache"]
    : [
        response.model,
        `${(response.latency_ms / 1000).toFixed(1)} s`,
        `${response.usage.requests} ${response.usage.requests === 1 ? "chamada" : "chamadas"} ao modelo`,
      ].filter(Boolean);
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3 text-[11px] dark:border-slate-800">
      <span className="text-slate-400">{meta.join(" · ")}</span>
      <CopyAnswer text={response.answer} />
    </div>
  );
}

function Answer({ response }: { response: AskResponse }) {
  return (
    <div className="space-y-4">
      <AnswerText text={response.answer} />
      {response.assumptions.length > 0 && <Assumptions items={response.assumptions} />}
      <AnswerDetails response={response} />
      <Footer response={response} />
    </div>
  );
}

export function MessageBubble({ message, onRetry }: Props) {
  if (message.role === "user") {
    return (
      <div data-message={message.id} className="flex animate-fade-in scroll-mt-4 justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-gradient-to-br from-brand-600 to-brand-700 px-4 py-2.5 text-sm text-white shadow-sm shadow-brand-600/20">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex animate-fade-in gap-3">
      <Avatar />
      <div className="min-w-0 flex-1 rounded-2xl rounded-tl-md border border-slate-200 bg-white/95 px-5 py-4 text-sm shadow-soft dark:border-slate-800 dark:bg-slate-900/95">
        {message.status === "loading" && <Thinking startedAt={message.startedAt} />}
        {message.status === "error" && (
          <div className="flex flex-wrap items-start justify-between gap-3">
            <p className="flex items-start gap-2 text-rose-600 dark:text-rose-400">
              <AlertIcon className="mt-0.5 h-4 w-4 shrink-0" />
              {message.error}
            </p>
            {message.question && (
              <button
                onClick={() => onRetry(message.id)}
                className="flex shrink-0 items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:border-brand-300 hover:text-brand-700 dark:border-slate-700 dark:text-slate-300"
              >
                <RefreshIcon className="h-3.5 w-3.5" /> Tentar novamente
              </button>
            )}
          </div>
        )}
        {message.status === "done" && message.response && <Answer response={message.response} />}
      </div>
    </div>
  );
}
