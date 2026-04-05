# Critical Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 17 audit findings — 4 critical bugs, 3 critical security, 3 high bugs, 7 medium issues — making the orchestrator loop functional and the system secure.

**Architecture:** Targeted fixes at exact locations. Replace in-memory GATE_STATE gate with file-based check. Keep lib/ stateless. All fixes are backward-compatible with existing tests.

**Tech Stack:** Python 3.13, FastMCP, pytest

---

## File Map

| File | Responsibility | Fixes |
|------|---------------|-------|
| `lib/ledger.py` | File-based task lifecycle + project knowledge | B3, S3, B7, M1, M3, M4, M5, M7 |
| `orchestrator_loop.py` | Autonomous execution loop | B1, B2, B4-loop, M1 |
| `server.py` | MCP tool registration + gate enforcement | B4-gate, S1, M1 |
| `lib/dispatch.py` | Multi-model prompt crafting + execution | S2, M1, M6 |
| `lib/analyzer.py` | Scoring, classification, system model derivation | B5, B6 |

---

### Task 1: lib/ledger.py — Add task_id validation, log_failure, has_failure_logged (B3, S3)

**Files:**
- Modify: `lib/ledger.py:12-17` (imports), `lib/ledger.py:567-578` (_find_task_file)
- Test: `tests/test_orchestrator.py` (existing tests must still pass)

- [ ] **Step 1: Add _valid_task_id and log_failure + has_failure_logged functions**

In `lib/ledger.py`, add after the imports (around line 17):

```python
_TASK_ID_RE = re.compile(r"^[A-Z]{2,4}-\d{1,4}$")


def _valid_task_id(task_id: str) -> bool:
    return bool(_TASK_ID_RE.match(task_id))
```

Add before the `# ── Internal Helpers` section (around line 565):

```python
def log_failure(
    project_dir: str,
    task_id: str,
    check_name: str,
    expected: str,
    actual: str,
    severity: str = "major",
) -> str:
    """Append structured QA failure to failures.md. Must be called before REWORK."""
    if severity not in ("minor", "major", "critical"):
        return json.dumps({"error": "severity must be minor, major, or critical"})
    failures_path = Path(project_dir) / "project-ledger" / "failures.md"
    failures_path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    header = "# QA Failures\n\n| Task | Check | Expected | Actual | Severity | Time |\n|------|-------|----------|--------|----------|------|\n"
    if not failures_path.exists():
        with open(failures_path, "w") as f:
            f.write(header)
    entry = f"| {task_id} | {check_name} | {expected} | {actual} | {severity} | {ts} |\n"
    with open(failures_path, "a") as f:
        f.write(entry)
    return json.dumps({"logged": True, "task_id": task_id, "check": check_name, "severity": severity})


def has_failure_logged(project_dir: str, task_id: str) -> bool:
    """Check if any failure has been logged for this task_id in failures.md."""
    failures_path = Path(project_dir) / "project-ledger" / "failures.md"
    if not failures_path.exists():
        return False
    return f"| {task_id} |" in failures_path.read_text()
```

- [ ] **Step 2: Add validation to _find_task_file**

Replace `_find_task_file` (around line 567):

```python
def _find_task_file(project_dir: str, task_id: str) -> Path | None:
    """Find a task file by ID across all department directories."""
    if not _valid_task_id(task_id):
        return None
    tasks_dir = Path(project_dir) / "project-ledger" / "tasks"
    if not tasks_dir.exists():
        return None
    for dept_dir in tasks_dir.iterdir():
        if not dept_dir.is_dir():
            continue
        path = dept_dir / f"{task_id}.md"
        if path.exists():
            return path
    return None
```

- [ ] **Step 3: Add validation to public functions**

At the top of `get_task` (line 159), `submit_worker_report` (line 179), `submit_qa_report` (line 193), `submit_manager_review` (line 210), add:

