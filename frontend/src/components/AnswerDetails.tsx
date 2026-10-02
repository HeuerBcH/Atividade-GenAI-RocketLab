import { useState, type ReactNode } from "react";
import type { AskResponse } from "../types";
import { ChartPanel, canChart } from "./ChartPanel";
import { ChartIcon, CodeIcon, StepsIcon, TableIcon } from "./icons";
import { ResultTable } from "./ResultTable";
import { SqlBlock } from "./SqlBlock";
import { StepsPanel } from "./StepsPanel";

interface Tab {
  id: string;
  label: string;
  icon: ReactNode;
  render: () => ReactNode;
}

function tabsFor(response: AskResponse): Tab[] {
  const { columns, rows, sql, steps, truncated } = response;
  const tabs: Tab[] = [];
  if (canChart(columns, rows))
    tabs.push({ id: "chart", label: "Gráfico", icon: <ChartIcon />, render: () => <ChartPanel columns={columns} rows={rows} /> });
  if (rows.length > 0)
    tabs.push({
      id: "table",
      label: `Tabela (${rows.length})`,
      icon: <TableIcon />,
      render: () => <ResultTable columns={columns} rows={rows} truncated={truncated} />,
    });
  if (sql) tabs.push({ id: "sql", label: "SQL", icon: <CodeIcon />, render: () => <SqlBlock sql={sql} /> });
  if (steps.length > 0)
    tabs.push({
      id: "steps",
      label: `Raciocínio (${steps.length})`,
      icon: <StepsIcon />,
      render: () => <StepsPanel steps={steps} />,
    });
  return tabs;
}

// dados, consulta e passos do agente organizados em abas, em vez de empilhados
export function AnswerDetails({ response }: { response: AskResponse }) {
  const tabs = tabsFor(response);
  const [active, setActive] = useState(tabs[0]?.id);
  if (tabs.length === 0) return null;
  const current = tabs.find((t) => t.id === active) ?? tabs[0];

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700">
      <div
        role="tablist"
        className="flex gap-1 overflow-x-auto overflow-y-hidden border-b border-slate-200 bg-slate-50/80 px-1.5 pt-1.5 dark:border-slate-700 dark:bg-slate-800/40"
      >
        {tabs.map((tab) => {
          const selected = tab.id === current.id;
          return (
            <button
              key={tab.id}
              role="tab"
              aria-selected={selected}
              onClick={() => setActive(tab.id)}
              className={`-mb-px flex shrink-0 items-center gap-1.5 rounded-t-lg border px-3 py-1.5 text-xs font-medium transition ${
                selected
                  ? "border-slate-200 border-b-white bg-white text-brand-700 dark:border-slate-700 dark:border-b-slate-900 dark:bg-slate-900 dark:text-brand-300"
                  : "border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          );
        })}
      </div>
      <div role="tabpanel" className="bg-white dark:bg-slate-900">
        {current.render()}
      </div>
    </div>
  );
}
