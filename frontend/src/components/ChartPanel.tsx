import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatCell } from "../format";

const MAX_POINTS = 30;
const BAR_HEIGHT = 26;
const MAX_LABEL = 26;

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

const shorten = (text: string) => (text.length > MAX_LABEL ? `${text.slice(0, MAX_LABEL - 1)}…` : text);

const tooltipStyle = {
  borderRadius: 10,
  border: "1px solid rgb(221 214 254)",
  boxShadow: "0 4px 16px rgb(0 0 0 / 0.08)",
  fontSize: 12,
};

export function ChartPanel({ columns, rows }: Props) {
  const picked = pickColumns(columns, rows);
  if (!picked) return null;
  const [label, value] = picked;
  const data = rows.map((r) => ({ label: formatCell(r[label]), value: r[value] as number }));
  const isSeries = /ano/i.test(columns[label]);
  const valueName = columns[value].replaceAll("_", " ");
  // barras: a altura cresce com o número de itens para nenhum rótulo sumir
  const height = isSeries ? 260 : Math.max(200, data.length * BAR_HEIGHT + 40);

  return (
    <div
      className="w-full rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900"
      style={{ height }}
    >
      <ResponsiveContainer width="100%" height="100%">
        {isSeries ? (
          <LineChart data={data} margin={{ left: 8, right: 16, top: 12 }}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
            <XAxis dataKey="label" tick={{ fontSize: 12, fill: "#94a3b8" }} />
            <YAxis
              domain={["auto", "auto"]}
              tick={{ fontSize: 12, fill: "#94a3b8" }}
              tickFormatter={(v: number) => formatCell(v)}
              width={70}
            />
            <Tooltip contentStyle={tooltipStyle} formatter={(v) => [formatCell(v), valueName]} />
            <Line type="monotone" dataKey="value" stroke="#7c3aed" strokeWidth={2.5} dot={{ r: 3.5 }} />
          </LineChart>
        ) : (
          <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24 }}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} horizontal={false} />
            <XAxis
              type="number"
              tick={{ fontSize: 12, fill: "#94a3b8" }}
              tickFormatter={(v: number) => formatCell(v)}
            />
            <YAxis
              type="category"
              dataKey="label"
              width={190}
              interval={0}
              tick={{ fontSize: 12, fill: "#94a3b8" }}
              tickFormatter={shorten}
            />
            <Tooltip
              contentStyle={tooltipStyle}
              cursor={{ fill: "rgb(139 92 246 / 0.08)" }}
              formatter={(v) => [formatCell(v), valueName]}
            />
            <Bar dataKey="value" fill="#8b5cf6" radius={[0, 6, 6, 0]} maxBarSize={22} />
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