```python
    if not _valid_task_id(task_id):
        return json.dumps({"error": f"Invalid task_id format: '{task_id}'"})
```

- [ ] **Step 4: Run tests**

Run: `cd /home/Ricky/systems-orchestrator-v3 && python3 -m pytest tests/test_orchestrator.py -v --tb=short`
Expected: 43 passed

- [ ] **Step 5: Commit**

```bash
git add lib/ledger.py
git commit -m "fix(ledger): add task_id validation, log_failure, has_failure_logged (B3, S3)"
```

---

### Task 2: lib/ledger.py — Status guard, remove _unblock_dependents, length/type validation (M7, B7, M3, M4)

**Files:**
- Modify: `lib/ledger.py`

- [ ] **Step 1: Add status guard to submit_worker_report (M7)**

At the top of `submit_worker_report` (after the task_id validation added in Task 1), add:

```python
    path = _find_task_file(project_dir, task_id)
    if not path:
        return json.dumps({"error": f"Task {task_id} not found"})
    content = path.read_text()
    if "**Status**: VERIFIED" in content or "**Status**: ESCALATED" in content:
        return json.dumps({"error": f"Task {task_id} is already closed (VERIFIED/ESCALATED). Cannot reopen."})
```

Remove the duplicate `path = _find_task_file(...)` and `if not path:` check that follows — it's now handled above.

- [ ] **Step 2: Remove _unblock_dependents (B7)**

Delete the `_unblock_dependents` function (around line 606-610). In `submit_manager_review`, remove the call `_unblock_dependents(project_dir, task_id)`. Add a comment in its place:

```python
    # Unblocking is handled lazily by get_unblocked_tasks()
```

- [ ] **Step 3: Add length validation helper (M4)**

Add near the top of the file, after the constants:

```python
def _check_length(value: str, max_len: int, field_name: str) -> str | None:
    """Return error message if value exceeds max_len, else None."""
    if len(value) > max_len:
        return f"{field_name} exceeds maximum length ({len(value)} > {max_len})"
    return None
```

Add to `create_task` (after dept/size validation):
```python
    err = _check_length(description, 10_000, "description")
    if err:
        return json.dumps({"error": err})
```

Add to `submit_worker_report` (after status guard):
```python
    err = _check_length(report, 50_000, "report")
    if err:
        return json.dumps({"error": err})
```

Add to `submit_qa_report` (after task_id validation):
```python
    err = _check_length(report, 50_000, "report")
    if err:
        return json.dumps({"error": err})
```

- [ ] **Step 4: Add type validation to record_tool_outcome (M3)**

At the top of `record_tool_outcome` (around line 329), add:

```python
    if not isinstance(tool_name, str) or not tool_name:
        return json.dumps({"error": "tool_name must be a non-empty string"})
    if not isinstance(action, str) or not action:
        return json.dumps({"error": "action must be a non-empty string"})
    if not isinstance(success, bool):
        return json.dumps({"error": "success must be a boolean (true/false)"})
```

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/test_orchestrator.py -v --tb=short`
Expected: 43 passed

- [ ] **Step 6: Commit**

```bash
git add lib/ledger.py
git commit -m "fix(ledger): status guard, remove _unblock_dependents, add validation (M7, B7, M3, M4)"
```

---

### Task 3: lib/ledger.py + server.py — Clean imports (M1 partial)

**Files:**
- Modify: `lib/ledger.py:13`, `server.py:21-26,39,52`

- [ ] **Step 1: Remove unused `os` from lib/ledger.py**

Delete line 13: `import os`

- [ ] **Step 2: Clean server.py imports**

Remove these lines from server.py:
- Line 21: `import os`
- Line 22: `import random`
- Line 26: `from collections import defaultdict`

Change line 39 from:
```python
from lib.onboarding import OnboardingFlow, GoalAssessment, CLARIFYING_PROMPTS
```
to:
```python
from lib.onboarding import OnboardingFlow, GoalAssessment
```

Remove `execute_dispatch` from line 47-52 dispatch import block.

- [ ] **Step 3: Add log_failure and has_failure_logged imports to server.py**

In the `from lib.ledger import (...)` block (line 54), add:

```python
    log_failure as _log_failure,
    has_failure_logged as _has_failure_logged,
