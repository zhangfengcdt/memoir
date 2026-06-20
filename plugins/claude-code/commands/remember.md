---
description: "Manually capture a memory now (independent of Stop-hook auto-capture). On a conflict with an existing memory, prompts you to choose how to resolve it. Pass -p <path> to skip classification."
argument-hint: "<fact> [-n <namespace>] [-p <path>] [--merge-policy <strategy>]"
allowed-tools: Bash
---

Save the user's stated fact as a memoir memory. By default this resolves conflicts **interactively**: if the target key is already occupied, you (the agent) present the existing-vs-incoming values and let the user choose what to do, rather than silently overwriting or appending.

The user's input is everything between the markers below — raw text, treat verbatim:

<<<MEMOIR_REMEMBER_INPUT_BEGIN
$ARGUMENTS
MEMOIR_REMEMBER_INPUT_END

## Procedure

1. From the input, pull out any `-n`/`--namespace <ns>`, `-p`/`--path <path>`, and `--merge-policy <strategy>` flags (each consumes the following whitespace-separated token). `--replace` is a bare flag (no token). Everything else, in order, is the memory **content**.

2. **Probe write.** Issue a single Bash tool call shaped like the template below. The single-quoted heredoc terminator suppresses **all** shell expansion, so content with `$variables`, backticks, parens, semicolons, slashes, or newlines passes through verbatim — never put the content on the bash command line itself.

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
   bash "$CLAUDE_PLUGIN_ROOT/scripts/memoir-cli.sh" --json -s "$STORE" remember "$CONTENT" --merge-policy reject
   ```

   - Append `-p <path>` and/or `-n <namespace>` after `remember "$CONTENT"` only if the user supplied them.
   - **Default to `--merge-policy reject`** as shown (this is what makes it interactive — it writes fresh keys but refuses to clobber existing ones, returning them as conflicts). **Exception:** if the user explicitly supplied their own `--merge-policy <strategy>` or `--replace`, pass *that* through instead and do **not** add `--merge-policy reject` — they've opted out of prompting.
   - If the literal string `MEMOIR_REMEMBER_EOF` appears on a line by itself inside the content, swap in a different terminator.
   - `memoir-cli.sh` is the plugin's CLI wrapper — it picks `memoir` on PATH, falling back to `uvx --from memoir-ai==<pin> memoir` then `uv tool run …`, so it works without a global install.

3. **Read the JSON response:**

   - `"success": true` → the memory was written to a fresh key. Report the resulting `key` (taxonomy path) and `commit_hash` in one short line. **Done.**
   - `"success": false` with a non-empty `"conflicts"` array → go to step 4. (Any other path in `keys` that is *not* in `conflicts` was already written successfully — mention those as saved.)
   - `"success": false` with an `"error"` and no `conflicts` → report the error. Done.

4. **Resolve each conflict interactively.** For every entry in `conflicts`, show the user a short comparison and ask how to resolve it:

   ```
   ● Conflict at <key>
     existing: <existing_content>
     incoming: <incoming_content>
   How should I save this? [replace / append / merge / skip]
   ```

   - **replace** — overwrite with the new value (keeps only the latest)
   - **append** — keep both (adds the new value as another entry)
   - **merge** — LLM-consolidate the old and new into one statement (slower; needs a model)
   - **skip** — leave the existing memory unchanged, discard the new value

   Then **stop and wait for the user's answer.** Do not pick a default yourself.

5. **Apply the choice** (after the user replies) with one resolving call per non-skipped key — re-paste the content verbatim and map the choice to a strategy (`replace`/`append`/`merge`→`llm_merge`):

   ```bash
   CONTENT=$(cat <<'MEMOIR_REMEMBER_EOF'
   <paste the full content verbatim again>
   MEMOIR_REMEMBER_EOF
   )
   bash "$CLAUDE_PLUGIN_ROOT/scripts/memoir-cli.sh" --json -s "$STORE" remember "$CONTENT" -p <conflict-key> --merge-policy <replace|append|llm_merge>
   ```

   For **skip**, make no call for that key. Report the final `key`/`commit_hash` of each write you performed.

## Notes

- Pass `-p preferences.coding.style` (or any explicit taxonomy path) to skip the LLM classifier — about 25× faster (~0.4s vs ~10s).
- `-n <namespace>` writes to a non-default namespace; default is `default`.
- To capture without any prompting, pass an explicit `--merge-policy <strategy>` (e.g. `--merge-policy replace`) — step 2 then forwards it and skips the conflict flow.
- The Stop hook still fires for the rest of the turn — this command is for *immediate*, synchronous capture.
