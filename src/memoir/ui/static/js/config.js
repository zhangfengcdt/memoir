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
    const MUTATING_COMMANDS = new Set([
        '/connect', '/new', '/demo',
        '/remember', '/forget',
        '/branch',  // create/delete subcommands mutate
        '/checkout', '/merge', '/time-travel',
    ]);

    // Commands that require calling an LLM.
    const LLM_COMMANDS = new Set([
        '/recall', '/search', '/summarize',
        '/remember',  // classification step
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

        if (config.readonly) {
            disable('addBranchBtn',    'Readonly mode: cannot create branches');
            disable('removeBranchBtn', 'Readonly mode: cannot delete branches');
            disable('branchSelector',  'Readonly mode: switching branches writes the current-branch pointer');
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
