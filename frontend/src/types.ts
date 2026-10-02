export type StepKind = "pensamento" | "acao" | "observacao" | "erro";

export interface TraceStep {
  kind: StepKind;
  content: string;
}

export interface AskResponse {
  question: string;
  session_id: string | null;
  cached: boolean;
  answer: string;
  assumptions: string[];
  sql: string | null;
  columns: string[];
  rows: unknown[][];
  truncated: boolean;
  steps: TraceStep[];
  model: string | null;
  usage: { requests: number; input_tokens: number; output_tokens: number };
  latency_ms: number;
}

export interface Health {
  status: string;
  provider: string;
  models: string[];
}

export type Examples = Record<string, string[]>;

export type ChatMessage =
  | { id: string; role: "user"; content: string }
  | {
      id: string;
      role: "assistant";
      status: "loading" | "done" | "error";
      question?: string; // para refazer a pergunta quando der erro
      startedAt?: number;
      response?: AskResponse;
      error?: string;
    };

export interface Conversation {
  id: string;
  title: string;
  createdAt: number;
  messages: ChatMessage[];
}
