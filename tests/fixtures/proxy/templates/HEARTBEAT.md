# HEARTBEAT.md - Scheduled Tasks

This file defines what the agent should check periodically.

## Check Frequency: Every 30 minutes

## Tasks

### 1. Git Status Check
- Run `git status` to check for uncommitted changes
- If there are changes, summarize them briefly
- Do NOT commit automatically

### 2. Test Status
- Check if tests are currently passing
- Only run tests if explicitly requested

### 3. Build Status
- Check if there are any build errors
- Report but do not fix automatically

### 4. Dependency Updates
- Check for security advisories only
- Do not upgrade dependencies automatically

## Response Format

If nothing needs attention, respond with:
```
HEARTBEAT_OK
```

If there are items to report:
```
HEARTBEAT_REPORT
- [item 1]
- [item 2]
```

## Important

- Do NOT infer tasks from prior conversations
- Do NOT repeat old tasks
- Only check what is listed above
- Keep responses minimal
