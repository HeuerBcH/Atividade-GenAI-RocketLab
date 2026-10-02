import type { StepKind, TraceStep } from "../types";

const STYLE: Record<StepKind, { label: string; dot: string }> = {
  pensamento: { label: "Pensamento", dot: "bg-slate-400" },
  acao: { label: "Ação", dot: "bg-brand-500" },
  observacao: { label: "Observação", dot: "bg-emerald-500" },
  erro: { label: "Correção", dot: "bg-amber-500" },
};

// ciclo ReAct da resposta: pensar, agir (ferramenta), observar (resultado)
export function StepsPanel({ steps }: { steps: TraceStep[] }) {
  return (
    <ol className="scrollbar-soft relative max-h-96 space-y-4 overflow-y-auto p-4">
      {steps.map((step, i) => (
        <li key={i} className="relative flex gap-3 text-xs">
          {i < steps.length - 1 && (
            <span className="absolute left-[3px] top-4 h-[calc(100%+0.5rem)] w-px bg-slate-200 dark:bg-slate-700" />
          )}
          <span className={`relative mt-1.5 h-2 w-2 shrink-0 rounded-full ${STYLE[step.kind].dot}`} />
          <div className="min-w-0">
            <p className="font-semibold text-slate-700 dark:text-slate-200">
              {i + 1}. {STYLE[step.kind].label}
            </p>
            <p className="mt-0.5 whitespace-pre-wrap break-words font-mono text-slate-500 dark:text-slate-400">
              {step.content}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}
