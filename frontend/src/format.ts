const number = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
// margens e diferenças pequenas (0,1234) perderiam a informação com só 2 casas
const small = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 4 });

// só apresentação: o CSV e os dados da resposta continuam com o valor original
export function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    // anos e ids não levam separador de milhar
    if (Number.isInteger(value) && value >= 1900 && value <= 2100) return String(value);
    return (Math.abs(value) < 10 ? small : number).format(value);
  }
  return String(value);
}

const WORDS: Record<string, string> = {
  titulo: "título",
  lancamento: "lançamento",
  genero: "gênero",
  media: "média",
  medio: "médio",
  orcamento: "orçamento",
  avaliacoes: "avaliações",
  usuarios: "usuários",
  divergencia: "divergência",
  participacoes: "participações",
  duracao: "duração",
  qtd: "qtd.",
};
const CURRENCY: Record<string, string> = { brl: "(R$)", usd: "(US$)" };

// nome da coluna para leitura: "receita_brl" -> "Receita (R$)", "ano_lancamento" -> "Ano lançamento"
export function columnLabel(column: string): string {
  const words = column.toLowerCase().split("_").filter(Boolean);
  const label = words.map((w) => CURRENCY[w] ?? WORDS[w] ?? w).join(" ");
  return label.charAt(0).toUpperCase() + label.slice(1);
}

// texto que começa com = + - @ vira fórmula no Excel (injeção de CSV, OWASP); há títulos assim
// na base ("+-90", "-21"). O apóstrofo faz a planilha tratar como texto e não aparece na célula
const FORMULA_START = /^[=+\-@\t\r]/;

export function toCsv(columns: string[], rows: unknown[][]): string {
  const escape = (v: unknown) => {
    let text = v === null || v === undefined ? "" : String(v);
    if (typeof v === "string" && FORMULA_START.test(text)) text = `'${text}`;
    return /[",;\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
  };
  return [columns, ...rows].map((r) => r.map(escape).join(";")).join("\n");
}

export function downloadCsv(columns: string[], rows: unknown[][], name = "resultado.csv") {
  // BOM para o Excel abrir os acentos certo
  const blob = new Blob(["\ufeff" + toCsv(columns, rows)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = Object.assign(document.createElement("a"), { href: url, download: name });
  link.click();
  URL.revokeObjectURL(url);
}

const compact = new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 });

// para eixos e rótulos de gráfico: 12.390.136.500 -> "12,4 bi"
export function formatCompact(value: unknown): string {
  if (typeof value !== "number") return String(value ?? "");
  return Math.abs(value) >= 10_000 ? compact.format(value) : formatCell(value);
}
