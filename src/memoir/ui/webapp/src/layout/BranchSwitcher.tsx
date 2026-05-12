import { useEffect, useMemo, useRef, useState } from "react";
import { api, MemoirApiError } from "../api/client";
import { useStore } from "../state/storeSlice";
import "./BranchSwitcher.css";

interface BranchSwitcherProps {
  open: boolean;
  onClose: () => void;
  anchorRef: React.RefObject<HTMLElement | null>;
}

export default function BranchSwitcher({
  open,
  onClose,
  anchorRef,
}: BranchSwitcherProps) {
  const storePath = useStore((s) => s.storePath);
  const data = useStore((s) => s.data);
  const branches = data?.branches ?? [];
  const currentBranch = data?.current_branch ?? "";
  const codeRepoBranch = data?.code_repo_branch ?? null;

  const popoverRef = useRef<HTMLDivElement | null>(null);
  const listRef = useRef<HTMLUListElement | null>(null);
  const [switching, setSwitching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sorted = useMemo(() => {
    return [...branches].sort((a, b) => {
      if (a === currentBranch) return -1;
      if (b === currentBranch) return 1;
      return a.localeCompare(b);
    });
  }, [branches, currentBranch]);

  useEffect(() => {
    if (!open) {
      setError(null);
      setSwitching(false);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const onMouseDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (popoverRef.current?.contains(target)) return;
      if (anchorRef.current?.contains(target)) return;
      onClose();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onMouseDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onMouseDown);
    };
  }, [open, onClose, anchorRef]);

  // Auto-focus the first non-current row when the popover opens so
  // keyboard users can immediately activate or arrow through options.
  useEffect(() => {
    if (!open) return;
    const list = listRef.current;
    if (!list) return;
    const first = list.querySelector<HTMLLIElement>(
      'li[role="option"]:not([aria-disabled="true"])',
    );
    first?.focus();
  }, [open, sorted.length]);

  if (!open) return null;

  const handlePick = async (branch: string) => {
    if (!storePath || switching) return;
    if (branch === currentBranch) {
      onClose();
      return;
    }
    setError(null);
    setSwitching(true);
    try {
      await api.checkout(storePath, branch);
      await useStore.getState().refresh();
      onClose();
    } catch (err) {
      setError(err instanceof MemoirApiError ? err.message : String(err));
      setSwitching(false);
    }
  };

  // Focus a sibling option row by index, wrapping at both ends and
  // skipping disabled (current) rows.
  const focusRow = (index: number) => {
    const list = listRef.current;
    if (!list) return;
    const rows = Array.from(
      list.querySelectorAll<HTMLLIElement>(
        'li[role="option"]:not([aria-disabled="true"])',
      ),
    );
    if (rows.length === 0) return;
    const wrapped = ((index % rows.length) + rows.length) % rows.length;
    rows[wrapped]?.focus();
  };

  const handleKeyDown = (
    e: React.KeyboardEvent<HTMLLIElement>,
    branch: string,
    enabledIndex: number,
    enabledCount: number,
  ) => {
    switch (e.key) {
      case "Enter":
      case " ":
        e.preventDefault();
        void handlePick(branch);
        return;
      case "ArrowDown":
        e.preventDefault();
        focusRow(enabledIndex + 1);
        return;
      case "ArrowUp":
        e.preventDefault();
        focusRow(enabledIndex - 1);
        return;
      case "Home":
        e.preventDefault();
        focusRow(0);
        return;
      case "End":
        e.preventDefault();
        focusRow(enabledCount - 1);
        return;
    }
  };

  const enabledBranches = sorted.filter((b) => b !== currentBranch);
  const enabledIndexOf = (branch: string) => enabledBranches.indexOf(branch);

  return (
    <div
      ref={popoverRef}
      className="branch-switcher"
      role="listbox"
      aria-label="Switch branch"
    >
      <div className="branch-switcher-header">Switch branch</div>
      <ul ref={listRef} className="branch-switcher-list">
        {sorted.length === 0 && (
          <li className="branch-switcher-empty">No branches</li>
        )}
        {sorted.map((branch) => {
          const isCurrent = branch === currentBranch;
          const isMain = branch === "main";
          const isCodeMatch =
            codeRepoBranch != null && branch === codeRepoBranch;
          const classes = [
            "branch-switcher-row",
            isCurrent && "current",
            !isCurrent && isMain && "highlight-main",
            !isCurrent && isCodeMatch && "highlight-code",
          ]
            .filter(Boolean)
            .join(" ");
          const disabled = switching || isCurrent;
          return (
            <li
              key={branch}
              role="option"
              aria-selected={isCurrent}
              aria-disabled={disabled}
              tabIndex={disabled ? -1 : 0}
              className={classes}
              onMouseDown={(e) => {
                e.preventDefault();
                void handlePick(branch);
              }}
              onKeyDown={(e) =>
                handleKeyDown(
                  e,
                  branch,
                  enabledIndexOf(branch),
                  enabledBranches.length,
                )
              }
            >
              <span className="branch-switcher-bullet" aria-hidden="true">
                {isCurrent ? "●" : "○"}
              </span>
              <span className="branch-switcher-name">{branch}</span>
              <span className="branch-switcher-tags">
                {isCurrent && (
                  <span className="branch-switcher-tag tag-current">
                    current
                  </span>
                )}
                {!isCurrent && isMain && (
                  <span
                    className="branch-switcher-tag tag-main"
                    title="memoir default branch"
                  >
                    main
                  </span>
                )}
                {!isCurrent && isCodeMatch && (
                  <span
                    className="branch-switcher-tag tag-code"
                    title="matches checked-out code branch"
                  >
                    code
                  </span>
                )}
              </span>
            </li>
          );
        })}
      </ul>
      {error && (
        <p className="branch-switcher-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
