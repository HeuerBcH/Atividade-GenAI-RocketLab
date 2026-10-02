import { useEffect, useRef, useState } from "react";
import { getExamples, getHealth } from "./api";
import { ChatInput } from "./components/ChatInput";
import { ExampleQuestions } from "./components/ExampleQuestions";
import { Header } from "./components/Header";
import { HistoryDrawer } from "./components/HistoryDrawer";
import { MessageBubble } from "./components/MessageBubble";
import type { Examples, Health } from "./types";
import { useChat } from "./useChat";
import { useTheme } from "./useTheme";

export default function App() {
  const { current, history, busy, send, startNew, open, remove } = useChat();
  const { theme, toggle } = useTheme();
  const [historyOpen, setHistoryOpen] = useState(false);
  const [examples, setExamples] = useState<Examples>({});
  const [health, setHealth] = useState<Health | null | undefined>(undefined);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void getHealth().then(setHealth);
    void getExamples()
      .then(setExamples)
      .catch(() => setExamples({}));
  }, []);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [current.messages]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setHistoryOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <HistoryDrawer
        open={historyOpen}
        conversations={history}
        currentId={current.id}
        onClose={() => setHistoryOpen(false)}
        onPick={open}
        onDelete={remove}
        onNew={startNew}
      />
      <Header
        health={health}
        theme={theme}
        onToggleTheme={toggle}
        onOpenHistory={() => setHistoryOpen(true)}
        onNewConversation={startNew}
      />

      <main className="scrollbar-soft flex-1 overflow-y-auto px-4 sm:px-6">
        {current.messages.length === 0 ? (
          <ExampleQuestions examples={examples} onPick={(q) => void send(q)} />
        ) : (
          <div className="mx-auto max-w-4xl space-y-5 py-6">
            {current.messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}
          </div>
        )}
        <div ref={bottom} />
      </main>

      <footer className="border-t border-brand-100/70 bg-white/70 px-4 py-3 backdrop-blur-md dark:border-brand-900/40 dark:bg-slate-950/70">
        <ChatInput disabled={busy} onSend={(q) => void send(q)} />
      </footer>
    </div>
  );
}
