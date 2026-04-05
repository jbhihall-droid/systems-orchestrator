# Critical Fixes — Design Spec

Date: 2026-04-05
Status: Approved
Scope: 17 fixes across 4 files (server.py, orchestrator_loop.py, lib/ledger.py, lib/dispatch.py)

## Goal

Fix all critical bugs that make the orchestrator loop non-functional, close security vulnerabilities, and resolve high/medium issues found in the audit.

## Approach

**File-based gate + targeted fixes.** Replace in-memory `GATE_STATE["failure_logged"]` with file-based check against `failures.md`. Fix each bug at its exact location. Keep lib/ stateless — file operations only, no business logic.

---

## Section 1: Critical Bugs

### B1 — orchestrator_loop.py reads wrong dict key

**File**: orchestrator_loop.py:269
**Current**: `parsed.get("tasks", [])`
**Fix**: `parsed.get("unblocked", [])`
**Also fix line 278**: items are `{"task_id": "ENG-001", "dept": "engineering"}` dicts. Extract: `task_id = task_info["task_id"] if isinstance(task_info, dict) else str(task_info)`

### B2 — execute_dispatch returns dict, step functions expect string

**Files**: orchestrator_loop.py:60-100
**Current**: `_step_researcher`, `_step_planner`, `_step_worker`, `_step_qa` return `execute_dispatch(packet)` directly (a dict).
**Fix**: Each step function extracts: `output = result.get("output", "") if isinstance(result, dict) else str(result)`. Return the string, not the dict.
**Also fix**: `submit_worker_report(project_dir, task_id, output)` — pass the string, not the dict.

### B3 — log_failure missing from lib/ledger.py

**File**: lib/ledger.py
**Add two functions**:

```python
def log_failure(project_dir, task_id, check_name, expected, actual, severity="major"):
    """Append structured failure to failures.md. Prerequisite for REWORK."""
    # Validate severity
    # Append markdown table row to project-ledger/failures.md
    # Create file with header if doesn't exist

def has_failure_logged(project_dir, task_id):
    """Check if any failure has been logged for this task_id."""
    # Read failures.md, check if task_id appears in any row
    # Return bool
```

### B4 — REWORK gate file-based enforcement

**File**: server.py
**Current**: `GATE_STATE["failure_logged"].get(task_id)` in-memory check
**Fix**: Replace with `_has_failure_logged(str(PROJECT_DIR), task_id)` — reads `failures.md`. Import `has_failure_logged` from lib/ledger.
**Kill**: Remove `"failure_logged"` from `GATE_STATE` dict. Keep `"tool_errors"` and `"onboarding"` (those are runtime state, not persistence).

**File**: orchestrator_loop.py:114-127
**Current**: Writes to failures.md inline with hardcoded header. 
**Fix**: Call `log_failure(project_dir, task_id, ...)` from lib/ledger instead of inline file writes.

---

## Section 2: Critical Security

### S1 — Shell injection in suggest_packages

**File**: server.py:589
**Current**: `search_term = need.split()[0]` then interpolated into shell commands.
**Fix**: Validate with `re.match(r'^[a-zA-Z0-9_-]+$', search_term)`. Return error JSON if invalid.

### S2 — Codex --dangerously-bypass-approvals-and-sandbox

**File**: lib/dispatch.py:393
**Current**: `cmd = [binary, "exec", "--dangerously-bypass-approvals-and-sandbox"]`
**Fix**: Remove the flag. Use `cmd = [binary, "exec"]` only. Let Codex use its default safety mode.

### S3 — Path traversal in _find_task_file

**File**: lib/ledger.py:567
**Add**: `_valid_task_id(task_id)` function — regex `^[A-Z]{2,4}-\d{1,4}$`. 
**Call**: At top of `_find_task_file`. Return `None` for invalid IDs.
**Also call**: At top of `get_task`, `submit_worker_report`, `submit_qa_report`, `submit_manager_review` — return error JSON for invalid IDs.

---

## Section 3: High Bugs