```

- [ ] **Step 4: Run tests**

Run: `python3 -c "import server; print('OK')" && python3 -m pytest tests/test_orchestrator.py --tb=short`
Expected: OK + 43 passed

- [ ] **Step 5: Commit**

```bash
git add lib/ledger.py server.py
git commit -m "chore: clean unused imports (M1 partial)"
```

---

### Task 4: server.py — File-based REWORK gate + sanitize suggest_packages (B4, S1)

**Files:**
- Modify: `server.py:82-83` (GATE_STATE), `server.py:580-605` (suggest_packages), `server.py:693-743` (log_failure + submit_manager_review)

- [ ] **Step 1: Remove failure_logged from GATE_STATE**

Change `GATE_STATE` (line 82-84) from:
```python
GATE_STATE: dict[str, Any] = {
    "failure_logged": {},    # task_id → True (must log_failure before REWORK)
    "tool_errors": {},       # tool_name → consecutive error count
    "onboarding": None,      # OnboardingFlow instance
}
```
to:
```python
GATE_STATE: dict[str, Any] = {
    "tool_errors": {},       # tool_name → consecutive error count
    "onboarding": None,      # OnboardingFlow instance
}
```

- [ ] **Step 2: Update log_failure MCP tool to call lib function**

Replace the `log_failure` MCP tool body (around line 693-718). Keep the `@mcp.tool()` decorator and docstring. Replace the body with:

```python
    return _log_failure(str(PROJECT_DIR), task_id, check_name, expected, actual, severity)
```

- [ ] **Step 3: Update submit_manager_review gate to use file check**

In the `submit_manager_review` MCP tool (around line 737), replace:
```python
    if verdict == "REWORK" and not GATE_STATE["failure_logged"].get(task_id):
```
with:
```python
    if verdict == "REWORK" and not _has_failure_logged(str(PROJECT_DIR), task_id):
```

Remove the line that clears the gate (around line 743):
```python
    GATE_STATE["failure_logged"].pop(task_id, None)
```

- [ ] **Step 4: Sanitize suggest_packages input (S1)**

In `suggest_packages` (around line 589), after `search_term = need.split()[0] if need.split() else need`, add:

```python
    import re as _re
    if not _re.match(r'^[a-zA-Z0-9_-]+$', search_term):
        return json.dumps({"error": f"Invalid search term: '{search_term}'. Use only letters, numbers, hyphens, underscores."})
```

- [ ] **Step 5: Run tests**

Run: `python3 -c "import server; print('OK')" && python3 -m pytest tests/ --tb=short`
Expected: OK + all tests pass

- [ ] **Step 6: Commit**

```bash
git add server.py
git commit -m "fix(server): file-based REWORK gate, sanitize suggest_packages (B4, S1)"
```

---

### Task 5: lib/dispatch.py — Remove --dangerously flag, validate dept, clean imports (S2, M6, M1)

**Files:**
- Modify: `lib/dispatch.py:13,89-94,393`

- [ ] **Step 1: Remove unused `os` import**

Delete line 13: `import os`

- [ ] **Step 2: Remove --dangerously-bypass-approvals-and-sandbox (S2)**

Change line 393 from:
```python
            cmd = [binary, "exec", "--dangerously-bypass-approvals-and-sandbox"]
```
to:
```python
            cmd = [binary, "exec"]
```

- [ ] **Step 3: Validate dept in _load_playbook (M6)**

Import DEPARTMENTS at the top of dispatch.py. Add after existing imports:
```python
from lib.ledger import DEPARTMENTS
```

Change `_load_playbook` (line 89-94) from:
```python
def _load_playbook(playbook_dir: str, dept: str, role: str) -> str:
    """Load a department playbook file."""
    path = Path(playbook_dir) / dept / f"{role}.md"
    if path.exists():
        return path.read_text()
    return f"(No {role} playbook for {dept})"
