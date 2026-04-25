import { useRef, useEffect } from "react";
import "./CommandBar.css";

export default function CommandBar() {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <footer className="commandbar">
      <span className="commandbar-prompt" aria-hidden="true">
        /
      </span>
      <input
        ref={inputRef}
        className="commandbar-input"
        placeholder="Type a command — /connect /remember /recall …   (⌘K)"
        aria-label="Command input"
        spellCheck={false}
        autoCapitalize="off"
        autoComplete="off"
      />
      <kbd className="commandbar-kbd">⌘K</kbd>
    </footer>
  );
}
