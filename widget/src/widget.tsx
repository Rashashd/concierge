import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import type { ReactElement } from "react";
import { createRoot } from "react-dom/client";

import { ChatMessage, fetchWidgetConfig, requestWidgetToken, sendChatMessage } from "./api";
import "./widget.css";

type UrlConfig = {
  apiBase: string;
  widgetId: string;
};

function readWidgetConfig(): UrlConfig {
  const params = new URLSearchParams(window.location.search);
  const apiBase = params.get("apiBase") ?? window.location.origin;
  const widgetId = params.get("widgetId") ?? "";

  return { apiBase, widgetId };
}

function createSessionId(): string {
  return createId("session");
}

function createId(prefix: string): string {
  if (window.crypto.randomUUID) {
    return window.crypto.randomUUID();
  }

  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function ConciergeWidget(): ReactElement {
  const config = useMemo(readWidgetConfig, []);
  const sessionId = useMemo(createSessionId, []);
  const tokenRef = useRef<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([
    { id: "welcome", role: "assistant", text: "Hi, how can I help you?" }
  ]);

  useEffect(() => {
    fetchWidgetConfig(config.apiBase, config.widgetId).then((wc) => {
      setMessages([{ id: "welcome", role: "assistant", text: wc.greeting }]);
      document.documentElement.style.setProperty("--widget-accent", wc.theme_color);
    });
  }, [config.apiBase, config.widgetId]);

  async function ensureToken(): Promise<string> {
    if (tokenRef.current) {
      return tokenRef.current;
    }

    tokenRef.current = await requestWidgetToken(
      config.apiBase,
      config.widgetId,
      sessionId
    );
    return tokenRef.current;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const nextMessage = input.trim();
    if (!nextMessage || isSending) {
      return;
    }

    setInput("");
    setError(null);
    setIsSending(true);
    setMessages((current) => [
      ...current,
      { id: createId("visitor"), role: "visitor", text: nextMessage }
    ]);

    try {
      const token = await ensureToken();
      const response = await sendChatMessage(
        config.apiBase,
        token,
        nextMessage,
        conversationId
      );
      setConversationId(response.conversation_id);
      setMessages((current) => [
        ...current,
        { id: createId("assistant"), role: "assistant", text: response.answer }
      ]);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Message failed to send."
      );
    } finally {
      setIsSending(false);
    }
  }

  return (
    <main className="concierge-shell">
      <header className="concierge-header">
        <div>
          <span className="concierge-status" />
          <p>Concierge</p>
        </div>
        <strong>Tenant-safe chat</strong>
      </header>

      <section className="concierge-thread" aria-live="polite">
        {messages.map((message) => (
          <article className={`message message-${message.role}`} key={message.id}>
            {message.text}
          </article>
        ))}
        {isSending ? (
          <article className="message message-assistant">...</article>
        ) : null}
      </section>

      {error ? <p className="concierge-error">{error}</p> : null}

      <form className="concierge-composer" onSubmit={handleSubmit}>
        <textarea
          aria-label="Message"
          disabled={isSending}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ask about services, hours, pricing..."
          rows={2}
          value={input}
        />
        <button disabled={isSending || !input.trim()} type="submit">
          Send
        </button>
      </form>
    </main>
  );
}

const root = document.getElementById("concierge-root");
if (root) {
  createRoot(root).render(<ConciergeWidget />);
}
