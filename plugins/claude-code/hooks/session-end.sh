#!/usr/bin/env bash
# SessionEnd hook: no-op for memoir (no watch process, no daemons).
# Kept for symmetry with SessionStart and to reserve the hook slot for future
# cleanup needs (e.g. optional GC of dangling branches).
exit 0
