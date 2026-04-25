import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { dispatch } from "../commands/registry";
import type { CommandDef } from "../commands/registry";
import { matchCommands } from "../commands/match";
import CommandAutocomplete from "../commands/CommandAutocomplete";
import { useStore } from "../state/storeSlice";
import { useUI } from "../state/uiSlice";
import "./CommandBar.css";

export default function CommandBar() {
  const inputRef = useRef<HTMLInputElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [value, setValue] = useState("");
  const [historyIndex, setHistoryIndex] = useState<number | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [autocompleteOpen, setAutocompleteOpen] = useState(true);
  const status = useStore((s) => s.status);
  const history = useStore((s) => s.history);
  const openHelp = useUI((s) => s.openHelp);

  const historyInputs = history.map((e) => e.input);

  // Compute matches from current input. The dropdown only shows when:
  // - input starts with "/"
  // - the user hasn't typed past a space (i.e., they're still picking
  //   a command, not filling args)
  // - there's at least one match
  // - autocompleteOpen is true (Esc collapses it without clearing input)
  const matches: CommandDef[] = useMemo(() => matchCommands(value), [value]);
  const showAutocomplete = autocompleteOpen && matches.length > 0;

  // Reset the active index whenever the match set shrinks past it.
  useEffect(() => {
    if (activeIndex >= matches.length) setActiveIndex(0);
  }, [matches.length, activeIndex]);

  // Re-open the dropdown whenever the input changes (after the user
  // dismissed it with Esc, typing should bring it back).
  function setInput(next: string) {
    setValue(next);
    setHistoryIndex(null);
    setAutocompleteOpen(true);
    setActiveIndex(0);
  }

  // Click outside the command bar dismisses the dropdown without
  // touching the input value.
  useEffect(() => {
    if (!showAutocomplete) return;
    const onClick = (e: MouseEvent) => {
      if (
        wrapperRef.current &&
        !wrapperRef.current.contains(e.target as Node)
      ) {
        setAutocompleteOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [showAutocomplete]);

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

  function pickMatch(def: CommandDef) {
    setValue(`/${def.name} `);
    setAutocompleteOpen(false);
    setActiveIndex(0);
    inputRef.current?.focus();
  }

  async function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    // Autocomplete owns arrows + Tab + Enter when open and not
    // navigating history.
    if (showAutocomplete) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((i) => (i + 1) % matches.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((i) => (i - 1 + matches.length) % matches.length);
        return;
      }
      if (e.key === "Tab") {
        e.preventDefault();
        const def = matches[activeIndex];
        if (def) pickMatch(def);
        return;
      }
      if (e.key === "Enter" && matches[activeIndex]?.name === inputCommandName(value)) {
        // Exact name match — let Enter through to the dispatch path
        // below, so it actually runs the command.
      } else if (e.key === "Enter" && value.trim().length > 1) {
        // Enter on a partial input completes to the highlighted command
        // first; user presses Enter again to run.
        e.preventDefault();
        const def = matches[activeIndex];
        if (def) pickMatch(def);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setAutocompleteOpen(false);
        return;
      }
    }

    if (e.key === "Enter") {
      const input = value;
      if (!input.trim()) return;
      setValue("");
      setHistoryIndex(null);
      setAutocompleteOpen(true);
      setActiveIndex(0);
      await dispatch(input);
      return;
    }

    // Arrow up/down without an open autocomplete = walk command history
    // (the original Phase-2 behavior).
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
      setAutocompleteOpen(false);
    }
  }

  return (
    <footer
      ref={wrapperRef}
      className="commandbar"
      data-status={status}
      role="contentinfo"
    >
      {showAutocomplete && (
        <CommandAutocomplete
          matches={matches}
          activeIndex={activeIndex}
          onPick={pickMatch}
          onHover={setActiveIndex}
        />
      )}
      <div className="commandbar-pill" data-focus={value.startsWith("/") ? "command" : "ask"}>
        <input
          ref={inputRef}
          className="commandbar-input"
          placeholder="Type a command (try /help) or ask a question…"
          aria-label="Command input"
          spellCheck={false}
          autoCapitalize="off"
          autoComplete="off"
          value={value}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
        />
        {status === "connecting" && <span className="commandbar-spinner" aria-hidden="true" />}
        <button
          type="button"
          className="commandbar-help"
          onClick={openHelp}
          aria-label="Open command reference"
          title="Command reference (/help)"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="12" cy="12" r="10" />
            <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
        </button>
        <kbd className="commandbar-kbd">⌘K</kbd>
      </div>
    </footer>
  );
}

function inputCommandName(input: string): string | null {
  if (!input.startsWith("/")) return null;
  const tail = input.slice(1).split(/\s+/)[0];
  return tail || null;
}
