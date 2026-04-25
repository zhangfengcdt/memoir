import { useEffect, useRef } from "react";
import { useStore } from "../state/storeSlice";
import "./LiveAnnouncer.css";

/**
 * Visually-hidden ``aria-live="polite"`` region that announces the
 * latest command output to screen readers. Without this, slash-command
 * users have no audible feedback that a command ran (the visual log
 * scrolls below the fold for sighted users; for screen readers it's
 * silent).
 *
 * We mirror the most recent ``HistoryEntry`` rather than its full
 * content — assistive tech reads from a polite live region only when
 * its text actually changes, so empty announcements do nothing.
 */
export default function LiveAnnouncer() {
  const lastEntry = useStore((s) => s.history[s.history.length - 1]);
  const announcedId = useRef<number | null>(null);

  useEffect(() => {
    if (lastEntry && lastEntry.id !== announcedId.current) {
      announcedId.current = lastEntry.id;
    }
  }, [lastEntry]);

  if (!lastEntry) return null;

  // Compose a one-line announcement: "<input>: <first line>".
  // Keep it short so screen readers can be interrupted easily.
  const summary = `${lastEntry.input}: ${lastEntry.lines[0] ?? ""}`;

  return (
    <div className="visually-hidden" role="status" aria-live="polite" aria-atomic="true">
      {summary}
    </div>
  );
}
