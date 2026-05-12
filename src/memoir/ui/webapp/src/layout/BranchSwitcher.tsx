import { useEffect, useRef, useState } from "react";
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
  const [switching, setSwitching] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  if (!open) return null;

  const sorted = [...branches].sort((a, b) => {
    if (a === currentBranch) return -1;
    if (b === currentBranch) return 1;
    return a.localeCompare(b);
  });

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

  return (
    <div
      ref={popoverRef}
      className="branch-switcher"
      role="listbox"
      aria-label="Switch branch"
    >
      <div className="branch-switcher-header">Switch branch</div>
      <ul className="branch-switcher-list">
        {sorted.length === 0 && (
          <li className="branch-switcher-empty">No branches</li>
        )}
        {sorted.map((branch) => {
          const isCurrent = branch === currentBranch;
          const isMain = branch === "main";
          const isCodeMatch = codeRepoBranch != null && branch === codeRepoBranch;
          const classes = [
            "branch-switcher-row",
            isCurrent && "current",
            !isCurrent && isMain && "highlight-main",
            !isCurrent && isCodeMatch && "highlight-code",
          ]
            .filter(Boolean)
            .join(" ");
          return (
            <li
              key={branch}
              role="option"
              aria-selected={isCurrent}
              aria-disabled={switching || isCurrent}
              className={classes}
              onMouseDown={(e) => {
                e.preventDefault();
                void handlePick(branch);
              }}
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
