---
type: descriptions
id: general-categories
name: General Category Descriptions
domain: general
version: 1.1.0
description: Top-level categories with semantic descriptions for classification guidance. Primary audience is coding-agent scenarios; general-purpose categories are retained but de-emphasized.
---

# Category Descriptions

Top-level categories with semantic descriptions for fast classification. Ordered by typical
importance for coding-agent workflows — the primary user base — with general-purpose
categories retained and marked `[general]` where coding relevance is secondary.

| Category | Description |
|----------|-------------|
| context | Project & team facts: tech stack, repo layout, architecture, standards, CI/CD, deploy targets, team roles/methodology. The "what is this codebase / how do we run it" bucket — the heaviest-used L2 for coding agents. |
| workflow | Process rules agents must follow: lint-before-commit, branching strategy, test gates, review policies, deploy pipelines, automation hooks, push conventions. |
| preferences | How the user likes to work: languages, frameworks, editors, AI models, formatting, commit/PR style, agent output verbosity. `preferences.coding.*` and `preferences.tools.*` dominate coding agents. Also `[general]` tastes (hobbies, food, entertainment). |
| knowledge | Non-obvious technical knowledge about systems: invariants, performance characteristics, hidden constraints, implementation quirks that aren't in the docs or readable from the code. |
| debugging | Investigation techniques and practices: log-dive patterns, repro strategies, profiling, bisection, instrumentation, common failure modes — reusable debugging toolkit. |
| project | Current-state task management: sprints, milestones, priorities, backlog (technical + features + bugs), blockers, requirements. For in-flight project goals. |
| experience | Past events that should shape future decisions: incidents, post-mortems, debugging wars, migrations, refactors, lessons-learned. |
| entity | Specific mentions, especially code entities: files, repositories, services, modules, endpoints, classes, functions. Also people/places/events when referenced by name. |
| settings | Configuration choices: editor, formatter, linter, git, shell, keybindings, debugger. Local environment setup. |
| system | Runtime/infrastructure config: cloud region, resource sizing, networking, observability. Live-system state, distinct from `context.project.infrastructure` (which is repo-level intent). |
| routine | Recurring habits: coding cadence (test-first, commit-often), review rhythms, standup/retro schedules. Distinguished from `workflow` (routine = habit, workflow = rule). |
| communication | Collaboration practices and surfaces: PR review style, RFC/ADR conventions, chat channels carrying load-bearing decisions. |
| profile | User identity facts useful to agents: role, seniority, primary languages/stacks, timezone, location. `[general]` personal demographics/health/finances also live here. |
| goals | Personal intentions: career advancement, learning targets, certifications, side projects. For project-scoped goals, prefer `context.project.goals` or `project.priorities.*`. |
| topics | Subject-matter stance on debates (patterns, practices, tech choices). De-emphasized for agents — actionable facts belong in `workflow`, `context`, or `knowledge`. |
| learning | Education resources being consumed: courses, books, videos. `[general]` — rarely load-bearing for coding agents. |
| relationships | People connections. Coding agents should prefer `context.team.roles` for ownership/reporting facts. `[general]` family/friends also live here. |

## Paths to prefer (canonical forms for common overlaps)

- **Project state vs. personal goals** — `context.project.goals` for in-flight project intent; `goals.*` reserved for personal career/learning goals. Do **not** write the same fact to both.
- **Team facts** — `context.team.roles` over `relationships.professional.*` when the fact describes project ownership or reporting structure.
- **Tech-stack knowledge** — `context.project.stack` for what the project uses; `knowledge.technical.*` for how those choices actually behave in practice; `topics.coding.languages` only for opinion/debate.
- **Testing conventions** — `workflow.coding.testing` for the rule ("tests must pass"); `preferences.coding.testing` for the tool/style preference; `routine.coding.testing` for the habit ("I write tests first").

## Machine-written namespaces (reserved, not in the taxonomy)

- `codebase:onboard` — populated by `/memoir-onboard` in a git repo, injected at SessionStart.
- `project:onboard` — populated by `/memoir-onboard` in a non-git folder; mirrors `codebase:onboard` for non-code projects (writing, editing, bookkeeping). File-shape index built by deterministic extractors, not LLM calls.
- `taxonomy:v1:*` — classifier bookkeeping; internal.
- `automemory.*` — reserved for auto-memory mirror hooks (optional plugin feature).

These are not classified via this taxonomy. Writes to them use `-p <path> -n <namespace>` to bypass the classifier.