```
to:
```python
def _load_playbook(playbook_dir: str, dept: str, role: str) -> str:
    """Load a department playbook file."""
    if dept not in DEPARTMENTS:
        return f"(Unknown department '{dept}' — use your best judgment)"
    path = Path(playbook_dir) / dept / f"{role}.md"
    if path.exists():
        return path.read_text()
    return f"(No {role} playbook for {dept})"
```

- [ ] **Step 4: Run tests**

Run: `python3 -c "from lib.dispatch import execute_dispatch; print('OK')" && python3 -m pytest tests/ --tb=short`
Expected: OK + all tests pass

- [ ] **Step 5: Commit**

```bash
git add lib/dispatch.py
git commit -m "fix(dispatch): remove --dangerously flag, validate dept, clean imports (S2, M6, M1)"
```

---

### Task 6: lib/analyzer.py — Wire DIRECT_SIGNAL_KEYWORDS, add self-referencing verbs (B5, B6)

**Files:**
- Modify: `lib/analyzer.py:80-82` (ACTION_KEYWORDS), `lib/analyzer.py:176-200` (classify_complexity)

- [ ] **Step 1: Add self-referencing verbs to ACTION_KEYWORDS (B6)**

Check each verb. Add the verb itself if missing from its keyword list:

```python
ACTION_KEYWORDS: dict[str, list[str]] = {
    "observe": ["observe", "monitor", "watch", "log", "trace", "track", "inspect", "telemetry", "metrics"],
    "measure": ["measure", "benchmark", "profile", "perf", "latency", "throughput", "load-test"],
    "analyze": ["analyze", "audit", "scan", "review", "assess", "investigate", "diagnose", "debug"],
    "test": ["test", "check", "validate", "assert", "expect", "spec", "coverage", "unit", "integration", "e2e"],
    "verify": ["verify", "confirm", "ensure", "guarantee", "certify", "approve"],
    "transform": ["transform", "create", "build", "generate", "write", "implement", "deploy", "install", "configure",
                   "update", "modify", "refactor", "fix", "patch", "migrate", "upgrade", "convert"],
    "plan": ["plan", "design", "architect", "spec", "rfc", "proposal", "roadmap", "estimate", "scope"],
}
```

- [ ] **Step 2: Wire DIRECT_SIGNAL_KEYWORDS into classify_complexity (B5)**

In `classify_complexity` (around line 188), add BEFORE the FULL signal check:

```python
    # DIRECT fast-track: explicit simple-task keywords
    if any(kw in task_lower for kw in DIRECT_SIGNAL_KEYWORDS):
        if element_count <= 1 and action_count <= 1:
            return "DIRECT"
```

This goes after the variable assignments but before the `has_full_signal` check.

- [ ] **Step 3: Run tests**

Run: `python3 -c "from lib.analyzer import classify_complexity; print('OK')" && python3 -m pytest tests/ --tb=short && python3 tests/test_analyze.py 2>&1 | tail -3`
Expected: OK + 43 unit tests pass + accuracy >= 85%

- [ ] **Step 4: Commit**

```bash
git add lib/analyzer.py
git commit -m "fix(analyzer): wire DIRECT_SIGNAL_KEYWORDS, add self-referencing verbs (B5, B6)"
```

---

### Task 7: orchestrator_loop.py — Fix key mismatch, output extraction, use lib log_failure (B1, B2, B4-loop, M1)

**Files:**
- Modify: `orchestrator_loop.py`

- [ ] **Step 1: Fix imports (M1)**

Replace the import section (lines 20-25) with:

```python
import argparse
import datetime
import json
import re
import sys
import time
from pathlib import Path
```

Remove `os` and `subprocess` (unused). Add `datetime` and `re` at module level (were inline).

Add `log_failure` to the ledger import (around line 41):
```python
from lib.ledger import (
    get_unblocked_tasks, get_task, get_project_goal,
    submit_worker_report, submit_qa_report, submit_manager_review,
    record_tool_outcome, log_failure,
)
```

- [ ] **Step 2: Fix step functions to extract output string (B2)**

Replace `_step_researcher` (line 60-66):
```python
def _step_researcher(project_dir: str, playbook_dir: str, task_id: str, task_content: str, goal: str) -> str:
    """Research phase: gather context for planning."""
    print(f"  [researcher] Dispatching research for {task_id}...")
    packet = craft_researcher_prompt(task_id, task_content, playbook_dir, goal)
    result = execute_dispatch(packet)
    output = result.get("output", "") if isinstance(result, dict) else str(result)
    print(f"  [researcher] Done ({len(output)} chars)")
    return output
