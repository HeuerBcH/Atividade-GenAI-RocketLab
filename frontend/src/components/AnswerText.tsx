import type { ReactNode } from "react";

// o modelo responde com um markdown simples: parágrafos, listas, **negrito**, *itálico* e `código`
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`)/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`"))
      return (
        <code key={i} className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[0.85em] dark:bg-slate-800">
          {part.slice(1, -1)}
        </code>
      );
    if (part.length > 2 && part.startsWith("*") && part.endsWith("*")) return <em key={i}>{part.slice(1, -1)}</em>;
    return part;
  });
}

export function AnswerText({ text }: { text: string }) {
  const lines = text.split("\n").filter((line) => line.trim());
  return (
    <div className="space-y-1.5 leading-relaxed">
      {lines.map((line, i) => {
        const item = line.match(/^\s*(?:[-*•]|\d+[.)])\s+(.*)$/);
        return item ? (
          <p key={i} className="flex gap-2">
            <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" />
            <span>{inline(item[1])}</span>
          </p>
        ) : (
          <p key={i}>{inline(line)}</p>
        );
      })}
    </div>
  );
}
