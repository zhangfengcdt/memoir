# Cloud Sync

`memoir remote`, `push`, `pull`, `fetch`, and `clone` round-trip a local memoir store with [memoir-cloud](https://github.com/zhangfengcdt/memoir-cloud). The commands exist in every install but are gated on `MEMORY_API_KEY`: without the variable, memoir behaves exactly as before (COMMUNITY tier) and the cloud commands exit 1 with `Cloud sync requires MEMORY_API_KEY (PRO)`.

```bash
export MEMORY_API_KEY=mk_...        # from the gateway's /app/keys page
memoir remote add --create --name "laptop"   # or: memoir remote add str_<id>
memoir push

# on another machine
memoir clone str_<id> ~/memories
export MEMOIR_STORE=~/memories
memoir recall "preferences"
```

## What syncs

A memoir store is an ordinary non-bare git repo. Its commits track one file, `data/prolly_config_tree_config`, which holds the ProllyTree root hash. The memory data itself lives in node files under `.git/prolly/nodes/files/<hash>`, which git does not track. Sync therefore has two halves, and the cloud serves both:

| Half | Carries | Transport |
|---|---|---|
| Git | commits, branches, tags | standard git smart-HTTP via the `git` binary memoir already requires |
| Chunks | the node files, keyed by filename | a small HTTP protocol: negotiate → upload missing → download missing |

Node filenames are prollytree node hashes and are treated as opaque identifiers; nothing is re-hashed. v1 syncs the whole node directory, and negotiation makes repeat pushes incremental (only chunks the server lacks are uploaded).

## Commands

| Command | What it does |
|---|---|
| `memoir remote add <store_id> [--url <gateway>] [--force]` | Verify the key (`GET /auth/whoami`) and the store (`GET /stores/<id>`), then add a git remote named `memoir-cloud` with URL `<gateway>/sync/<store_id>`. |
| `memoir remote add --create [--name <name>]` | Create the cloud store first (name defaults to the store directory name), then link. |
| `memoir remote show` / `remove` | Print gateway, store id, branch, and the cloud store summary; or unlink. |
| `memoir push [--branch <b>]` | Upload every chunk the cloud is missing, **then** `git push`. Default: current branch. |
| `memoir fetch` | `git fetch` all branches, tags, and `refs/cloud/*`; download every chunk not present locally. Moves no local branch. |
| `memoir pull [--branch <b>]` | `fetch`, then fast-forward the branch (creating it from the cloud if it does not exist locally). |
| `memoir clone <store_id> <path> [--url <gateway>]` | `git clone`, mark the store file-backed, download all chunks, verify the root chunk, name the remote `memoir-cloud`. |

All commands support `--json`.

## Rules

**Fast-forward only.** User branches on the cloud never rewind. If the cloud is ahead, `memoir push` exits with code 6 and `remote has commits you don't have; run memoir pull first`. If local and cloud histories have diverged, `memoir pull` also exits 6 (`local and cloud histories have diverged; cloud merge is not available yet`). Cloud-side merge is a later feature; memoir does not attempt a local merge of cloud history.

**Chunks before refs.** `push` only runs `git push` after every chunk upload has succeeded. A failed upload never results in a git push, so no cloud ref ever points at a commit whose root chunk is missing. The server enforces the same invariant: it refuses to advance a ref unless the root hash in the pushed commit is an uploaded chunk.

**`cloud/*` branches are read-only locally.** Branches under `refs/cloud/*` are cloud-owned proposal branches. `fetch` makes them visible as `memoir-cloud/cloud/...`; `push` refuses a branch whose name starts with `cloud/`.

**Root chunk check.** After `pull` and `clone`, memoir verifies that the chunk named by the tracked root hash exists locally and errors otherwise, so the store is never left pointing at missing data.

## Key handling

- The API key is read from `MEMORY_API_KEY` only. It is never written to `.git/config` or any other file.
- Git gets it per invocation as `-c http.extraHeader="Authorization: Bearer <key>"`; git runs with `GIT_TERMINAL_PROMPT=0` so an invalid key fails fast instead of prompting.
- The key is redacted from any error output that echoes a command.
- A 401 from the gateway is reported as `MEMORY_API_KEY is missing or invalid`.

## Environment variables

| Variable | Effect |
|---|---|
| `MEMORY_API_KEY` | Enables the cloud commands (PRO tier). |
| `MEMOIR_CLOUD_URL` | Gateway URL used by `remote add` and `clone` when `--url` is not passed. Default: the production gateway. After `remote add`, the URL is read back from the git remote. |

## Exit codes

| Code | Meaning |
|---|---|
| 1 | HTTP / auth error, or cloud sync not enabled |
| 2 | branch not found (locally for `push`, on the cloud for `pull`) |
| 3 | no store configured |
| 5 | git operation failed |
| 6 | non-fast-forward: cloud is ahead (`push`) or histories diverged (`pull`) |

## Out of scope for now

Merging diverged histories, a reachability walk so only chunks referenced by the pushed commit are synced, and proposal review from the CLI.
