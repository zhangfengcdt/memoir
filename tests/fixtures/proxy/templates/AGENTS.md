# AGENTS.md - Multi-Agent Team Configuration

## Team Structure

This file defines the multi-agent team hierarchy and handoff protocols.

## Agents

### coordinator
- **Role**: Primary coordinator agent
- **SOUL**: ~/.openclaw/agents/coordinator/SOUL.md
- **Capabilities**: Task decomposition, delegation, synthesis
- **Can delegate to**: developer, researcher, reviewer

### developer
- **Role**: Code implementation specialist
- **SOUL**: ~/.openclaw/agents/developer/SOUL.md
- **Capabilities**: Write code, run tests, debug
- **Reports to**: coordinator

### researcher
- **Role**: Information gathering and analysis
- **SOUL**: ~/.openclaw/agents/researcher/SOUL.md
- **Capabilities**: Web search, documentation lookup, summarization
- **Reports to**: coordinator

### reviewer
- **Role**: Code review and quality assurance
- **SOUL**: ~/.openclaw/agents/reviewer/SOUL.md
- **Capabilities**: Code review, security analysis, best practices
- **Reports to**: coordinator

## Handoff Protocol

### Delegation Format
```json
{
  "action": "delegate",
  "to": "<agent_id>",
  "task": "<task_description>",
  "context": "<relevant_context>",
  "return_to": "<calling_agent_id>"
}
```

### Completion Format
```json
{
  "action": "complete",
  "from": "<agent_id>",
  "result": "<task_result>",
  "return_to": "<calling_agent_id>"
}
```

## Shared Context

All agents share:
- Workspace files and git history
- MEMORY.md for persistent context
- Tool definitions from TOOLS.md

## Constraints

- Maximum delegation depth: 3 levels
- Each agent must complete or escalate within 5 minutes
- Circular delegation is prohibited
