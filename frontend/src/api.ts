import type { AskResponse, Examples, Health } from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000";

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // corpo não é JSON
  }
  if (res.status === 422) return "A pergunta precisa ter entre 3 e 500 caracteres.";
  return `Erro ${res.status} ao falar com a API.`;
}

export async function ask(question: string, sessionId: string): Promise<AskResponse> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, session_id: sessionId }),
    });
  } catch {
    throw new Error(`Não foi possível conectar à API em ${API_BASE}. Ela está rodando?`);
  }
  if (!res.ok) throw new Error(await errorMessage(res));
  return (await res.json()) as AskResponse;
}

export async function resetSession(sessionId: string): Promise<void> {
  await fetch(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" }).catch(
    () => undefined,
  );
}

export async function getExamples(): Promise<Examples> {
  const res = await fetch(`${API_BASE}/examples`);
  return res.ok ? ((await res.json()) as Examples) : {};
}

export async function getHealth(): Promise<Health | null> {
  try {
    const res = await fetch(`${API_BASE}/health`);
    return res.ok ? ((await res.json()) as Health) : null;
  } catch {
    return null;
  }
}