```

Replace `_step_planner` (line 69-75):
```python
def _step_planner(project_dir: str, playbook_dir: str, task_id: str, task_content: str, goal: str) -> str:
    """Planning phase: create execution plan."""
    print(f"  [planner] Creating plan for {task_id}...")
    packet = craft_planner_prompt(task_id, task_content, playbook_dir, goal)
    result = execute_dispatch(packet)
    output = result.get("output", "") if isinstance(result, dict) else str(result)
    print(f"  [planner] Done ({len(output)} chars)")
    return output
```

Replace `_step_worker` (line 78-85):
```python
def _step_worker(project_dir: str, playbook_dir: str, task_id: str, task_content: str, reasoning_level: str) -> str:
    """Execution: do the work at the given reasoning level."""
    print(f"  [worker] Executing {task_id} at {reasoning_level}...")
    packet = craft_worker_prompt(task_id, task_content, playbook_dir, reasoning_level)
    result = execute_dispatch(packet)
    output = result.get("output", "") if isinstance(result, dict) else str(result)
    print(f"  [worker] Done ({len(output)} chars)")
    submit_worker_report(project_dir, task_id, output)
    return output
```

Replace `_step_qa` (line 88-100):
```python
def _step_qa(project_dir: str, playbook_dir: str, task_id: str, task_content: str,
             worker_report: str, reasoning_level: str) -> tuple[str, float]:
    """QA: verify the work at a stepped-down reasoning level."""
    qa_level = QA_LEVEL_DOWN.get(reasoning_level, reasoning_level)
    print(f"  [qa] Verifying {task_id} at {qa_level} (stepped from {reasoning_level})...")
    packet = craft_qa_prompt(task_id, task_content, worker_report, playbook_dir, qa_level)
    result = execute_dispatch(packet)
    output = result.get("output", "") if isinstance(result, dict) else str(result)
    print(f"  [qa] Done ({len(output)} chars)")
    score = _extract_qa_score(output)
    submit_qa_report(project_dir, task_id, output, score)
    return output, score
```

Replace `_step_manager` (line 103-131):
```python
def _step_manager(project_dir: str, task_id: str, task_content: str,
                  worker_report: str, qa_report: str, rework_count: int, goal: str) -> str:
    """Manager review: VERIFIED / REWORK / ESCALATED."""
    print(f"  [manager] Reviewing {task_id} (rework #{rework_count})...")
    packet = craft_manager_prompt(task_id, task_content, worker_report, qa_report, rework_count, goal)
    result = execute_dispatch(packet)
    output = result.get("output", "") if isinstance(result, dict) else str(result)
    print(f"  [manager] Done")

    verdict = _extract_verdict(output)

    # If REWORK, log a failure before submitting review (gate enforcement)
    if verdict == "REWORK":
        log_failure(project_dir, task_id, "manager_review", "pass", "rework_needed", "major")

    submit_manager_review(project_dir, task_id, verdict, output)
    print(f"  [manager] Verdict: {verdict}")
    return verdict
