import { useRef, useEffect, useState, KeyboardEvent } from "react";
import { dispatch } from "../commands/registry";
import { useStore } from "../state/storeSlice";
import "./CommandBar.css";

export default function CommandBar() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [value, setValue] = useState("");
  const [historyIndex, setHistoryIndex] = useState<number | null>(null);
  const status = useStore((s) => s.status);
  const history = useStore((s) => s.history);

  // The up/down arrow keys walk through previously-entered commands only
  // (not their output), so we filter down to input strings beginning with /.
  const historyInputs = history.map((e) => e.input);

  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  async function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      const input = value;
      if (!input.trim()) return;
      setValue("");
      setHistoryIndex(null);
      await dispatch(input);
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      if (historyInputs.length === 0) return;
      const next =
        historyIndex === null
          ? historyInputs.length - 1
          : Math.max(0, historyIndex - 1);
      setHistoryIndex(next);
      setValue(historyInputs[next]);
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (historyIndex === null) return;
      const next = historyIndex + 1;
      if (next >= historyInputs.length) {
        setHistoryIndex(null);
        setValue("");
      } else {
        setHistoryIndex(next);
        setValue(historyInputs[next]);
      }
      return;
    }
    if (e.key === "Escape") {
      setValue("");
      setHistoryIndex(null);
    }
  }

  return (
    <footer className="commandbar" data-status={status} role="contentinfo">
      <span className="commandbar-prompt" aria-hidden="true">
        /
      </span>
      <input
        ref={inputRef}
        className="commandbar-input"
        placeholder="Type a command — /connect /status /refresh /help  (⌘K)"
        aria-label="Command input"
        spellCheck={false}
        autoCapitalize="off"
        autoComplete="off"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={onKeyDown}
      />
      {status === "connecting" && <span className="commandbar-spinner" aria-hidden="true" />}
      <kbd className="commandbar-kbd">⌘K</kbd>
    </footer>
  );
}
