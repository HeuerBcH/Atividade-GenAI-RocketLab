import { useState } from "react";
import { CheckIcon, CodeIcon, CopyIcon } from "./icons";

export function SqlBlock({ sql }: { sql: string }) {
  const [copied, setCopied] = useState(false);

  function copy() {
    void navigator.clipboard.writeText(sql).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  return (
    <details className="group overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700">
      <summary className="flex cursor-pointer select-none items-center gap-2 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-600 hover:text-brand-700 dark:bg-slate-800/60 dark:text-slate-300">
        <CodeIcon className="h-3.5 w-3.5" />
        SQL executada
      </summary>
      <div className="relative bg-slate-950">
        <button
          onClick={copy}
          className="absolute right-2 top-2 flex items-center gap-1 rounded-md bg-white/10 px-2 py-1 text-[11px] text-slate-200 hover:bg-white/20"
        >
          {copied ? <CheckIcon className="h-3 w-3" /> : <CopyIcon className="h-3 w-3" />}
          {copied ? "Copiado" : "Copiar"}
        </button>
        <pre className="scrollbar-soft overflow-x-auto p-4 pr-20 font-mono text-xs leading-relaxed text-slate-100">
          {sql}
        </pre>
      </div>
    </details>
  );
}
