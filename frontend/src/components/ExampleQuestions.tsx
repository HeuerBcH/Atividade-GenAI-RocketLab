import type { ReactNode } from "react";
import type { Examples } from "../types";
import { ChevronIcon, DollarIcon, FilmIcon, LayersIcon, StarIcon, TrendIcon, UsersIcon } from "./icons";

const ICONS: Record<string, ReactNode> = {
  "Bilheteria e Finanças": <DollarIcon />,
  "Popularidade e Engajamento": <TrendIcon />,
  "Elenco e Equipe": <UsersIcon />,
  "Gêneros e Produtoras": <LayersIcon />,
  "Avaliações dos Usuários": <StarIcon />,
};

export function ExampleQuestions({ examples, onPick }: { examples: Examples; onPick: (q: string) => void }) {
  return (
    <div className="mx-auto max-w-5xl animate-fade-in py-6">
      <div className="mb-8 text-center">
        <div className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br from-brand-500 to-brand-800 text-white shadow-lg shadow-brand-700/30">
          <FilmIcon className="h-7 w-7" />
        </div>
        <h2 className="text-2xl font-semibold tracking-tight">O que você quer saber sobre o catálogo?</h2>
        <p className="mx-auto mt-2 max-w-xl text-sm text-slate-500 dark:text-slate-400">
          Pergunte em português. O agente escreve a consulta, executa na camada Gold e responde com os
          dados, um gráfico e a SQL usada. Dá para continuar a conversa, como em "e só de 2020?".
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Object.entries(examples).map(([category, questions]) => (
          <section
            key={category}
            className="flex flex-col gap-3 rounded-2xl border border-brand-100 bg-white/90 p-5 shadow-soft transition hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-md dark:border-brand-900/50 dark:bg-slate-900/90 dark:hover:border-brand-700"
          >
            <header className="flex items-center gap-2">
              <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-50 text-brand-700 ring-1 ring-brand-100 dark:bg-brand-900/40 dark:text-brand-200 dark:ring-brand-800">
                {ICONS[category] ?? <ChevronIcon />}
              </span>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-brand-700 dark:text-brand-300">
                {category}
              </h3>
            </header>
            <ul className="flex flex-col gap-2">
              {questions.map((q) => (
                <li key={q}>
                  <button
                    onClick={() => onPick(q)}
                    className="flex w-full items-start gap-2 rounded-xl border border-slate-100 bg-white px-3 py-2.5 text-left text-sm text-slate-700 transition hover:border-brand-300 hover:bg-brand-50 hover:text-brand-900 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:border-brand-600 dark:hover:bg-slate-700"
                  >
                    <ChevronIcon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand-500" />
                    <span>{q}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
