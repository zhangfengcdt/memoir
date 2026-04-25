import { useEffect, useRef } from "react";
import { tagLabel, type CommandDef, type CommandTag } from "./registry";
import "./CommandAutocomplete.css";

interface AutocompleteProps {
  matches: CommandDef[];
  activeIndex: number;
  onPick: (def: CommandDef) => void;
  onHover: (index: number) => void;
}

/**
 * Vertical card list shown above the command bar input. Mirrors v1's
 * popup look: each row gets a usage label, tag pills, and a summary.
 */
export default function CommandAutocomplete({
  matches,
  activeIndex,
  onPick,
  onHover,
}: AutocompleteProps) {
  const listRef = useRef<HTMLUListElement | null>(null);

  // Keep the active row scrolled into view when the user arrows past
  // the visible window.
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const active = list.querySelector<HTMLLIElement>(
      `li[data-index="${activeIndex}"]`,
    );
    active?.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  if (matches.length === 0) return null;

  return (
    <div
      className="autocomplete"
      role="listbox"
      aria-label="Command suggestions"
    >
      <ul ref={listRef} className="autocomplete-list">
        {matches.map((def, i) => (
          <li
            key={def.name}
            data-index={i}
            role="option"
            aria-selected={i === activeIndex}
            className={`autocomplete-row${i === activeIndex ? " active" : ""}`}
            onMouseEnter={() => onHover(i)}
            onMouseDown={(e) => {
              // ``mousedown`` so the row triggers before the input
              // ``blur``-on-focus-loss closes the dropdown.
              e.preventDefault();
              onPick(def);
            }}
          >
            <div className="autocomplete-head">
              <code className="autocomplete-usage">{def.usage}</code>
              {def.tags.length > 0 && (
                <span className="autocomplete-tags">
                  {def.tags.map((t) => (
                    <TagPill key={t} tag={t} />
                  ))}
                </span>
              )}
            </div>
            <p className="autocomplete-summary">{def.summary}</p>
            {def.aliases.length > 0 && (
              <p className="autocomplete-aliases">
                Aliases:{" "}
                {def.aliases.map((a, j) => (
                  <span key={a}>
                    <code>/{a}</code>
                    {j < def.aliases.length - 1 && ", "}
                  </span>
                ))}
              </p>
            )}
          </li>
        ))}
      </ul>
      <footer className="autocomplete-footer">
        <span>
          <kbd>↑</kbd>
          <kbd>↓</kbd> nav
        </span>
        <span>
          <kbd>Tab</kbd> complete
        </span>
        <span>
          <kbd>Enter</kbd> run
        </span>
        <span>
          <kbd>Esc</kbd> dismiss
        </span>
      </footer>
    </div>
  );
}

function TagPill({ tag }: { tag: CommandTag }) {
  return (
    <span className={`autocomplete-tag tag-${tag}`}>{tagLabel(tag)}</span>
  );
}
