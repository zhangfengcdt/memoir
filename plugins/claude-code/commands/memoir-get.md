---
description: "Fast direct lookup of memories by exact taxonomy path. No LLM — use when you already know the key(s)."
argument-hint: "<key> [<key>...] [-n <namespace>]"
allowed-tools: Bash
---

Fetch stored values directly from the prolly store by exact key. This is the fast shortcut — no LLM classification, no semantic search, just a key/value read. Use it once you already know the taxonomy path (e.g. from `/memoir-keys` or a prior `/memoir-recall`).

Pass one or more keys separated by spaces:

```
/memoir-get preferences.coding.style
/memoir-get preferences.coding.style profile.professional.skills
/memoir-get user.preferences.theme -n default
```

Latency is typically <10ms vs ~500-800ms for `/memoir-recall`, since no LLM call is made.

!`bash -c 'STORE="${MEMOIR_STORE:-$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/derive-store-path.sh")}"; eval "memoir --json -s \"$STORE\" get $ARGUMENTS"' ARGUMENTS="$ARGUMENTS"`

Show each returned `full_key` and its `value.content`. Mark any `found: false` entries as missing so the user knows which keys don't exist.
