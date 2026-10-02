import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatCell } from "../format";

const MAX_POINTS = 30;

interface Props {
  columns: string[];
  rows: unknown[][];
}

// gráfico só quando o resultado é um rótulo + um número (ranking ou série por ano)
function pickColumns(columns: string[], rows: unknown[][]): [number, number] | null {
  if (rows.length < 2 || rows.length > MAX_POINTS) return null;
  const isNumeric = (i: number) => rows.every((r) => typeof r[i] === "number");
  const label = columns.findIndex((_, i) => !isNumeric(i) || /ano/i.test(columns[i]));
  const value = columns.findIndex((_, i) => i !== label && isNumeric(i));
  return label >= 0 && value >= 0 ? [label, value] : null;
}

export function ChartPanel({ columns, rows }: Props) {
  const picked = pickColumns(columns, rows);
  if (!picked) return null;
  const [label, value] = picked;
  const data = rows.map((r) => ({ label: formatCell(r[label]), value: r[value] as number }));
  const isSeries = /ano/i.test(columns[label]);
  const valueName = columns[value];

  return (
    <div className="h-64 w-full rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
      <ResponsiveContainer width="100%" height="100%">
        {isSeries ? (
          <LineChart data={data} margin={{ left: 8, right: 16, top: 8 }}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
            <XAxis dataKey="label" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} tickFormatter={(v: number) => formatCell(v)} width={70} />
            <Tooltip formatter={(v) => [formatCell(v), valueName]} />
            <Line type="monotone" dataKey="value" stroke="#7c3aed" strokeWidth={2} dot={{ r: 3 }} />
          </LineChart>
        ) : (
          <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
            <XAxis type="number" tick={{ fontSize: 12 }} tickFormatter={(v: number) => formatCell(v)} />
            <YAxis type="category" dataKey="label" width={170} tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v) => [formatCell(v), valueName]} />
            <Bar dataKey="value" fill="#8b5cf6" radius={[0, 4, 4, 0]} />
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
