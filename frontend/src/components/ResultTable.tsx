import { downloadCsv, formatCell } from "../format";
import { DownloadIcon } from "./icons";

const SHOWN_ROWS = 50;

interface Props {
  columns: string[];
  rows: unknown[][];
  truncated: boolean;
}

export function ResultTable({ columns, rows, truncated }: Props) {
  const numeric = columns.map((_, i) => rows.every((r) => r[i] === null || typeof r[i] === "number"));
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700">
      <div className="scrollbar-soft max-h-80 overflow-auto">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 bg-slate-50 text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-800 dark:text-slate-400">
            <tr>
              {columns.map((c, i) => (
                <th key={c} className={`whitespace-nowrap px-3 py-2 font-semibold ${numeric[i] ? "text-right" : ""}`}>
                  {c.replaceAll("_", " ")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {rows.slice(0, SHOWN_ROWS).map((row, i) => (
              <tr key={i} className="hover:bg-brand-50/50 dark:hover:bg-slate-800/50">
                {row.map((cell, j) => (
                  <td
                    key={j}
                    className={`px-3 py-2 ${typeof cell === "number" ? "text-right font-mono text-xs tabular-nums" : ""}`}
                  >
                    {formatCell(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-800/60">
        <span>
          {rows.length} linha(s)
          {rows.length > SHOWN_ROWS && ` · exibindo ${SHOWN_ROWS}`}
          {truncated && " · resultado truncado"}
        </span>
        <button
          onClick={() => downloadCsv(columns, rows)}
          className="flex items-center gap-1 font-medium hover:text-brand-700 dark:hover:text-brand-300"
        >
          <DownloadIcon className="h-3.5 w-3.5" /> CSV
        </button>
      </div>
    </div>
  );
}
