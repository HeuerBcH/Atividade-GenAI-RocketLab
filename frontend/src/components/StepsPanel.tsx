import type { StepKind, TraceStep } from "../types";
import { StepsIcon } from "./icons";

const STYLE: Record<StepKind, { label: string; dot: string }> = {
  pensamento: { label: "Pensamento", dot: "bg-slate-400" },
  acao: { label: "Ação", dot: "bg-brand-500" },
  observacao: { label: "Observação", dot: "bg-emerald-500" },
  erro: { label: "Correção", dot: "bg-amber-500" },
};

export function StepsPanel({ steps }: { steps: TraceStep[] }) {
  return (
    <details className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700">
      <summary className="flex cursor-pointer select-none items-center gap-2 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-600 hover:text-brand-700 dark:bg-slate-800/60 dark:text-slate-300">
        <StepsIcon className="h-3.5 w-3.5" />
        Raciocínio do agente ({steps.length} passos)
      </summary>
      <ol className="space-y-3 p-4">
        {steps.map((step, i) => (
          <li key={i} className="flex gap-3 text-xs">
            <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${STYLE[step.kind].dot}`} />
            <div className="min-w-0">
              <p className="font-semibold text-slate-700 dark:text-slate-200">{STYLE[step.kind].label}</p>
              <p className="whitespace-pre-wrap break-words font-mono text-slate-500 dark:text-slate-400">
                {step.content}
              </p>
            </div>
          </li>
        ))}
      </ol>
    </details>
  );
}
