// Browser-side SSE consumer for /api/chat/[personaId].
//
// Why fetch + reader rather than EventSource:
//   - EventSource is GET-only; our chat backend takes a POST body
//     (`message` + `history`).
//   - Fetch + ReadableStream is the standard pattern for POST SSE.
//
// The server frames each token as `data: <text>\n\n`. The final frame is
// `data: [DONE]\n\n`. Worker escapes literal newlines inside a delta as
// `\\n` so a single message can't accidentally split into two SSE events;
// we un-escape on consumption.

export type ChatStreamMessage = {
  role: "user" | "assistant";
  content: string;
};

export class ChatStreamError extends Error {
  constructor(
    message: string,
    public readonly code:
      | "http"
      | "stream_error"
      | "aborted"
      | "network" = "stream_error",
    public readonly status?: number,
  ) {
    super(message);
    this.name = "ChatStreamError";
  }
}

/**
 * Stream chat tokens for one user message.
 *
 * Usage:
 *   for await (const delta of streamChat("warren", "AAPL?", history)) {
 *     append(delta);
 *   }
 */
export async function* streamChat(
  personaId: string,
  message: string,
  history: ChatStreamMessage[],
  signal?: AbortSignal,
): AsyncGenerator<string, void, unknown> {
  let resp: Response;
  try {
    resp = await fetch(`/api/chat/${personaId}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ message, history }),
      signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      throw new ChatStreamError("stream aborted", "aborted");
    }
    throw new ChatStreamError(
      err instanceof Error ? err.message : String(err),
      "network",
    );
  }

  if (!resp.ok || !resp.body) {
    const text = await resp.text().catch(() => "");
    throw new ChatStreamError(
      `chat ${resp.status}: ${text || "no body"}`,
      "http",
      resp.status,
    );
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });

      // SSE events end at `\n\n`. Keep any partial event in `buf`.
      const events = buf.split("\n\n");
      buf = events.pop() ?? "";

      for (const evt of events) {
        if (!evt.trim()) continue;
        let eventType = "message";
        const data: string[] = [];
        for (const line of evt.split("\n")) {
          if (line.startsWith("event:")) eventType = line.slice(6).trim();
          else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
        }
        const text = data.join("\n");
        if (eventType === "error") {
          throw new ChatStreamError(`stream error: ${text}`, "stream_error");
        }
        if (text === "[DONE]") return;
        // Worker escaped real newlines inside a delta as \n.
        // Restore them so prose renders correctly.
        yield text.replace(/\\n/g, "\n");
      }
    }
  } finally {
    reader.releaseLock();
  }
}
