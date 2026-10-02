import { useId } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { columnLabel, formatCell, formatCompact } from "../format";

const MAX_POINTS = 30;
const ROW_HEIGHT = 34;
const MAX_LABEL = 30;

interface Props {
  columns: string[];
  rows: unknown[][];
}

const isYear = (column: string) => /^ano|_ano$|year/i.test(column);

// gráfico só quando o resultado é um rótulo + um número que varia (ranking ou série por ano)
function pickColumns(columns: string[], rows: unknown[][]): [number, number] | null {
  if (rows.length < 2 || rows.length > MAX_POINTS) return null;
  const isNumeric = (i: number) => rows.every((r) => typeof r[i] === "number");
  const label = columns.findIndex((_, i) => !isNumeric(i) || isYear(columns[i]));
  // ano é eixo, nunca métrica (num ranking de filmes a coluna ano vem antes da receita)
  const value = columns.findIndex((_, i) => i !== label && isNumeric(i) && !isYear(columns[i]));
  if (label < 0 || value < 0) return null;
  const distinct = new Set(rows.map((r) => r[value])).size;
  return distinct > 1 ? [label, value] : null; // valores todos iguais não dizem nada num gráfico
}

interface TickProps {
  x?: number | string;
  y?: number | string;
  payload?: { value: unknown };
}

function CategoryTick({ x = 0, y = 0, payload }: TickProps) {
  const text = String(payload?.value ?? "");
  const short = text.length > MAX_LABEL ? `${text.slice(0, MAX_LABEL - 1)}…` : text;
  return (
    <text x={Number(x) - 10} y={Number(y)} dy={4} textAnchor="end" className="fill-slate-600 text-[12px] dark:fill-slate-300">
      <title>{text}</title>
      {short}
    </text>
  );
}

interface TooltipProps {
  active?: boolean;
  payload?: ReadonlyArray<{ value?: unknown }>;
  label?: unknown;
  name: string;
}

function ChartTooltip({ active, payload, label, name }: TooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-brand-100 bg-white/95 px-3 py-2 text-xs shadow-lg backdrop-blur dark:border-brand-900/60 dark:bg-slate-900/95">
      <p className="mb-0.5 font-semibold text-slate-800 dark:text-slate-100">{String(label)}</p>
      <p className="text-slate-500 dark:text-slate-400">
        {name}: <span className="font-semibold text-brand-700 dark:text-brand-300">{formatCell(payload[0].value)}</span>
      </p>
    </div>
  );
}

export const canChart = (columns: string[], rows: unknown[][]) => pickColumns(columns, rows) !== null;

export function ChartPanel({ columns, rows }: Props) {
  const id = useId().replaceAll(":", "");
  const picked = pickColumns(columns, rows);
  if (!picked) return null;

  const [label, value] = picked;
  const data = rows.map((r) => ({ label: formatCell(r[label]), value: r[value] as number }));
  const isSeries = isYear(columns[label]);
  const valueName = columnLabel(columns[value]);
  const tooltip = (props: Omit<TooltipProps, "name">) => <ChartTooltip {...props} name={valueName} />;

  return (
    <figure className="p-4">
      <figcaption className="mb-3 flex items-center gap-2 text-xs font-medium text-slate-500 dark:text-slate-400">
        <span className="text-slate-700 dark:text-slate-200">{valueName}</span>
        <span className="text-slate-400">por {columnLabel(columns[label]).toLowerCase()}</span>
      </figcaption>

      {isSeries ? (
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id={`area-${id}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#8b5cf6" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#8b5cf6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} strokeDasharray="4 4" stroke="#94a3b8" strokeOpacity={0.25} />
              <XAxis dataKey="label" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: "#94a3b8" }} />
              <YAxis
                domain={[(min: number) => Math.floor(min), (max: number) => Math.ceil(max)]}
                allowDecimals={false}
                axisLine={false}
                tickLine={false}
                width={56}
                tick={{ fontSize: 12, fill: "#94a3b8" }}
                tickFormatter={formatCompact}
              />
              <Tooltip content={tooltip} cursor={{ stroke: "#8b5cf6", strokeOpacity: 0.3 }} />
              <Area
                type="monotone"
                dataKey="value"
                stroke="#7c3aed"
                strokeWidth={2.5}
                fill={`url(#area-${id})`}
                dot={{ r: 3, fill: "#7c3aed", strokeWidth: 0 }}
                activeDot={{ r: 5 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div style={{ height: data.length * ROW_HEIGHT + 8 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical" margin={{ top: 0, right: 64, left: 0, bottom: 0 }} barCategoryGap={7}>
              <defs>
                <linearGradient id={`bar-${id}`} x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="#c4b5fd" />
                  <stop offset="100%" stopColor="#7c3aed" />
                </linearGradient>
              </defs>
              <XAxis type="number" hide domain={[(min: number) => Math.min(0, min), "dataMax"]} />
              <YAxis
                type="category"
                dataKey="label"
                width={230}
                interval={0}
                axisLine={false}
                tickLine={false}
                tick={<CategoryTick />}
              />
              <Tooltip content={tooltip} cursor={{ fill: "rgb(139 92 246 / 0.07)" }} />
              <Bar dataKey="value" fill={`url(#bar-${id})`} radius={[0, 6, 6, 0]} maxBarSize={22}>
                <LabelList
                  dataKey="value"
                  position="right"
                  formatter={formatCompact}
                  className="fill-slate-500 text-[11px] font-medium dark:fill-slate-400"
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </figure>
  );
}
