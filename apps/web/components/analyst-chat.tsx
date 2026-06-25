"use client";
import { useEffect, useRef, useState } from "react";
import { ArrowUp, Sparkles } from "lucide-react";
import type { Persona } from "@/lib/mock/personas";
import { ACCENT_CLASS } from "@/lib/mock/personas";
import { STARTERS, type ChatMessage } from "@/lib/chat-starters";
import {
  ChatStreamError,
  streamChat,
  type ChatStreamMessage,
} from "@/lib/chat-stream";
import { PersonaAvatar } from "./persona-avatar";
import { cn } from "@/lib/utils";

const HISTORY_TURNS = 10; // last N messages sent back as conversation context

export function AnalystChat({ persona }: { persona: Persona }) {
  const a = ACCENT_CLASS[persona.accent];
  // Fall back to a generic opener so a persona missing from STARTERS can never
  // crash the chat (a 4-entry map once threw on Michael's id).
  const starter = STARTERS[persona.id] ?? {
    greeting: `Hi, I'm ${persona.name}. Ask me anything about my book or how I think about the market.`,
    suggestions: [],
  };

  const [messages, setMessages] = useState<ChatMessage[]>([
    { id: "greet", role: "analyst", content: starter.greeting, ts: Date.now() },
  ]);
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const [streamingId, setStreamingId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, typing]);

  // Cancel any in-flight stream when the component unmounts or persona switches
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, [persona.id]);

  const send = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || typing || streamingId) return;

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      content: trimmed,
      ts: Date.now(),
    };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setTyping(true);

    // Conversation history sent to the model — last N turns, greeting
    // excluded (it's a UI flourish, not analyst output).
    const history: ChatStreamMessage[] = messages
      .filter((m) => m.id !== "greet")
      .slice(-HISTORY_TURNS)
      .map((m) => ({
        role: m.role === "analyst" ? "assistant" : "user",
        content: m.content,
      }));

    const assistantId = `a-${Date.now()}`;
    setMessages((m) => [
      ...m,
      { id: assistantId, role: "analyst", content: "", ts: Date.now() },
    ]);
    setStreamingId(assistantId);
    setTyping(false);

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    // ─── Typewriter pump ────────────────────────────────────────────────
    // The SSE stream from Anthropic arrives in chunks of 50–200 chars,
    // sometimes with multi-second pauses between bursts (server-side
    // batching + network buffering). Rendering each chunk directly
    // makes the message lurch. Instead, push every delta into a
    // string buffer and let a 16 ms tick drain the buffer at an
    // adaptive rate: ≥2 chars per frame baseline, faster when the
    // backlog grows (cap at 50/frame to never stall behind the model).
    // The visual feels continuous; if the model actually pauses, the
    // pump runs out and the cursor sits — which reads as "thinking".
    let buffer = "";
    let streamDone = false;
    const pumpId = window.setInterval(() => {
      if (ctrl.signal.aborted) {
        window.clearInterval(pumpId);
        setStreamingId((id) => (id === assistantId ? null : id));
        return;
      }
      if (buffer.length === 0) {
        if (streamDone) {
          // Pump caught up; clear the blinking cursor at the same moment
          // the last char rendered, so the visual matches the data.
          window.clearInterval(pumpId);
          setStreamingId((id) => (id === assistantId ? null : id));
        }
        return;
      }
      const burst = Math.min(50, Math.max(2, Math.ceil(buffer.length / 30)));
      const chunk = buffer.slice(0, burst);
      buffer = buffer.slice(burst);
      setMessages((m) =>
        m.map((msg) =>
          msg.id === assistantId
            ? { ...msg, content: msg.content + chunk }
            : msg,
        ),
      );
    }, 16);

    try {
      for await (const delta of streamChat(
        persona.id,
        trimmed,
        history,
        ctrl.signal,
      )) {
        buffer += delta;
      }
    } catch (err) {
      buffer += formatStreamError(err, persona.name);
    } finally {
      streamDone = true;
      // streamingId cleared by pump when buffer drains — keeps the
      // blinking cursor on screen until the visible text catches up.
      if (abortRef.current === ctrl) abortRef.current = null;
    }
  };

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  };

  return (
    <div className="flex h-full flex-col">
      {/* Conversation */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6">
        <div className="mx-auto max-w-2xl space-y-5">
          {messages.map((m) => (
            <Message
              key={m.id}
              msg={m}
              persona={persona}
              streaming={streamingId === m.id}
            />
          ))}
          {typing && (
            <div className="flex items-end gap-3">
              <PersonaAvatar persona={persona} size="sm" />
              <div className="rounded-2xl rounded-tl-md border border-ink-900/[0.06] bg-cream-50 px-4 py-3">
                <Dots />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Suggestions (only when conversation is fresh) */}
      {messages.length === 1 && (
        <div className="border-t border-ink-900/[0.06] bg-cream-100/40 px-6 py-4">
          <div className="mx-auto max-w-2xl">
            <div className="mb-2 flex items-center gap-1.5 text-[10px] uppercase tracking-[0.16em] text-ink-500">
              <Sparkles className="h-3 w-3" /> Try asking
            </div>
            <div className="flex flex-wrap gap-2">
              {starter.suggestions.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className={cn(
                    "rounded-full border border-ink-900/10 bg-cream-50 px-3 py-1.5 text-xs text-ink-700 transition-all hover:border-ink-900/20 hover:bg-ink-900/[0.04]",
                    a.text,
                  )}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Input bar */}
      <div className="border-t border-ink-900/[0.06] bg-cream-50/95 px-6 py-4 backdrop-blur">
        <div className="mx-auto max-w-2xl">
          <div className="flex items-end gap-2 rounded-2xl border border-ink-900/[0.08] bg-cream-50 px-4 py-2.5 shadow-[0_2px_12px_-6px_rgba(31,30,27,0.08)] focus-within:border-ink-900/[0.18]">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKey}
              rows={1}
              placeholder={
                streamingId ? `${persona.name} is typing…` : `Message ${persona.name}…`
              }
              disabled={!!streamingId}
              className="num min-h-[24px] flex-1 resize-none bg-transparent text-[14px] leading-relaxed text-ink-900 placeholder:text-ink-400 focus:outline-none disabled:opacity-60"
              style={{ fontFamily: "var(--font-sans)" }}
            />
            <button
              onClick={() => send(input)}
              disabled={!input.trim() || typing || !!streamingId}
              aria-label="Send"
              className={cn(
                "grid h-8 w-8 shrink-0 place-items-center rounded-full transition-colors",
                input.trim() && !typing && !streamingId
                  ? "bg-ink-900 text-cream-50 hover:bg-ink-800"
                  : "bg-ink-900/[0.06] text-ink-400",
              )}
            >
              <ArrowUp className="h-4 w-4" />
            </button>
          </div>
          <p className="mt-2 text-center text-[11px] text-ink-400">
            Powered by Sonnet 4.6 in {persona.name}'s voice · not financial advice
          </p>
        </div>
      </div>
    </div>
  );
}

function formatStreamError(err: unknown, personaName: string): string {
  if (err instanceof ChatStreamError) {
    if (err.code === "aborted") return "";
    if (err.code === "network") {
      return `\n\n_[연결이 끊겼어요. 다시 시도해 주세요.]_`;
    }
    if (err.code === "http" && err.status === 503) {
      return `\n\n_[채팅 서버가 아직 연결되지 않았습니다. 잠시 후 다시 시도해주세요.]_`;
    }
    if (err.message.includes("chat_disabled")) {
      return `\n\n_[Chat is disabled on this environment (FEATURE_REAL_LLM=false).]_`;
    }
    if (err.message.includes("budget_exceeded")) {
      return `\n\n_[Daily LLM budget reached — ${personaName} is offline until tomorrow.]_`;
    }
    return `\n\n_[Error: ${err.message}]_`;
  }
  return `\n\n_[Unexpected error: ${err instanceof Error ? err.message : String(err)}]_`;
}

function Message({
  msg,
  persona,
  streaming,
}: {
  msg: ChatMessage;
  persona: Persona;
  streaming: boolean;
}) {
  const a = ACCENT_CLASS[persona.accent];
  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-tr-md bg-ink-900 px-4 py-2.5 text-[14px] leading-relaxed text-cream-50">
          {msg.content}
        </div>
      </div>
    );
  }
  return (
    <div className="flex items-start gap-3">
      <PersonaAvatar persona={persona} size="sm" />
      <div className="max-w-[80%] rounded-2xl rounded-tl-md border border-ink-900/[0.06] bg-cream-50 px-4 py-3">
        <div
          className={cn(
            "mb-1 text-[10px] uppercase tracking-[0.16em]",
            a.text,
          )}
        >
          {persona.name}
        </div>
        <div className="whitespace-pre-wrap text-[14px] leading-relaxed text-ink-800">
          {msg.content}
          {streaming && (
            <span className="ml-0.5 inline-block h-3.5 w-[2px] translate-y-0.5 animate-pulse bg-ink-700" />
          )}
        </div>
      </div>
    </div>
  );
}

function Dots() {
  return (
    <div className="flex items-center gap-1">
      <span
        className="h-1.5 w-1.5 animate-bounce rounded-full bg-ink-400"
        style={{ animationDelay: "0ms" }}
      />
      <span
        className="h-1.5 w-1.5 animate-bounce rounded-full bg-ink-400"
        style={{ animationDelay: "150ms" }}
      />
      <span
        className="h-1.5 w-1.5 animate-bounce rounded-full bg-ink-400"
        style={{ animationDelay: "300ms" }}
      />
    </div>
  );
}
