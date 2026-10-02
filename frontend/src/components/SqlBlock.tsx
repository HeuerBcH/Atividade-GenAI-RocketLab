import { useState } from "react";
import { CheckIcon, CopyIcon } from "./icons";

export function SqlBlock({ sql }: { sql: string }) {
  const [copied, setCopied] = useState(false);

  function copy() {
    void navigator.clipboard.writeText(sql).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  return (
    <div className="relative bg-slate-950">
      <button
        onClick={copy}
        className="absolute right-2 top-2 flex items-center gap-1 rounded-md bg-white/10 px-2 py-1 text-[11px] text-slate-200 hover:bg-white/20"
      >
        {copied ? <CheckIcon className="h-3 w-3" /> : <CopyIcon className="h-3 w-3" />}
        {copied ? "Copiado" : "Copiar"}
      </button>
      <pre className="scrollbar-soft max-h-80 overflow-auto p-4 pr-20 font-mono text-xs leading-relaxed text-slate-100">
        {sql}
      </pre>
    </div>
  );
}
