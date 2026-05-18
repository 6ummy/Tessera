"use client";
import { useEffect, useRef, useState } from "react";
import { ArrowUp, Sparkles } from "lucide-react";
import type { Persona } from "@/lib/mock/personas";
import { ACCENT_CLASS } from "@/lib/mock/personas";
import { respond, STARTERS, type ChatMessage } from "@/lib/mock/chat";
import { PersonaAvatar } from "./persona-avatar";
import { cn } from "@/lib/utils";

const TYPING_DELAY_MS = 600;
const STREAM_CHAR_MS = 8;

export function AnalystChat({ persona }: { persona: Persona }) {
  const a = ACCENT_CLASS[persona.accent];
  const starter = STARTERS[persona.id];

  const [messages, setMessages] = useState<ChatMessage[]>([
    { id: "greet", role: "analyst", content: starter.greeting, ts: Date.now() },
  ]);
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const [streamingId, setStreamingId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, typing]);

  const send = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || typing) return;
    const userMsg: ChatMessage = { id: `u-${Date.now()}`, role: "user", content: trimmed, ts: Date.now() };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setTyping(true);

    setTimeout(() => {
      const fullReply = respond(persona.id, trimmed);
      const id = `a-${Date.now()}`;
      setMessages((m) => [...m, { id, role: "analyst", content: "", ts: Date.now() }]);
      setStreamingId(id);
      setTyping(false);

      // Character-by-character stream
      let i = 0;
      const tick = () => {
        i += Math.max(1, Math.floor(fullReply.length / 80));
        const slice = fullReply.slice(0, Math.min(i, fullReply.length));
        setMessages((m) => m.map((msg) => (msg.id === id ? { ...msg, content: slice } : msg)));
        if (i < fullReply.length) {
          setTimeout(tick, STREAM_CHAR_MS);
        } else {
          setStreamingId(null);
        }
      };
      setTimeout(tick, STREAM_CHAR_MS);
    }, TYPING_DELAY_MS);
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
            <Message key={m.id} msg={m} persona={persona} streaming={streamingId === m.id} />
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
                    a.text
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
              placeholder={`Message ${persona.name}…`}
              className="num min-h-[24px] flex-1 resize-none bg-transparent text-[14px] leading-relaxed text-ink-900 placeholder:text-ink-400 focus:outline-none"
              style={{ fontFamily: "var(--font-sans)" }}
            />
            <button
              onClick={() => send(input)}
              disabled={!input.trim() || typing}
              aria-label="Send"
              className={cn(
                "grid h-8 w-8 shrink-0 place-items-center rounded-full transition-colors",
                input.trim() && !typing
                  ? "bg-ink-900 text-cream-50 hover:bg-ink-800"
                  : "bg-ink-900/[0.06] text-ink-400"
              )}
            >
              <ArrowUp className="h-4 w-4" />
            </button>
          </div>
          <p className="mt-2 text-center text-[11px] text-ink-400">
            Demo · responses are mock-generated from {persona.name}'s philosophy and reports. No LLM calls.
          </p>
        </div>
      </div>
    </div>
  );
}

function Message({ msg, persona, streaming }: { msg: ChatMessage; persona: Persona; streaming: boolean }) {
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
        <div className={cn("mb-1 text-[10px] uppercase tracking-[0.16em]", a.text)}>{persona.name}</div>
        <div className="whitespace-pre-wrap text-[14px] leading-relaxed text-ink-800">
          {msg.content}
          {streaming && <span className="ml-0.5 inline-block h-3.5 w-[2px] translate-y-0.5 animate-pulse bg-ink-700" />}
        </div>
      </div>
    </div>
  );
}

function Dots() {
  return (
    <div className="flex items-center gap-1">
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-ink-400" style={{ animationDelay: "0ms" }} />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-ink-400" style={{ animationDelay: "150ms" }} />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-ink-400" style={{ animationDelay: "300ms" }} />
    </div>
  );
}
