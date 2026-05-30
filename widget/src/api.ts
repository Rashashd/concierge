export type WidgetConfig = {
  widget_id: string;
  greeting: string;
  theme_color: string;
};

export async function fetchWidgetConfig(
  apiBase: string,
  widgetId: string
): Promise<WidgetConfig> {
  try {
    const response = await fetch(`${apiBase}/widget/config?widget_id=${widgetId}`);
    if (!response.ok) throw new Error("config fetch failed");
    return (await response.json()) as WidgetConfig;
  } catch {
    return { widget_id: widgetId, greeting: "Hi, how can I help you?", theme_color: "#0066CC" };
  }
}

export type ChatMessage = {
  id: string;
  role: "assistant" | "visitor";
  text: string;
};

type WidgetTokenResponse = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
};

type ChatResponse = {
  answer: string;
  conversation_id: string | null;
};

export async function requestWidgetToken(
  apiBase: string,
  widgetId: string,
  sessionId: string
): Promise<string> {
  const response = await fetch(`${apiBase}/widget/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ widget_id: widgetId, session_id: sessionId })
  });

  if (!response.ok) {
    throw new Error(`Token request failed with ${response.status}`);
  }

  const payload = (await response.json()) as WidgetTokenResponse;
  return payload.access_token;
}

export async function sendChatMessage(
  apiBase: string,
  token: string,
  message: string,
  conversationId: string | null
): Promise<ChatResponse> {
  const response = await fetch(`${apiBase}/chat`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      message,
      conversation_id: conversationId
    })
  });

  if (!response.ok) {
    throw new Error(`Chat request failed with ${response.status}`);
  }

  return (await response.json()) as ChatResponse;
}
