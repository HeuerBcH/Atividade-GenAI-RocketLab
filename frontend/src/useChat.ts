import { useEffect, useState } from "react";
import { ask, resetSession } from "./api";
import type { ChatMessage, Conversation } from "./types";

const STORAGE_KEY = "cinedata.conversations";
const MAX_CONVERSATIONS = 30;

interface Store {
  currentId: string;
  conversations: Conversation[];
}

function newConversation(): Conversation {
  return { id: crypto.randomUUID().replaceAll("-", ""), title: "Nova conversa", createdAt: Date.now(), messages: [] };
}

function load(): Store {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      const store = JSON.parse(saved) as Store;
      // respostas que estavam carregando quando a página fechou não voltam mais
      const conversations = store.conversations.map((c) => ({
        ...c,
        messages: c.messages.filter((m) => !(m.role === "assistant" && m.status === "loading")),
      }));
      if (conversations.some((c) => c.id === store.currentId)) return { ...store, conversations };
    }
  } catch {
    // localStorage indisponível ou corrompido: começa do zero
  }
  const first = newConversation();
  return { currentId: first.id, conversations: [first] };
}

export function useChat() {
  const [store, setStore] = useState<Store>(load);
  const current = store.conversations.find((c) => c.id === store.currentId)!;
  const busy = current.messages.some((m) => m.role === "assistant" && m.status === "loading");

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
    } catch {
      // sem persistência, o chat continua funcionando
    }
  }, [store]);

  function updateConversation(id: string, change: (c: Conversation) => Conversation) {
    setStore((s) => ({ ...s, conversations: s.conversations.map((c) => (c.id === id ? change(c) : c)) }));
  }

  async function send(question: string) {
    const text = question.trim();
    if (!text || busy) return;
    const conversationId = current.id;
    const answerId = crypto.randomUUID();
    updateConversation(conversationId, (c) => ({
      ...c,
      title: c.messages.length === 0 ? text.slice(0, 60) : c.title,
      messages: [
        ...c.messages,
        { id: crypto.randomUUID(), role: "user", content: text },
        { id: answerId, role: "assistant", status: "loading" },
      ],
    }));

    let result: ChatMessage;
    try {
      const response = await ask(text, conversationId);
      result = { id: answerId, role: "assistant", status: "done", response };
    } catch (err) {
      const error = err instanceof Error ? err.message : "Erro inesperado.";
      result = { id: answerId, role: "assistant", status: "error", error };
    }
    updateConversation(conversationId, (c) => ({
      ...c,
      messages: c.messages.map((m) => (m.id === answerId ? result : m)),
    }));
  }

  function startNew() {
    if (current.messages.length === 0) return;
    const fresh = newConversation();
    setStore((s) => ({
      currentId: fresh.id,
      conversations: [fresh, ...s.conversations].slice(0, MAX_CONVERSATIONS),
    }));
  }

  function open(id: string) {
    setStore((s) => ({ ...s, currentId: id }));
  }

  function remove(id: string) {
    void resetSession(id);
    setStore((s) => {
      const rest = s.conversations.filter((c) => c.id !== id);
      if (rest.length === 0) {
        const fresh = newConversation();
        return { currentId: fresh.id, conversations: [fresh] };
      }
      return { currentId: s.currentId === id ? rest[0].id : s.currentId, conversations: rest };
    });
  }

  const history = store.conversations.filter((c) => c.messages.length > 0);
  return { current, history, busy, send, startNew, open, remove };
}
