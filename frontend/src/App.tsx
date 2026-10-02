import { useEffect, useRef, useState } from "react";
import { getExamples, getHealth } from "./api";
import { ChatInput } from "./components/ChatInput";
import { ExampleQuestions } from "./components/ExampleQuestions";
import { Header } from "./components/Header";
import { MessageBubble } from "./components/MessageBubble";
import { Sidebar } from "./components/Sidebar";
import type { Examples, Health } from "./types";
import { useChat } from "./useChat";
import { useTheme } from "./useTheme";

export default function App() {
  const { current, history, busy, send, retry, startNew, open, remove } = useChat();
  const { theme, toggle } = useTheme();
  const [menuOpen, setMenuOpen] = useState(false);
  const [examples, setExamples] = useState<Examples>({});
  const [health, setHealth] = useState<Health | null | undefined>(undefined);
  const main = useRef<HTMLElement>(null);

  useEffect(() => {
    void getHealth().then(setHealth);
    void getExamples()
      .then(setExamples)
      .catch(() => setExamples({}));
  }, []);

  // leva a última pergunta ao topo: a resposta aparece logo abaixo, a partir do começo
  const lastQuestion = [...current.messages].reverse().find((m) => m.role === "user")?.id;
  const last = current.messages.at(-1);
  const lastStatus = last?.role === "assistant" ? last.status : undefined;
  useEffect(() => {
    if (!lastQuestion) return;
    main.current
      ?.querySelector(`[data-message="${lastQuestion}"]`)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [lastQuestion, lastStatus]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMenuOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const empty = current.messages.length === 0;
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar
        open={menuOpen}
        conversations={history}
        currentId={current.id}
        onClose={() => setMenuOpen(false)}
        onPick={open}
        onDelete={remove}
        onNew={startNew}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <Header
          title={empty ? "Nova conversa" : current.title}
          health={health}
          theme={theme}
          onToggleTheme={toggle}
          onOpenMenu={() => setMenuOpen(true)}
          onNewConversation={startNew}
        />

        <main ref={main} className="scrollbar-soft flex-1 overflow-y-auto px-4 sm:px-6">
          {empty ? (
            <ExampleQuestions examples={examples} onPick={(q) => void send(q)} />
          ) : (
            <div className="mx-auto max-w-3xl space-y-6 py-6">
              {current.messages.map((m) => (
                <MessageBubble key={m.id} message={m} onRetry={(id) => void retry(id)} />
              ))}
              {/* espaço para a última pergunta conseguir subir até o topo */}
              <div className="h-[40vh]" aria-hidden />
            </div>
          )}
        </main>

        <footer className="shrink-0 px-4 pb-3 pt-2 sm:px-6">
          <ChatInput disabled={busy} onSend={(q) => void send(q)} />
        </footer>
      </div>
    </div>
  );
}
