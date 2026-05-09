---
description: "Manually capture a memory now (independent of Stop-hook auto-capture). Pass -p <path> to skip classification."
argument-hint: "<fact> [-n <namespace>] [-p <path>]"
allowed-tools: Bash
---

Save the user's stated fact as a memoir memory immediately, in **one** Bash tool call. Do not retry by re-invoking this slash command — the steps below already handle every content shape (multiline, parentheses, slashes, semicolons, quotes, backticks, `$variables`, etc.).

The user's input is everything between the markers below — raw text, treat verbatim:

<<<MEMOIR_REMEMBER_INPUT_BEGIN
$ARGUMENTS
MEMOIR_REMEMBER_INPUT_END

Procedure:

1. From the input, pull out any `-n <namespace>` / `--namespace <namespace>` and `-p <path>` / `--path <path>` flag pairs (each consumes the immediately following whitespace-separated token). Everything else, in order, is the memory **content**.

2. Issue a single Bash tool call shaped like the template below. The single-quoted heredoc terminator suppresses **all** shell expansion inside the body, so content with `$variables`, backticks, parens, semicolons, slashes, or newlines passes through verbatim — never put the content on the bash command line itself.

   ```bash
   if [ ! -x "${CLAUDE_PLUGIN_ROOT:-}/scripts/memoir-cli.sh" ]; then
     for c in "$(pwd)/plugins/claude-code" "${HOME}/.claude/plugins/marketplaces/memoir/plugins/claude-code"; do
       if [ -x "$c/scripts/memoir-cli.sh" ]; then CLAUDE_PLUGIN_ROOT="$c"; break; fi
     done
   fi
   STORE="${MEMOIR_STORE:-$(bash "$CLAUDE_PLUGIN_ROOT/scripts/derive-store-path.sh")}"
   bash "$CLAUDE_PLUGIN_ROOT/scripts/ensure-store.sh" "$STORE" >/dev/null
   CONTENT=$(cat <<'MEMOIR_REMEMBER_EOF'
   <paste the full content verbatim, including any newlines>
   MEMOIR_REMEMBER_EOF
   )
   bash "$CLAUDE_PLUGIN_ROOT/scripts/memoir-cli.sh" --json -s "$STORE" remember "$CONTENT"
   ```

   - Append `-p <path>` and/or `-n <namespace>` after `remember "$CONTENT"` only if the user supplied them.
   - If the literal string `MEMOIR_REMEMBER_EOF` appears on a line by itself inside the content, swap in a different terminator.
   - `bash "$CLAUDE_PLUGIN_ROOT/scripts/memoir-cli.sh"` is the plugin's CLI wrapper — it picks `memoir` on PATH, falling back to `uvx --from memoir-ai==<pin> memoir` and then `uv tool run …`, so this works on machines without a global memoir install.

3. Parse the JSON response and report the resulting `key` (taxonomy path) and `commit_hash` to the user in one short line.

Notes:
- Pass `-p preferences.coding.style` (or any explicit taxonomy path) to skip the LLM classifier — about 25× faster (~0.4s vs ~10s).
- `-n <namespace>` writes to a non-default namespace; default is `default`.
- The Stop hook still fires for the rest of the turn — this command is for *immediate*, synchronous capture.
