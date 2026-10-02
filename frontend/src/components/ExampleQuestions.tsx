import type { ReactNode } from "react";
import type { Examples } from "../types";
import { ChartIcon, ChevronIcon, CodeIcon, DollarIcon, FilmIcon, LayersIcon, SparkIcon, StarIcon, TrendIcon, UsersIcon } from "./icons";

const ICONS: Record<string, ReactNode> = {
  "Bilheteria e Finanças": <DollarIcon />,
  "Popularidade e Engajamento": <TrendIcon />,
  "Elenco e Equipe": <UsersIcon />,
  "Gêneros e Produtoras": <LayersIcon />,
  "Avaliações dos Usuários": <StarIcon />,
  "Busca por tema (sinopses)": <SparkIcon />,
};

const FEATURES: { icon: ReactNode; text: string }[] = [
  { icon: <ChartIcon />, text: "Resposta com gráfico e tabela" },
  { icon: <CodeIcon />, text: "SQL e raciocínio visíveis" },
  { icon: <TrendIcon />, text: 'Continue a conversa: "e só de 2020?"' },
];

export function ExampleQuestions({ examples, onPick }: { examples: Examples; onPick: (q: string) => void }) {
  const categories = Object.entries(examples);
  return (
    <div className="mx-auto max-w-5xl animate-fade-in py-8">
      <div className="mb-8 text-center">
        <div className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br from-brand-500 to-brand-800 text-white shadow-lg shadow-brand-700/30">
          <FilmIcon className="h-7 w-7" />
        </div>
        <h2 className="text-2xl font-semibold tracking-tight">O que você quer saber sobre o catálogo?</h2>
        <p className="mx-auto mt-2 max-w-xl text-sm text-slate-500 dark:text-slate-400">
          Pergunte em português, sem precisar de SQL. O agente consulta a camada Gold em tempo real e
          responde com os dados.
        </p>
        <ul className="mt-4 flex flex-wrap justify-center gap-2">
          {FEATURES.map((f) => (
            <li
              key={f.text}
              className="flex items-center gap-1.5 rounded-full border border-slate-200 bg-white/70 px-3 py-1 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-300"
            >
              <span className="text-brand-500">{f.icon}</span>
              {f.text}
            </li>
          ))}
        </ul>
      </div>

      {categories.length === 0 ? (
        <p className="text-center text-sm text-slate-400">
          Perguntas de exemplo indisponíveis: verifique se a API está rodando.
        </p>
      ) : (
        <>
          <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">Experimente uma pergunta</p>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {categories.map(([category, questions]) => (
              <section
                key={category}
                className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white/90 p-4 shadow-soft dark:border-slate-800 dark:bg-slate-900/90"
              >
                <header className="flex items-center gap-2">
                  <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-50 text-brand-700 ring-1 ring-brand-100 dark:bg-brand-900/40 dark:text-brand-200 dark:ring-brand-800">
                    {ICONS[category] ?? <ChevronIcon />}
                  </span>
                  <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">{category}</h3>
                </header>
                <ul className="flex flex-col gap-1.5">
                  {questions.map((q) => (
                    <li key={q}>
                      <button
                        onClick={() => onPick(q)}
                        className="group flex w-full items-start gap-2 rounded-lg px-2.5 py-2 text-left text-sm text-slate-600 transition hover:bg-brand-50 hover:text-brand-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-brand-100"
                      >
                        <ChevronIcon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-brand-500 dark:text-slate-600" />
                        <span>{q}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
