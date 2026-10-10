"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowUp, Loader2 } from "lucide-react";
import { useWorkspace } from "./WorkspaceProvider";
import { cn } from "@/lib/utils";

/** Glass prompt: Enter sends, Shift+Enter inserts a newline, "/" focuses it from anywhere. */
export function PromptBar({ large = false, autoFocus = false }: { large?: boolean; autoFocus?: boolean }) {
  const { send, busy, meta, ready } = useWorkspace();
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  const max = meta?.max_message_chars ?? 800;

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 176)}px`;
  }, [value]);

  useEffect(() => {
    if (autoFocus) ref.current?.focus();
  }, [autoFocus, ready]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const typing = t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable);
      if (e.key === "/" && !typing && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        ref.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const submit = async () => {
    const text = value.trim();
    if (!text || busy || text.length > max) return;
    setValue("");
    await send(text);
    ref.current?.focus();
  };

  const over = value.length > max;
  const canSend = value.trim().length > 0 && !busy && !over;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
      className="group/prompt relative"
      data-tour="prompt"
    >
      <div
        className={cn(
          "glass glass-strong relative flex items-end gap-2 overflow-hidden rounded-[30px] transition-[box-shadow,border-color] duration-500",
          "focus-within:border-white/50 focus-within:shadow-[0_0_0_1px_rgba(255,255,255,0.35),0_0_60px_-10px_rgba(255,255,255,0.35)]",
          large ? "p-3 pl-6" : "p-2 pl-5",
        )}
      >
        <label htmlFor="prompt" className="sr-only">
          Describe what you want to watch
        </label>
        <textarea
          id="prompt"
          ref={ref}
          rows={1}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              void submit();
            }
          }}
          placeholder={large ? "Tell me what you're in the mood for…" : "Ask for anything — a mood, a genre, a movie you loved"}
          aria-describedby="prompt-hint"
          className={cn(
            "max-h-44 min-h-[28px] flex-1 resize-none bg-transparent leading-relaxed text-white placeholder:text-white/40 focus:outline-none",
            large ? "py-3 text-[19px]" : "py-2.5 text-[16px]",
          )}
        />
        <div className="flex items-center gap-2 pb-0.5">
          {value.length > max * 0.8 && (
            <span className={cn("font-mono text-[11px]", over ? "text-white" : "text-white/40")} aria-live="polite">
              {value.length}/{max}
            </span>
          )}
          <button
            type="submit"
            disabled={!canSend}
            aria-label={busy ? "Thinking" : "Send message"}
            className={cn(
              "press grid shrink-0 place-items-center rounded-full bg-white text-black disabled:bg-white/15 disabled:text-white/40",
              large ? "h-12 w-12" : "h-10 w-10",
            )}
          >
            {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <ArrowUp className="h-5 w-5" strokeWidth={2.4} />}
          </button>
        </div>
      </div>
      <p id="prompt-hint" className="mt-2.5 hidden text-center text-[12px] text-white/35 sm:block">
        <kbd className="rounded border border-white/15 px-1.5 font-mono text-[10px]">Enter</kbd> to send ·{" "}
        <kbd className="rounded border border-white/15 px-1.5 font-mono text-[10px]">Shift</kbd>+
        <kbd className="rounded border border-white/15 px-1.5 font-mono text-[10px]">Enter</kbd> for a new line ·{" "}
        <kbd className="rounded border border-white/15 px-1.5 font-mono text-[10px]">/</kbd> to focus
      </p>
    </form>
  );
}
