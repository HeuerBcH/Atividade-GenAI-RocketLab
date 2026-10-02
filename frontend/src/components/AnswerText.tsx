import type { ReactNode } from "react";

// o modelo responde com um markdown simples: parágrafos, listas e **negrito**
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? <strong key={i}>{part.slice(2, -2)}</strong> : part,
  );
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
