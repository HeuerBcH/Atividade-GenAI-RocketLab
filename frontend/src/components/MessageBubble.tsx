import type { AskResponse, ChatMessage } from "../types";
import { AnswerText } from "./AnswerText";
import { ChartPanel } from "./ChartPanel";
import { AlertIcon, SparkIcon } from "./icons";
import { ResultTable } from "./ResultTable";
import { SqlBlock } from "./SqlBlock";
import { StepsPanel } from "./StepsPanel";

function Avatar() {
  return (
    <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-sm shadow-brand-700/20">
      <SparkIcon />
    </div>
  );
}

function Meta({ response }: { response: AskResponse }) {
  const chip = "rounded-full bg-slate-100 px-2 py-0.5 dark:bg-slate-800";
  if (response.cached) return <span className={chip}>resposta em cache</span>;
  return (
    <>
      <span className={chip}>{response.model}</span>
      <span className={chip}>{response.usage.requests} chamada(s)</span>
      <span className={chip}>{(response.latency_ms / 1000).toFixed(1)} s</span>
    </>
  );
}

function Answer({ response }: { response: AskResponse }) {
  return (
    <div className="space-y-4">
      <AnswerText text={response.answer} />
      {response.assumptions.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {response.assumptions.map((a) => (
            <span
              key={a}
              className="rounded-lg border border-brand-100 bg-brand-50/60 px-2 py-1 text-xs text-brand-800 dark:border-brand-900/60 dark:bg-brand-950/40 dark:text-brand-200"
            >
              {a}
            </span>
          ))}
        </div>
      )}
      {response.rows.length > 0 && (
        <>
          <ChartPanel columns={response.columns} rows={response.rows} />
          <ResultTable columns={response.columns} rows={response.rows} truncated={response.truncated} />
        </>
      )}
      {response.sql && <SqlBlock sql={response.sql} />}
      {response.steps.length > 0 && <StepsPanel steps={response.steps} />}
      <div className="flex flex-wrap gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
        <Meta response={response} />
      </div>
    </div>
  );
}

function Thinking() {
  return (
    <div className="flex items-center gap-3 text-sm text-slate-500 dark:text-slate-400">
      <span className="flex gap-1">
        {[0, 150, 300].map((delay) => (
          <span
            key={delay}
            className="h-2 w-2 animate-bounce rounded-full bg-brand-500"
            style={{ animationDelay: `${delay}ms` }}
          />
        ))}
      </span>
      Consultando o banco de dados...
    </div>
  );
}

export function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex animate-fade-in justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-md bg-gradient-to-br from-brand-600 to-brand-700 px-4 py-2.5 text-sm text-white shadow-sm shadow-brand-600/20">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex animate-fade-in gap-3">
      <Avatar />
      <div className="min-w-0 flex-1 rounded-2xl rounded-tl-md border border-brand-100 bg-white/95 px-5 py-4 text-sm shadow-soft dark:border-brand-900/40 dark:bg-slate-900/95">
        {message.status === "loading" && <Thinking />}
        {message.status === "error" && (
          <p className="flex items-start gap-2 text-rose-600 dark:text-rose-400">
            <AlertIcon className="mt-0.5 h-4 w-4 shrink-0" />
            {message.error}
          </p>
        )}
        {message.status === "done" && message.response && <Answer response={message.response} />}
      </div>
    </div>
  );
}
