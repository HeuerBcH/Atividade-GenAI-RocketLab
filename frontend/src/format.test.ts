import { describe, expect, it } from "vitest";
import { columnLabel, formatCell, toCsv } from "./format";

describe("toCsv", () => {
  it("neutraliza texto que viraria fórmula, sem mexer em números", () => {
    const csv = toCsv(["titulo", "lucro"], [["+-90", -5], ["=HYPERLINK(1)", 3], ["-21", 0]]);
    expect(csv.split("\n")).toEqual(["titulo;lucro", "'+-90;-5", "'=HYPERLINK(1);3", "'-21;0"]);
  });

  it("escapa separador, aspas e quebra de linha", () => {
    expect(toCsv(["t"], [['A; "B"\nC']])).toBe('t\n"A; ""B""\nC"');
  });

  it("deixa nulos como célula vazia", () => {
    expect(toCsv(["a", "b"], [[null, undefined]])).toBe("a;b\n;");
  });
});

describe("formatCell", () => {
  it("mostra anos sem separador e números no padrão brasileiro", () => {
    expect(formatCell(2022)).toBe("2022");
    expect(formatCell(12390136500.54)).toBe("12.390.136.500,54");
    expect(formatCell(null)).toBe("—");
  });

  it("mantém 4 casas em valores pequenos, como margens", () => {
    expect(formatCell(0.1234)).toBe("0,1234");
  });
});

describe("columnLabel", () => {
  it("traduz nomes de coluna para leitura", () => {
    expect(columnLabel("receita_brl")).toBe("Receita (R$)");
    expect(columnLabel("ano_lancamento")).toBe("Ano lançamento");
    expect(columnLabel("qtd_avaliacoes_usuarios")).toBe("Qtd. avaliações usuários");
  });
});
