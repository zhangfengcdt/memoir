// Memoir UI runtime config, parsed once from URL query params.
//
// Set by the `memoir ui` CLI via ?readonly=0|1&usellm=0|1. When launched
// manually (e.g. `python -m memoir.ui.server`), both flags fall back to
// "false" so the UI stays fully interactive.
//
// The guard helpers here are UX gates only, not security — the HTTP API
// still accepts every request. Keep them lightweight so they can be called
// from every command dispatcher, button handler, and UI renderer.

(function () {
    const params = new URLSearchParams(window.location.search);
    const asBool = (v) => v === '1' || v === 'true';

    const config = {
        readonly: asBool(params.get('readonly')),
        useLlm: asBool(params.get('usellm')),
    };

    // Commands that change the connected store or mutate store data.
    // These are blocked when config.readonly is true. /refresh is the one
    // exception — it re-reads the store without writing.
    // Note: /checkout persists the current-branch pointer in the repo, so
    // it counts as a write even when switching to an already-existing branch.
    // /remember and /forget live under the LLM gate (below) instead of here —
    // they're the primary content authoring commands and should follow the
    // same enablement as /recall rather than be coupled to branch-write gating.
    const MUTATING_COMMANDS = new Set([
        '/connect', '/new', '/demo',
        '/branch',  // create/delete subcommands mutate
        '/checkout', '/merge', '/time-travel',
    ]);

    // Commands that require calling an LLM.
    const LLM_COMMANDS = new Set([
        '/recall', '/search', '/summarize',
        '/remember',  // classification step
        '/forget',    // grouped with /remember for consistent authoring gate
    ]);

    // Return block info for a command, or null if it's allowed.
    // Callers use this for both runtime gating and visual styling of the
    // command list in the autocomplete and Command Reference modal.
    function isCommandBlocked(cmd) {
        if (config.readonly && MUTATING_COMMANDS.has(cmd)) {
            return {
                reason: 'readonly',
                label: 'READONLY',
                message: `${cmd} is disabled — UI is in readonly mode. `
                    + `Relaunch with 'memoir ui <path> --no-readonly' to allow writes.`,
            };
        }
        if (!config.useLlm && LLM_COMMANDS.has(cmd)) {
            return {
                reason: 'llm',
                label: 'NO LLM',
                message: `${cmd} needs an LLM — relaunch with `
                    + `'memoir ui <path> --usellm' to enable.`,
            };
        }
        return null;
    }

    function guardCommand(cmd) {
        const block = isCommandBlocked(cmd);
        if (block) {
            notify(block.message);
            return false;
        }
        return true;
    }

    function notify(msg) {
        if (typeof showNotification === 'function') {
            showNotification(msg, 'warning');
        } else {
            console.warn('[memoir]', msg);
        }
    }

    // Helper for inline onclick handlers that need to notify about a blocked
    // command. Keeps the message in a data-block-msg attribute so we don't
    // have to escape arbitrary strings into the onclick attribute itself.
    function notifyFromData(el) {
        notify(el && el.dataset && el.dataset.blockMsg
            ? el.dataset.blockMsg
            : 'This action is disabled.');
    }

    // Escape a string for safe use as an HTML attribute value (inside double
    // quotes). Also escapes `<`/`>` so tooltips containing things like
    // "<path>" render correctly in every browser.
    function escapeAttr(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    // Disable DOM controls that correspond to blocked capabilities. Called
    // from initializePage() once the page has rendered.
    function applyDomGuards() {
        const disable = (id, title) => {
            const el = document.getElementById(id);
            if (!el) return;
            el.disabled = true;
            el.classList.add('memoir-disabled');
            el.setAttribute('aria-disabled', 'true');
            el.title = title;
            el.style.opacity = '0.4';
            el.style.cursor = 'not-allowed';
            // Swallow clicks in the capture phase so existing listeners never
            // see them. We only block when the flag is on, so this is safe.
            el.addEventListener('click', (e) => {
                e.stopPropagation();
                e.preventDefault();
                notify(title);
            }, true);
        };

        const hide = (id) => {
            const el = document.getElementById(id);
            if (!el) return;
            el.style.display = 'none';
            el.setAttribute('aria-hidden', 'true');
        };

        const attachBranchListPopover = (id) => {
            const el = document.getElementById(id);
            if (!el) return;
            ensureBranchPopoverStyles();
            let popover = null;
            let showTimer = null;

            const show = () => {
                if (popover) return;
                // Read current branch list straight off the (disabled)
                // <select>'s options so we stay in sync automatically with
                // updateBranchesDropdown() — no extra fetch needed.
                const options = Array.from(el.options || []);
                if (options.length === 0) return;
                const current = el.value;
                const lines = options.map(o => {
                    const mark = o.value === current ? '●' : '○';
                    const cls  = o.value === current ? 'mbp-row mbp-current' : 'mbp-row';
                    return `<div class="${cls}"><span class="mbp-mark">${mark}</span><span class="mbp-name">${escapeAttr(o.textContent || o.value)}</span></div>`;
                }).join('');
                popover = document.createElement('div');
                popover.className = 'memoir-branch-popover';
                popover.innerHTML = `
                    <div class="mbp-header">Branches (${options.length})</div>
                    <div class="mbp-list">${lines}</div>
                    <div class="mbp-footer">● current · readonly — branch switching writes the current-branch pointer</div>
                `;
                document.body.appendChild(popover);

                // Position below the dropdown; flip up if it would overflow.
                const rect = el.getBoundingClientRect();
                const pop = popover.getBoundingClientRect();
                const margin = 6;
                let left = rect.left;
                if (left + pop.width > window.innerWidth - margin) {
                    left = Math.max(margin, window.innerWidth - pop.width - margin);
                }
                let top = rect.bottom + margin;
                if (top + pop.height > window.innerHeight - margin) {
                    top = Math.max(margin, rect.top - pop.height - margin);
                }
                popover.style.left = `${left}px`;
                popover.style.top  = `${top}px`;
            };

            const hidePop = () => {
                if (showTimer) { clearTimeout(showTimer); showTimer = null; }
                if (popover && popover.parentNode) popover.parentNode.removeChild(popover);
                popover = null;
            };

            el.addEventListener('mouseenter', () => {
                if (showTimer) clearTimeout(showTimer);
                showTimer = setTimeout(show, 180);
            });
            el.addEventListener('mouseleave', hidePop);
            // Safety net: tear down on any blur/scroll so a stale popover
            // never lingers after the user tabs away or resizes.
            window.addEventListener('blur', hidePop);
            window.addEventListener('scroll', hidePop, true);
        };

        const ensureBranchPopoverStyles = () => {
            if (document.getElementById('memoir-branch-popover-styles')) return;
            const s = document.createElement('style');
            s.id = 'memoir-branch-popover-styles';
            s.textContent = `
                .memoir-branch-popover {
                    position: fixed;
                    z-index: 10050;
                    min-width: 220px;
                    max-width: 320px;
                    max-height: 60vh;
                    overflow-y: auto;
                    background: rgba(17, 24, 39, 0.97);
                    color: #e5e7eb;
                    border: 1px solid rgba(99, 102, 241, 0.35);
                    border-radius: 10px;
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
                    padding: 10px 12px;
                    font-family: 'JetBrains Mono', ui-monospace, monospace;
                    font-size: 12px;
                    line-height: 1.5;
                    pointer-events: none;
                    backdrop-filter: blur(6px);
                    animation: mbp-fadein 0.12s ease-out;
                }
                @keyframes mbp-fadein {
                    from { opacity: 0; transform: translateY(-2px); }
                    to   { opacity: 1; transform: translateY(0);    }
                }
                .mbp-header {
                    font-weight: 600;
                    color: #a5b4fc;
                    border-bottom: 1px solid rgba(148, 163, 184, 0.2);
                    padding-bottom: 6px;
                    margin-bottom: 6px;
                }
                .mbp-list { display: flex; flex-direction: column; gap: 2px; }
                .mbp-row  { display: flex; gap: 8px; align-items: baseline; }
                .mbp-mark { width: 10px; color: #64748b; text-align: center; }
                .mbp-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
                .mbp-current .mbp-mark { color: #34d399; }
                .mbp-current .mbp-name { color: #e5e7eb; font-weight: 600; }
                .mbp-footer {
                    margin-top: 8px;
                    padding-top: 6px;
                    border-top: 1px solid rgba(148, 163, 184, 0.15);
                    color: #94a3b8;
                    font-style: italic;
                    font-size: 11px;
                }
            `;
            document.head.appendChild(s);
        };

        if (config.readonly) {
            // Hide +/- entirely in readonly so the dropdown can expand into
            // the freed horizontal space.
            hide('addBranchBtn');
            hide('removeBranchBtn');
            disable('branchSelector',  'Readonly mode: switching branches writes the current-branch pointer');
            // Hover popup on the (disabled) dropdown that lists every
            // branch, with the current one marked — lets the user peek
            // at what's available even though they can't switch.
            attachBranchListPopover('branchSelector');
            // refreshBtn intentionally NOT disabled — reloading store data
            // is a pure read operation.
        }
        if (!config.useLlm) {
            disable('queryBtn', 'LLM disabled: relaunch with --usellm to search');
            disable('modelBtn', 'LLM disabled: relaunch with --usellm to change models');
            // The input box no longer accepts free-text queries (those
            // route through /recall which needs an LLM). Make the constraint
            // obvious in the placeholder text.
            const input = document.getElementById('memoryInput');
            if (input) {
                input.placeholder = 'Type / for commands — LLM disabled (relaunch with --usellm for search)';
            }
            // The "Search for …" / "Query …" sample-query suggestions
            // would all route through /recall, so they're meaningless
            // without an LLM. Remove them entirely.
            const sampleSuggestions = document.getElementById('inputSuggestions');
            if (sampleSuggestions && sampleSuggestions.parentNode) {
                sampleSuggestions.parentNode.removeChild(sampleSuggestions);
            }
        }
    }

    window.memoirConfig = config;
    window.memoirConfig.isCommandBlocked = isCommandBlocked;
    window.memoirConfig.guardCommand = guardCommand;
    window.memoirConfig.applyDomGuards = applyDomGuards;
    window.memoirConfig.notify = notify;
    window.memoirConfig.notifyFromData = notifyFromData;
    window.memoirConfig.escapeAttr = escapeAttr;
})();
