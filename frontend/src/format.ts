const number = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });

export function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    // anos e ids não levam separador de milhar
    return Number.isInteger(value) && value >= 1900 && value <= 2100 ? String(value) : number.format(value);
  }
  return String(value);
}

export function toCsv(columns: string[], rows: unknown[][]): string {
  const escape = (v: unknown) => {
    const text = v === null || v === undefined ? "" : String(v);
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