### B5 — DIRECT_SIGNAL_KEYWORDS dead code

**File**: lib/analyzer.py:100
**Fix**: Wire into `classify_complexity`. Before the FULL signal check, add:
```
if any(kw in task_lower for kw in DIRECT_SIGNAL_KEYWORDS):
    if element_count <= 1 and action_count <= 1:
        return "DIRECT"
```

### B6 — "transform" verb doesn't self-trigger

**File**: lib/analyzer.py:80
**Fix**: Add `"transform"` to `ACTION_KEYWORDS["transform"]`. Check all 7 verbs — add any verb literal that's missing from its own keyword list:
- observe → add "observe" if missing
- measure → add "measure" if missing
- etc.

### B7 — _unblock_dependents no-op

**File**: lib/ledger.py:606
**Fix**: Remove the function and its call site in `submit_manager_review`. Add comment: `# Unblocking is handled lazily by get_unblocked_tasks()`. The function misleads readers into thinking it does something.

---

## Section 4: Medium Issues

### M1 — Unused imports

**server.py**: Remove `os`, `random`, `defaultdict`, `CLARIFYING_PROMPTS`, `execute_dispatch`
**lib/dispatch.py**: Remove `os`
**lib/ledger.py**: Remove `os`
**orchestrator_loop.py**: Move `import re`, `import datetime` to module level. Remove `os`, `subprocess` if unused.

### M2 — Empty prompts/ directory

Delete `prompts/` directory.

### M3 — record_tool_outcome type validation

**File**: lib/ledger.py:329
**Add**: Validate `tool_name` is str, `task_id` matches regex, `action` is str, `success` is bool. Return error JSON for invalid types.

### M4 — Input length validation

**File**: lib/ledger.py
**Add helper**: `_check_length(value, max_len, field_name)` returns error string or None.
**Apply**: `create_task` description capped at 10,000 chars. `submit_worker_report` and `submit_qa_report` reports capped at 50,000 chars.

### M5 — TOCTOU on append files

All files that are append-only (`failures.md`, `outcomes.jsonl`, `tool_outcomes.jsonl`, `state.jsonl`, `architecture.md`, `decisions.md`) already use `open(path, "a")`. Verify this is the case for all of them. For task files (read-modify-write for status updates), accept the race — document it.

### M6 — Path traversal in _load_playbook

**File**: lib/dispatch.py:89
**Fix**: Validate `dept` against `DEPARTMENTS` keys before building path. If invalid, return a fallback playbook string.

### M7 — VERIFIED tasks re-openable

**File**: lib/ledger.py:179
**Fix**: At top of `submit_worker_report`, read task content, check if `**Status**: VERIFIED` or `**Status**: ESCALATED` is present. If so, return error JSON.

---

## Files Changed

| File | Changes |
|------|---------|
| orchestrator_loop.py | B1 (key fix), B2 (output extraction), B4 (use log_failure from lib) |
| lib/ledger.py | B3 (add log_failure + has_failure_logged), S3 (task_id validation), B7 (remove _unblock_dependents), M1 (imports), M3 (type validation), M4 (length validation), M7 (status guard) |
| lib/dispatch.py | S2 (remove --dangerously flag), M1 (imports), M6 (dept validation in _load_playbook) |
| server.py | B4 (file-based gate), S1 (sanitize suggest_packages), M1 (imports) |
| lib/analyzer.py | B5 (wire DIRECT_SIGNAL_KEYWORDS), B6 (add self-referencing verbs) |
| prompts/ | M2 (delete directory) |

## Verification

After all fixes:
1. `python3 -c "import server"` — no import errors
2. `python3 -m pytest tests/ -v` — 43+ tests pass
3. `python3 tests/test_analyze.py` — 88%+ accuracy maintained
4. Manual: create ledger, create task, submit worker report, submit QA, attempt REWORK without log_failure → GATE_REJECTION, log failure, REWORK succeeds
5. Manual: `suggest_packages(need="x; whoami")` → error, not execution
6. Manual: `get_task(task_id="../../etc/passwd")` → error, not file read
