# Cloud Sync

`memoir remote`, `push`, `pull`, and `fetch` round-trip a local memoir store with [memoir-cloud](https://github.com/zhangfengcdt/memoir-cloud). The commands exist in every install but need a login (or `MEMOIR_API_KEY`); without one, memoir behaves exactly as before (COMMUNITY tier) and the cloud commands exit 1 asking you to run `memoir login`.

From the root of a local clone of your code repo:

```bash
memoir login                 # once per machine (add --url <gateway> for a non-production gateway)
memoir push --create         # New: create <handle>/<repo name> from this repo's memories
# or
memoir remote add <owner>/<store> && memoir pull   # Open: link an existing cloud store
```

Inside a code repo, memoir uses that repo's store, `~/.memoir/<slug>`, the same one the Claude Code plugin uses there (see [Store resolution](#store-resolution)), so there is no `MEMOIR_STORE` to set. `memoir login` saves the gateway, so there is no `--url` either.

There is no `clone`. Local stores are created automatically (by the Claude Code plugin on session start, or by the first memoir command), so linking is always done on a store that already exists, and `pull` adopts the cloud history when that store is still empty.

For a hands-on walkthrough see [Cloud sync commands](cli.md#cloud-sync-commands) on the CLI page.

## Logging in

`memoir login` works like `gh auth login`: it prints a short code and a link, opens the browser, and waits while you click **Authorize** on the cloud (signed in there). The cloud mints a key named `memoir CLI (<hostname>)`, which you can see and revoke on its keys page. `memoir login --with-key` reads a key from stdin instead, for headless machines. `memoir logout` revokes the key on the cloud when reachable and deletes it locally.

The key, gateway and handle are saved to `~/.config/memoir/cloud.json` (`$XDG_CONFIG_HOME/memoir/cloud.json` when that is set), mode 0600 in a 0700 directory.

| What | Resolution order |
|---|---|
| key | `MEMOIR_API_KEY` → `cloud.json` |
| gateway | `--url` → `MEMOIR_CLOUD_URL` → `cloud.json` → production |

## Store resolution

`-s` → `MEMOIR_STORE` → **repo mode** → current directory.

Repo mode applies when you're inside a git work tree that is not itself a memoir store. The store is `~/.memoir/<slug>`, where the slug is the main worktree root with `/` and `.` replaced by `-` (exactly the plugin's derivation, so linked worktrees share the main repo's store). Cloud commands print it first, e.g. `store: ~/.memoir/-Users-me-code-sedona (repo sedona)`. `--repo` forces repo mode even when `MEMOIR_STORE` is set. `remote add` and `pull` create the store on first use; other commands stop with a hint when it doesn't exist yet. With no arguments, `push --create` names the cloud store after the repo, and `remote add` proposes `<handle>/<repo name>`.

## Addresses

A cloud store is addressed GitHub-style as `<owner>/<store>`, for example `feng-zhang/demo`. `owner` is your handle (chosen once in the gateway's web app), `store` is the store name. The address is also a URL: `https://<gateway>/feng-zhang/demo` opens the store page in a browser and is the git remote memoir configures.

| Part | Rules |
|---|---|
| handle | 1–39 letters, digits or hyphens; no leading, trailing or double hyphen |
| store name | 1–100 letters, digits, `.`, `_` or `-`; not starting with `.`; not ending in `.git` |

Both are matched case-insensitively by the server. Memoir validates an address locally before any network call and rejects the server's internal `str_...` ids with a message pointing at the address form. If your account has no handle yet, every cloud command tells you to choose one at `<gateway>/app`.

## What syncs

A memoir store is an ordinary non-bare git repo. Its commits track one file, `data/prolly_config_tree_config`, which holds the ProllyTree root hash. The memory data itself lives in node files under `.git/prolly/nodes/files/<hash>`, which git does not track. Sync therefore has two halves, and the cloud serves both under the store's address:

| Half | Carries | Transport |
|---|---|---|
| Git | commits, branches, tags | standard git smart-HTTP via the `git` binary memoir already requires |
| Chunks | the node files, keyed by filename | a small HTTP protocol under `<address>/chunks`: negotiate → upload the missing ones in multipart batches (up to 500 per request, 4 in flight) → download missing |

Node filenames are prollytree node hashes and are treated as opaque identifiers; nothing is re-hashed. When the server advertises `Memoir-Accept-Encoding: gzip` on its chunk routes, upload batches are sent gzip-compressed (`Content-Encoding: gzip`), which cuts the bytes on the wire about five-fold; against a server that doesn't, they go out raw as before. v1 syncs the whole node directory. Repeat pushes are incremental twice over: after a successful push (or a fetch) memoir records the hashes the server confirmed under `.git/memoir-cloud/pushed-origin`, so the next push computes what is new locally and sends only that, with no negotiate round trip. If that record is missing, or the server rejects a ref with `missing chunk`, memoir falls back to negotiating the whole set and rebuilds the record.

## Commands

| Command | What it does |
|---|---|
| `memoir remote add [<owner>/<store>] [--url <gateway>] [--force]` | Resolve the address (404 → `store <owner>/<store> not found (or you don't own it)`), then set the git remote `origin` to `https://<gateway>/<owner>/<store>`. With no argument, proposes `<your handle>/<store directory name>` and asks before resolving. |
| `memoir remote show` / `remove` | Print the address, gateway, branch and cloud summary; or unlink. |
| `memoir push [--branch <b>] [--create <store>]` | Upload every chunk the cloud is missing (batched), **then** `git push`. `--create <store>` first creates that cloud store under your handle and links it as `origin`. Default branch: current. Prints `pushed main to <owner>/<store>: 7,361 chunks (6,900 new, 41.3 MB sent (gzip)) in 41.2 s, git in 2.4 s`. |
| `memoir fetch` | `git fetch` all branches, tags, and `refs/cloud/*`; download every chunk not present locally. Moves no local branch. |
| `memoir pull [--branch <b>] [--force]` | `fetch`, then fast-forward the branch. A branch that does not exist locally is created from the cloud; a pristine local store (only prollytree's initial commit, no memories) adopts the cloud history. `--force` replaces the local branch with the cloud copy, discarding local memories on it; the previous tip is kept under `refs/memoir/backup/<branch>` and printed. |
| `memoir status` | Shows `origin: <owner>/<store>` when a cloud remote is configured. |

All commands support `--json`; the JSON carries the address as `origin`, never an id.

## Rules

**Fast-forward only.** User branches on the cloud never rewind. If the cloud is ahead, `memoir push` exits with code 6 and `remote has commits you don't have; run memoir pull first`. If local and cloud histories have diverged, `memoir pull` also exits 6 (`local and cloud histories have diverged; cloud merge is not available yet`) and points at `memoir pull --force`, the one explicit way to discard the local memories on that branch and take the cloud copy. Linking a store that already holds its own memories to a cloud store with a different history is the same situation and gets the same answer. Cloud-side merge is planned; memoir does not attempt a local merge of cloud history.

**Chunks before refs.** `push` only runs `git push` after every batch has succeeded. A failed upload never results in a git push, so no cloud ref ever points at a commit whose root chunk is missing. The server enforces the same invariant: it refuses to advance a ref unless the root hash in the pushed commit is an uploaded chunk. A 502 (`object store unavailable`) is retried with backoff and then surfaced as `object store unavailable, retry later`; an interrupted push simply resumes on the next run, with already-written chunks reported as existing. A chunk the server rejects fails the push and is named in the error.

**`cloud/*` branches are read-only locally.** Branches under `refs/cloud/*` are cloud-owned proposal branches. `fetch` makes them visible as `origin/cloud/...`; `push` refuses a branch whose name starts with `cloud/`.

**Root chunk check.** After `pull`, memoir verifies that the chunk named by the tracked root hash exists locally and errors otherwise, so the store is never left pointing at missing data.

## Code repo metadata

When the store is the memory store of a code repo (the Claude Code plugin's `~/.memoir/<slug>` stores, where the slug is the repo's path), `memoir remote add` and every successful `memoir push` also report that repo to memoir-cloud, so the cloud's store list and store page can show its link, description, language and topics.

- **Always, from the local clone:** the `origin` URL normalised to https, host, owner and name, default branch, current branch and commit, and the repo directory name.
- **For GitHub repos, when reachable within 2 seconds:** description, topics, language, visibility, stars and homepage from the GitHub API, authenticated with `gh auth token` when the GitHub CLI is logged in. Offline, rate-limited or private-without-token simply means these fields are left out.
- The document is sent only when it changed since the last send (recorded in `.git/memoir-cloud/repo-meta-origin`). Collecting or sending it can never fail `remote add` or `push`. A store that maps to no code repo sends nothing, and nothing is written to the store itself.

## Key handling

- The API key comes from `MEMOIR_API_KEY` or, when that is unset, from the login file `~/.config/memoir/cloud.json` (mode 0600; see [Logging in](#logging-in)). It is never written to `.git/config`, to the store, or anywhere else, and never printed.
- Git gets it per invocation as `-c http.extraHeader="Authorization: Bearer <key>"`; git runs with `GIT_TERMINAL_PROMPT=0` so an invalid key fails fast instead of prompting.
- The key is redacted from any error output that echoes a command.
- A 401 from the gateway is reported as ``not signed in: run `memoir login` (or set MEMOIR_API_KEY)``.

## Environment variables

| Variable | Effect |
|---|---|
| `MEMOIR_API_KEY` | API key; overrides the one saved by `memoir login`. |
| `MEMOIR_CLOUD_URL` | Gateway URL used by `login`, `remote add` and `push --create` when `--url` is not passed; overrides the gateway saved by `memoir login`. Default: the production gateway. After linking, the gateway is read back from the `origin` URL. |

## Exit codes

| Code | Meaning |
|---|---|
| 1 | HTTP / auth / address error, or cloud sync not enabled |
| 2 | branch not found (locally for `push`, on the cloud for `pull`) |
| 3 | no store configured |
| 5 | git operation failed |
| 6 | non-fast-forward: cloud is ahead (`push`) or histories diverged (`pull`) |

## Out of scope for now

Merging diverged histories, a reachability walk so only chunks referenced by the pushed commit are synced, and proposal review from the CLI.
