# Memoir + OpenClaw Integration Design Spec

## Overview

This document specifies how to integrate Memoir (git-like versioned memory) with OpenClaw (AI agent platform) using skills and hooks—**no plugin required**.

### Goals

1. **Persistent cross-session memory** - Agent remembers across conversations
2. **Namespace isolation** - Separate agent, user, and system memory
3. **Cost efficiency** - Minimize LLM calls for recall/store operations
4. **Branch support** - Project isolation, parallel sub-agents, experimental learning
5. **Simple installation** - Skill + hooks, no code compilation

### Non-Goals

- Replacing lossless-claw (session context management)
- Real-time memory sync across agents
- Complex merge conflict resolution

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         OpenClaw Agent                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    Hooks Layer                               │   │
│  │                                                              │   │
│  │  agent:bootstrap          message:sent        command:new    │   │
│  │       │                        │                   │         │   │
│  │       ▼                        ▼                   ▼         │   │
│  │  memoir-recall            memoir-store        flush-batch    │   │
│  │  (inject context)         (buffer turns)     (process batch) │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    Skill Layer                               │   │
│  │                                                              │   │
│  │  Agent can call:                                             │   │
│  │  • memoir remember "fact" --namespace <ns>                   │   │
│  │  • memoir recall "query" --namespace <ns>                    │   │
│  │  • memoir get <path> --namespace <ns>                        │   │
│  │  • memoir checkout <branch> --namespace <ns>                 │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                 Session Context (lossless-claw)              │   │
│  │                 DAG summaries, compaction                    │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Memoir Store                                │
│                                                                     │
│  Namespaces:                                                        │
│  ├── system        (shared across all agents)                       │
│  ├── agent         (this agent's learnings)                         │
│  └── user:{id}     (per-user preferences)                           │
│                                                                     │
│  Each namespace supports:                                           │
│  • Branches (project/*, experiment/*, subagent/*)                   │
│  • Versioned commits                                                │
│  • Path-based storage                                               │
│  • Semantic search                                                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Namespace Design

| Namespace | Scope | Contents | Lifetime |
|-----------|-------|----------|----------|
| `system` | Global | Environment, available tools, policies, other agents | Permanent, admin-managed |
| `agent` | Per-agent | Skills, lessons, mistakes, patterns learned | Permanent |
| `user:{id}` | Per-user | Preferences, projects, communication style | Follows user |

### Path Conventions

```
system/
├── env/os
├── env/shell
├── tools/available
├── agents/roster
└── policies/security

agent/
├── skills/debugging
├── skills/refactoring
├── lessons/error-handling
├── mistakes/common
└── patterns/codebase

user:{id}/
├── preferences/theme
├── preferences/coding-style
├── preferences/communication
├── projects/current
├── projects/{name}/context
└── history/decisions
```

---

## Branch Strategy

### Standard Branches

| Branch Pattern | Use Case |
|----------------|----------|
| `main` | Default, stable knowledge |
| `project/{name}` | Project-specific context |
| `experiment/{name}` | Try before committing |
| `subagent/{id}` | Parallel sub-agent isolation |

### Branch Workflows

**Project switching:**
```bash
# Detect project from cwd, auto-checkout
memoir checkout project/webapp --create-if-missing --namespace user:{id}
```

**Experimental learning:**
```bash
memoir checkout -b experiment/new-pattern --namespace agent
# ... learn things ...
memoir checkout main --namespace agent
memoir merge experiment/new-pattern --namespace agent
memoir branch -d experiment/new-pattern --namespace agent
```

**Parallel sub-agents:**
```bash
# Each sub-agent gets isolated branch
memoir checkout -b subagent/{id} --namespace agent
# Sub-agent works...
# Main agent merges when complete
memoir merge subagent/{id} --namespace agent
```

---

## Skill Specification

### File: `~/.openclaw/skills/memoir/SKILL.md`

```markdown
---
name: memoir
description: Git-like versioned memory - store, recall, and branch persistent memories
metadata: {"openclaw":{"requires":{"bins":["memoir"]},"install":[{"kind":"pip","package":"memoir","bins":["memoir"],"label":"Install via pip"}]}}
---

# Memoir - Versioned Agent Memory

Memoir provides persistent, versioned memory across sessions with namespace isolation.

## Namespaces

| Namespace | Use For |
|-----------|---------|
| `system` | Shared environment, tools, policies |
| `agent` | Your learnings, skills, lessons |
| `user:$OPENCLAW_USER_ID` | User preferences, projects |

## Commands

### Store a memory

When you learn something important:

```bash
# About yourself (skills, lessons)
memoir remember "Learned to use rg instead of grep for speed" --namespace agent --json

# About the user (preferences, context)
memoir remember "User prefers functional programming style" --namespace user:$OPENCLAW_USER_ID --json

# About the system
memoir remember "MCP server github available on port 3000" --namespace system --json
```

### Recall memories

When you need context:

```bash
# Semantic search (expensive - use sparingly)
memoir recall "debugging techniques" --namespace agent --limit 5 --json

# Direct path lookup (cheap - prefer this)
memoir get preferences.theme --namespace user:$OPENCLAW_USER_ID --json
```

### Branch management

For project isolation or experiments:

```bash
# Switch project context
memoir checkout project/{name} --create-if-missing --namespace user:$OPENCLAW_USER_ID --json

# Experiment with new approach
memoir checkout -b experiment/{name} --namespace agent --json

# List branches
memoir branch --namespace agent --json

# Merge successful experiment
memoir checkout main --namespace agent && memoir merge experiment/{name} --namespace agent --json
```

### View history

```bash
memoir log --namespace agent --limit 10 --json
memoir commits --namespace user:$OPENCLAW_USER_ID --json
```

## Decision Guide

Before storing, ask: **Who benefits from this memory?**

| What to Store | Namespace | Example |
|--------------|-----------|---------|
| Skill you learned | `agent` | "Use console.trace() for call stacks" |
| User preference | `user:{id}` | "Prefers dark mode" |
| System info | `system` | "Redis available on localhost:6379" |

## Best Practices

1. **Prefer `get` over `recall`** - Path lookup is free, semantic search costs tokens
2. **Store atomically** - One fact per remember call
3. **Use branches for projects** - Keeps context clean when switching
4. **Let hooks handle routine storage** - You focus on explicit important learnings
```

---

## Hook Specifications

### Hook 1: memoir-recall (Bootstrap)

Injects relevant memories at session start.

#### File: `~/.openclaw/hooks/memoir-recall/HOOK.md`

```markdown
---
name: memoir-recall
description: Inject memoir context at session bootstrap
on: agent:bootstrap
requires:
  bins: [memoir]
---
```

#### File: `~/.openclaw/hooks/memoir-recall/handler.js`

```javascript
import { execSync } from 'child_process';

export default async function({ context, sessionKey }) {
  const userId = extractUserId(sessionKey);

  // Detect project from cwd
  const project = detectProject(process.cwd());

  // Checkout project branch if exists
  if (project) {
    try {
      execSync(`memoir checkout project/${project} --create-if-missing --namespace user:${userId}`, { encoding: 'utf-8' });
    } catch (e) {
      // Branch operations failed, continue with main
    }
  }

  // Tier 1: Cheap path-based lookups (no LLM)
  const memories = await Promise.allSettled([
    execAsync(`memoir get preferences --namespace user:${userId} --json`),
    execAsync(`memoir get projects.current --namespace user:${userId} --json`),
    execAsync(`memoir get skills --namespace agent --json`),
    execAsync(`memoir get tools.available --namespace system --json`),
  ]);

  const [userPrefs, currentProject, agentSkills, systemTools] = memories.map(r =>
    r.status === 'fulfilled' ? r.value : null
  );

  // Inject into system context
  const memoryContext = formatMemoryContext({
    userPrefs,
    currentProject,
    agentSkills,
    systemTools
  });

  if (memoryContext) {
    context.inject(memoryContext);
  }
}

function extractUserId(sessionKey) {
  // Pattern: agent:<agentId>:user:<userId>:...
  const match = sessionKey.match(/^agent:[^:]+:user:([^:]+):/);
  return match?.[1] ?? process.env.OPENCLAW_USER_ID ?? 'default';
}

function detectProject(cwd) {
  // Try package.json name, or git repo name, or directory name
  try {
    const pkg = JSON.parse(execSync(`cat ${cwd}/package.json`, { encoding: 'utf-8' }));
    return pkg.name?.replace(/[^a-z0-9-]/gi, '-');
  } catch {
    try {
      const gitRoot = execSync('git rev-parse --show-toplevel', { cwd, encoding: 'utf-8' }).trim();
      return gitRoot.split('/').pop();
    } catch {
      return null;
    }
  }
}

function execAsync(cmd) {
  return new Promise((resolve, reject) => {
    try {
      const result = execSync(cmd, { encoding: 'utf-8', timeout: 5000 });
      resolve(JSON.parse(result));
    } catch (e) {
      reject(e);
    }
  });
}

function formatMemoryContext({ userPrefs, currentProject, agentSkills, systemTools }) {
  const sections = [];

  if (userPrefs) {
    sections.push(`### User Preferences\n${JSON.stringify(userPrefs, null, 2)}`);
  }
  if (currentProject) {
    sections.push(`### Current Project\n${JSON.stringify(currentProject, null, 2)}`);
  }
  if (agentSkills) {
    sections.push(`### Your Learned Skills\n${JSON.stringify(agentSkills, null, 2)}`);
  }
  if (systemTools) {
    sections.push(`### Available Tools\n${JSON.stringify(systemTools, null, 2)}`);
  }

  if (sections.length === 0) return null;

  return `## Long-Term Memory (from Memoir)\n\n${sections.join('\n\n')}`;
}
```

---

### Hook 2: memoir-store (Batch Storage)

Buffers conversation turns and periodically sends to memoir for analysis.

#### File: `~/.openclaw/hooks/memoir-store/HOOK.md`

```markdown
---
name: memoir-store
description: Buffer and batch-store learnings to memoir
on: [message:sent, command:new]
requires:
  bins: [memoir]
---
```

#### File: `~/.openclaw/hooks/memoir-store/handler.js`

```javascript
import { appendFileSync, readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs';
import { execSync } from 'child_process';
import { join } from 'path';

const BUFFER_DIR = join(process.env.HOME, '.openclaw', 'memoir-buffer');
const BATCH_SIZE = 10;

export default async function({ messages, sessionKey, type }) {
  const userId = extractUserId(sessionKey);
  const bufferFile = join(BUFFER_DIR, `${userId}.jsonl`);

  // Ensure buffer directory exists
  if (!existsSync(BUFFER_DIR)) {
    mkdirSync(BUFFER_DIR, { recursive: true });
  }

  if (type === 'message:sent') {
    // Extract last turn
    const lastUser = messages.findLast(m => m.role === 'user');
    const lastAssistant = messages.findLast(m => m.role === 'assistant');

    if (!lastUser || !lastAssistant) return;

    // Quick filter: skip trivial exchanges
    const combined = `${lastUser.content} ${lastAssistant.content}`;
    if (combined.length < 100) return; // Too short to be meaningful

    // Append to buffer
    const turn = {
      user: lastUser.content?.slice(0, 2000), // Truncate for safety
      assistant: lastAssistant.content?.slice(0, 2000),
      timestamp: Date.now(),
      sessionKey
    };

    appendFileSync(bufferFile, JSON.stringify(turn) + '\n');

    // Check if batch is ready
    const lines = readLines(bufferFile);
    if (lines.length >= BATCH_SIZE) {
      await flushBatch(bufferFile, lines, userId);
    }
  }

  // Flush on new session (captures previous session's tail)
  if (type === 'command:new') {
    if (existsSync(bufferFile)) {
      const lines = readLines(bufferFile);
      if (lines.length > 0) {
        await flushBatch(bufferFile, lines, userId);
      }
    }
  }
}

function readLines(file) {
  if (!existsSync(file)) return [];
  return readFileSync(file, 'utf-8').trim().split('\n').filter(Boolean);
}

async function flushBatch(bufferFile, lines, userId) {
  const turns = lines.map(l => JSON.parse(l));

  // Format for memoir analysis
  const content = turns.map((t, i) =>
    `[Turn ${i + 1}]\nUser: ${t.user}\nAssistant: ${t.assistant}`
  ).join('\n\n---\n\n');

  try {
    // Send to memoir for batch analysis
    // Memoir decides what's worth remembering
    execSync(`memoir analyze-batch --namespace user:${userId} --json`, {
      input: content,
      encoding: 'utf-8',
      timeout: 30000
    });

    // Clear buffer on success
    writeFileSync(bufferFile, '');
  } catch (e) {
    console.error('memoir-store: batch analysis failed', e.message);
    // Keep buffer for retry
  }
}

function extractUserId(sessionKey) {
  const match = sessionKey.match(/^agent:[^:]+:user:([^:]+):/);
  return match?.[1] ?? process.env.OPENCLAW_USER_ID ?? 'default';
}
```

---

### Hook 3: memoir-subagent (Parallel Sub-Agent Support)

Manages branches for parallel sub-agents.

#### File: `~/.openclaw/hooks/memoir-subagent/HOOK.md`

```markdown
---
name: memoir-subagent
description: Manage memoir branches for parallel sub-agents
on: [message:received, message:sent]
requires:
  bins: [memoir]
---
```

#### File: `~/.openclaw/hooks/memoir-subagent/handler.js`

```javascript
import { execSync } from 'child_process';

export default async function({ sessionKey, type, context }) {
  // Only handle sub-agent sessions
  if (!isSubagentSession(sessionKey)) return;

  const subagentId = extractSubagentId(sessionKey);
  const branch = `subagent/${subagentId}`;

  if (type === 'message:received') {
    // Sub-agent starting: create/checkout branch
    try {
      execSync(`memoir checkout -b ${branch} --namespace agent 2>/dev/null || memoir checkout ${branch} --namespace agent`, {
        encoding: 'utf-8'
      });

      // Inject branch info for sub-agent
      context.inject(`## Memoir Branch\nYou are on branch: \`${branch}\`\nYour learnings are isolated. Main agent will merge when you complete.`);
    } catch (e) {
      // Branch operations failed, continue without
    }
  }
}

function isSubagentSession(sessionKey) {
  return sessionKey.includes(':subagent:');
}

function extractSubagentId(sessionKey) {
  const match = sessionKey.match(/:subagent:([^:]+)/);
  return match?.[1] ?? 'unknown';
}
```

**Note:** Sub-agent branch merging should be handled by the main agent after sub-agent completion, typically in the tool that spawned the sub-agent.

---

## Recall Strategy

### Tiered Approach

```
┌─────────────────────────────────────────────────────────────┐
│                    Recall Decision Tree                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  agent:bootstrap                                            │
│       │                                                     │
│       ▼                                                     │
│  Tier 1: Path-based `get` (FREE)                           │
│  • memoir get preferences --namespace user:{id}             │
│  • memoir get skills --namespace agent                      │
│  • memoir get tools --namespace system                      │
│       │                                                     │
│       ▼                                                     │
│  Inject into system context                                 │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  message:received (keyword detected)                        │
│       │                                                     │
│       ▼                                                     │
│  Keywords: "remember", "last time", "previously",           │
│            "you said", "my preference", "we discussed"      │
│       │                                                     │
│       ▼                                                     │
│  Tier 2: Semantic `recall` (EXPENSIVE)                     │
│  • memoir recall "{extracted query}" --namespace user:{id}  │
│       │                                                     │
│       ▼                                                     │
│  Inject into turn context                                   │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Agent decides (via skill)                                  │
│       │                                                     │
│       ▼                                                     │
│  Tier 3: On-demand `recall` (AGENT-CONTROLLED)             │
│  • Agent calls memoir recall when it judges necessary       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Cost Summary

| Operation | Trigger | LLM Cost | Frequency |
|-----------|---------|----------|-----------|
| `get` (path lookup) | Bootstrap | None | 1x/session |
| `recall` (keyword) | Keyword detected | Per-call | Rare |
| `recall` (skill) | Agent decides | Per-call | As needed |
| `analyze-batch` | Every N messages | Per-batch | ~1x/10 turns |

---

## Configuration

### Environment Variables

```bash
# Required
export MEMOIR_STORE=~/.openclaw/memoir

# Optional
export OPENCLAW_USER_ID=default          # Fallback user ID
export MEMOIR_BATCH_SIZE=10              # Turns before batch analysis
export MEMOIR_RECALL_KEYWORDS="remember|last time|previously"
```

### OpenClaw Config (`~/.openclaw/openclaw.json`)

```json
{
  "skills": {
    "entries": {
      "memoir": {
        "enabled": true
      }
    }
  },
  "hooks": {
    "entries": {
      "memoir-recall": { "enabled": true },
      "memoir-store": { "enabled": true },
      "memoir-subagent": { "enabled": true }
    }
  }
}
```

---

## Installation

### 1. Install Memoir

```bash
pip install memoir
# or
brew install memoir
```

### 2. Initialize Store

```bash
memoir new ~/.openclaw/memoir
export MEMOIR_STORE=~/.openclaw/memoir
```

### 3. Install Skill

```bash
mkdir -p ~/.openclaw/skills/memoir
# Copy SKILL.md from above
```

### 4. Install Hooks

```bash
mkdir -p ~/.openclaw/hooks/memoir-recall
mkdir -p ~/.openclaw/hooks/memoir-store
mkdir -p ~/.openclaw/hooks/memoir-subagent
# Copy HOOK.md and handler.js for each
```

### 5. Verify

```bash
memoir status
openclaw skills list | grep memoir
openclaw hooks list | grep memoir
```

---

## Sequence Diagrams

### Session Start

```
User starts session
        │
        ▼
OpenClaw: agent:bootstrap event
        │
        ▼
memoir-recall hook
        │
        ├── memoir get preferences --namespace user:{id}
        ├── memoir get projects.current --namespace user:{id}
        ├── memoir get skills --namespace agent
        └── memoir get tools --namespace system
        │
        ▼
Inject into system context
        │
        ▼
Agent ready with memory context
```

### During Conversation

```
User sends message
        │
        ▼
OpenClaw: message:received event
        │
        ▼
Keyword detected? ──No──► Skip
        │
       Yes
        │
        ▼
memoir recall "{query}" --namespace user:{id}
        │
        ▼
Inject into turn context
        │
        ▼
Agent responds
        │
        ▼
OpenClaw: message:sent event
        │
        ▼
memoir-store hook
        │
        ├── Append turn to buffer
        └── Buffer full? ──No──► Done
                │
               Yes
                │
                ▼
        memoir analyze-batch
                │
                ▼
        Memoir stores relevant facts
```

### Parallel Sub-Agents

```
Main agent spawns sub-agents
        │
        ├─────────────┬─────────────┐
        ▼             ▼             ▼
   Sub-agent A   Sub-agent B   Sub-agent C
        │             │             │
        ▼             ▼             ▼
   checkout       checkout       checkout
   subagent/a     subagent/b     subagent/c
        │             │             │
        ▼             ▼             ▼
   Work + store   Work + store   Work + store
   on branch      on branch      on branch
        │             │             │
        └─────────────┴─────────────┘
                      │
                      ▼
              All complete
                      │
                      ▼
              Main agent merges
              branches to main
```

---

## Future Enhancements

1. **`before_compaction` hook** - When OpenClaw fixes [issue #4967](https://github.com/openclaw/openclaw/issues/4967), store important context before it's compacted

2. **Smart keyword detection** - Use lightweight classifier instead of regex

3. **Cross-agent memory sharing** - `system` namespace with read-only access patterns

4. **Memory decay** - Automatically reduce confidence of old, unused memories

5. **Conflict resolution UI** - When merging branches with conflicts, surface to user

---

## Summary

| Component | Purpose |
|-----------|---------|
| **Skill** | Teaches agent when/how to use memoir CLI |
| **memoir-recall hook** | Injects memories at session start (cheap `get`) |
| **memoir-store hook** | Batches turns, sends to memoir for analysis |
| **memoir-subagent hook** | Manages branches for parallel sub-agents |
| **Namespaces** | Isolate agent/user/system memory |
| **Branches** | Project isolation, experiments, sub-agents |

**Key principles:**
- Prefer `get` over `recall` (path lookup is free)
- Batch storage to reduce LLM calls
- Agent controls expensive operations via skill
- Hooks handle routine recall/store automatically