```

- [ ] **Step 3: Fix poll_loop dict key and task_id extraction (B1)**

Replace line 269:
```python
        tasks = parsed.get("unblocked", [])
```

Replace lines 277-278:
```python
        for task_info in tasks:
            task_id = task_info["task_id"] if isinstance(task_info, dict) else str(task_info)
```

- [ ] **Step 4: Run tests**

Run: `python3 -c "from orchestrator_loop import poll_loop; print('OK')" && python3 -m pytest tests/ --tb=short`
Expected: OK + all tests pass

- [ ] **Step 5: Commit**

```bash
git add orchestrator_loop.py
git commit -m "fix(loop): correct dict key, extract output strings, use lib log_failure (B1, B2, B4, M1)"
```

---

### Task 8: Cleanup — delete prompts/, verify TOCTOU (M2, M5)

**Files:**
- Delete: `prompts/`
- Verify: append-mode usage in lib/ledger.py

- [ ] **Step 1: Delete empty prompts/ directory (M2)**

```bash
rm -rf /home/Ricky/systems-orchestrator-v3/prompts
```

- [ ] **Step 2: Verify append-mode usage (M5)**

Run: `grep -n 'open.*"w"' lib/ledger.py`

Verify the only `"w"` opens are for creating new files (headers). All data appends should use `"a"`. The `log_failure` function added in Task 1 uses `"w"` only for the initial header and `"a"` for entries — this is correct.

For task files (read-modify-write in `submit_worker_report`, `submit_qa_report`, `_set_status`), accept the race and add a comment at the top of each:

```python
    # Note: read-modify-write is not atomic. Concurrent calls to the same task
    # can lose data. Acceptable for single-user tool; use file locking if needed.
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: delete empty prompts/, document TOCTOU acceptance (M2, M5)"
```

---

### Task 9: Full verification

- [ ] **Step 1: Import check**

Run: `python3 -c "import server; print('OK')"`
Expected: OK

- [ ] **Step 2: Unit tests**

Run: `python3 -m pytest tests/test_orchestrator.py -v`
Expected: 43 passed

- [ ] **Step 3: Accuracy tests**

Run: `python3 tests/test_analyze.py 2>&1 | tail -3`
Expected: >= 85% cases, >= 90% checks

- [ ] **Step 4: Gate enforcement manual test**

```python
python3 -c "
import tempfile, json
from lib.ledger import *

d = tempfile.mkdtemp()
create_project_ledger('Test', [], ['engineering'], d)
create_task(d, 'engineering', 'Gate test', 'Test', 'M')
submit_worker_report(d, 'ENG-001', 'Done')
submit_qa_report(d, 'ENG-001', 'Failed', 0.3)

# REWORK without log_failure — should work at lib level (gate is at MCP level)
r = json.loads(submit_manager_review(d, 'ENG-001', 'REWORK', 'Fix it'))
print(f'REWORK: {r[\"verdict\"]}')

# Verify has_failure_logged works
print(f'has_failure before: {has_failure_logged(d, \"ENG-001\")}')
log_failure(d, 'ENG-001', 'test_check', 'pass', 'fail')
print(f'has_failure after: {has_failure_logged(d, \"ENG-001\")}')
"
```

- [ ] **Step 5: Security manual tests**

```python
python3 -c "
from lib.ledger import _valid_task_id, get_task
import tempfile, json
from lib.ledger import create_project_ledger

d = tempfile.mkdtemp()
create_project_ledger('Test', [], ['engineering'], d)

# Path traversal blocked
print(f'../../etc/passwd valid: {_valid_task_id(\"../../etc/passwd\")}')  # False
r = json.loads(get_task(d, '../../etc/passwd'))
print(f'traversal result: {r}')  # error
print(f'ENG-001 valid: {_valid_task_id(\"ENG-001\")}')  # True
"
```

- [ ] **Step 6: Push to GitHub**

```bash
git push origin main
```
