"""Project ledger v2 — directory-based task tracking with tool-level outcome learning.

Improvements over v1:
- Tool-level outcome tracking (not just department-level)
- Confidence decay for stale learned data
- Structured failure taxonomy for better learning
- Sprint-level aggregation
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_TASK_ID_RE = re.compile(r"^[A-Z]{2,4}-\d{1,4}$")

def _valid_task_id(task_id: str) -> bool:
    return bool(_TASK_ID_RE.match(task_id))

def _check_length(value: str, max_len: int, field_name: str) -> str | None:
    """Return error message if value exceeds max_len, else None."""
    if len(value) > max_len:
        return f"{field_name} exceeds maximum length ({len(value)} > {max_len})"
    return None

# ── Department Registry ──────────────────────────────────────────────────

DEPARTMENTS = {
    "engineering": "ENG",
    "design": "DES",
    "marketing": "MKT",
    "qa-testing": "QAT",
    "devops": "OPS",
    "product": "PRD",
    "security": "SEC",
}

TASK_STATUSES = ("PENDING", "IN_PROGRESS", "IN_REVIEW", "VERIFIED", "REWORK", "ESCALATED", "BLOCKED")

TASK_SIZES = {
    "S": {"agents": ["executor"], "description": "Worker only, no QA"},
    "M": {"agents": ["executor", "verifier"], "description": "Worker + QA"},
    "L": {"agents": ["executor", "verifier", "reviewer"], "description": "Worker + QA + Manager"},
    "XL": {"agents": ["researcher", "planner", "executor", "verifier", "reviewer"], "description": "Full pipeline"},
}


# ── Ledger Operations ────────────────────────────────────────────────────

def create_project_ledger(
    goal: str,
    rules: list[str] | None = None,
    departments: list[str] | None = None,
    project_dir: str = ".",
) -> str:
    """Create project-ledger/ directory with index.md, tasks/, sprints/, outcomes/."""
    base = Path(project_dir) / "project-ledger"
    if base.exists():
        return json.dumps({"error": "Ledger already exists at project-ledger/", "path": str(base)})

    base.mkdir(parents=True)
    (base / "tasks").mkdir()
    (base / "sprints").mkdir()
    (base / "outcomes").mkdir()

    depts = departments or list(DEPARTMENTS.keys())
    rules_str = "\n".join(f"- {r}" for r in (rules or ["No rules specified"]))
    dept_str = "\n".join(f"- {d} ({DEPARTMENTS.get(d, '???')})" for d in depts)

    index = f"""# Project Ledger

## Goal
{goal}

## Rules
{rules_str}

## Departments
{dept_str}

## Created
{datetime.now(timezone.utc).isoformat()}
"""
    (base / "index.md").write_text(index)
    (base / "dependency-graph.md").write_text("# Dependency Graph\n\n```\n(empty)\n```\n")

    # Init outcome files
    (base / "outcomes" / "outcomes.jsonl").write_text("")
    (base / "outcomes" / "tool_outcomes.jsonl").write_text("")

    # Create dept subdirs under tasks/
    for d in depts:
        (base / "tasks" / d).mkdir(exist_ok=True)

    return json.dumps({
        "created": str(base),
        "goal": goal,
        "departments": depts,
        "structure": ["index.md", "tasks/", "sprints/", "outcomes/", "dependency-graph.md"],
    }, indent=2)


def create_task(
    project_dir: str,
    dept: str,
    title: str,
    description: str,
    size: str = "M",
    blocked_by: list[str] | None = None,
    blocks: list[str] | None = None,
    files_touched: list[str] | None = None,
) -> str:
    """Create a new task in the given department."""
    prefix = DEPARTMENTS.get(dept)
    if not prefix:
        return json.dumps({"error": f"Unknown department: {dept}", "valid": list(DEPARTMENTS.keys())})
    if size not in TASK_SIZES:
        return json.dumps({"error": f"Invalid size: {size}", "valid": list(TASK_SIZES.keys())})
    err = _check_length(description, 10_000, "description")
    if err:
        return json.dumps({"error": err})

    tasks_dir = Path(project_dir) / "project-ledger" / "tasks" / dept
    if not tasks_dir.exists():
        return json.dumps({"error": f"Department directory not found: {tasks_dir}. Create ledger first."})

    # Find next task number
    existing = sorted(tasks_dir.glob(f"{prefix}-*.md"))
    next_num = 1
    if existing:
        last = existing[-1].stem
        match = re.search(r"(\d+)", last)
        if match:
            next_num = int(match.group(1)) + 1

    task_id = f"{prefix}-{next_num:03d}"
    blocked_str = ", ".join(blocked_by) if blocked_by else "none"
    blocks_str = ", ".join(blocks) if blocks else "none"
    files_str = ", ".join(files_touched) if files_touched else "none"

    task_md = f"""# {task_id}: {title}

## Metadata
- **Department**: {dept}
- **Size**: {size} ({TASK_SIZES[size]['description']})
- **Status**: PENDING
- **Created**: {datetime.now(timezone.utc).isoformat()}
- **Blocked by**: {blocked_str}
- **Blocks**: {blocks_str}
- **Files touched**: {files_str}

## Description
{description}
"""
    (tasks_dir / f"{task_id}.md").write_text(task_md)

    # Update dependency graph
    _update_dep_graph(project_dir, task_id, blocked_by or [], blocks or [])

    return json.dumps({
        "task_id": task_id,
        "department": dept,
        "size": size,
        "status": "PENDING",
        "file": str(tasks_dir / f"{task_id}.md"),
    }, indent=2)


def get_task(project_dir: str, task_id: str) -> str:
    """Read a task file."""
    if not _valid_task_id(task_id):
        return json.dumps({"error": f"Invalid task_id format: '{task_id}'"})
    path = _find_task_file(project_dir, task_id)
    if not path:
        return json.dumps({"error": f"Task {task_id} not found"})
    return path.read_text()


def get_project_goal(project_dir: str) -> str:
    """Extract the project goal from index.md."""
    index = Path(project_dir) / "project-ledger" / "index.md"
    if not index.exists():
        return "(no project goal set)"
    text = index.read_text()
    match = re.search(r"## Goal\n(.+?)(?:\n##|\Z)", text, re.DOTALL)
    return match.group(1).strip() if match else "(goal not found in index.md)"


# ── Status Updates ───────────────────────────────────────────────────────

def submit_worker_report(project_dir: str, task_id: str, report: str) -> str:
    """Append worker report, change status to IN_REVIEW."""
    if not _valid_task_id(task_id):
        return json.dumps({"error": f"Invalid task_id format: '{task_id}'"})
    path = _find_task_file(project_dir, task_id)
    if not path:
        return json.dumps({"error": f"Task {task_id} not found"})

    content = path.read_text()
    if "**Status**: VERIFIED" in content or "**Status**: ESCALATED" in content:
        return json.dumps({"error": f"Task {task_id} is already closed (VERIFIED/ESCALATED). Cannot reopen."})
    err = _check_length(report, 50_000, "report")
    if err:
        return json.dumps({"error": err})
    content = _set_status(content, "IN_REVIEW")
    content += f"\n## Worker Report\n{report}\n"
    path.write_text(content)

    return json.dumps({"task_id": task_id, "status": "IN_REVIEW", "next": "dispatch_qa"})


def submit_qa_report(project_dir: str, task_id: str, report: str, score: float) -> str:
    """Append QA report."""
    if not _valid_task_id(task_id):
        return json.dumps({"error": f"Invalid task_id format: '{task_id}'"})
    err = _check_length(report, 50_000, "report")
    if err:
        return json.dumps({"error": err})
    path = _find_task_file(project_dir, task_id)
    if not path:
        return json.dumps({"error": f"Task {task_id} not found"})

    content = path.read_text()
    content += f"\n## QA Report (score: {score:.2f})\n{report}\n"
    path.write_text(content)

    return json.dumps({
        "task_id": task_id,
        "qa_score": score,
        "next": "submit_manager_review" if score >= 0.9 else "log_failure then submit_manager_review",
    })


def submit_manager_review(
    project_dir: str,
    task_id: str,
    verdict: str,
    notes: str = "",
    rework_items: list[str] | None = None,
    playbook_updates: dict[str, str] | None = None,
) -> str:
    """Record manager verdict, update status, record outcome."""
    if not _valid_task_id(task_id):
        return json.dumps({"error": f"Invalid task_id format: '{task_id}'"})
    if verdict not in ("VERIFIED", "REWORK", "ESCALATED"):
        return json.dumps({"error": f"Invalid verdict: {verdict}", "valid": ["VERIFIED", "REWORK", "ESCALATED"]})

    path = _find_task_file(project_dir, task_id)
    if not path:
        return json.dumps({"error": f"Task {task_id} not found"})

    content = path.read_text()
    content = _set_status(content, verdict)

    rework_str = ""
    if rework_items:
        rework_str = "\n### Rework Items\n" + "\n".join(f"- [ ] {r}" for r in rework_items)

    content += f"\n## Manager Review\n- **Verdict**: {verdict}\n- **Notes**: {notes}\n{rework_str}\n"
    path.write_text(content)

    # Record outcome
    _record_outcome(project_dir, task_id, verdict, notes)

    # Unblocking is handled lazily by get_unblocked_tasks()

    return json.dumps({
        "task_id": task_id,
        "verdict": verdict,
        "rework_items": rework_items or [],
    }, indent=2)


# ── Query Functions ──────────────────────────────────────────────────────

def get_unblocked_tasks(project_dir: str, dept: str | None = None) -> str:
    """Find PENDING tasks with all dependencies VERIFIED."""
    ledger = Path(project_dir) / "project-ledger" / "tasks"
    if not ledger.exists():
        return json.dumps({"error": "No ledger found"})

    results = []
    dirs = [ledger / dept] if dept and (ledger / dept).exists() else sorted(ledger.iterdir())

    for dept_dir in dirs:
        if not dept_dir.is_dir():
            continue
        for task_file in sorted(dept_dir.glob("*.md")):
            content = task_file.read_text()
            if "**Status**: PENDING" not in content:
                continue

            # Check blocked_by
            match = re.search(r"\*\*Blocked by\*\*: (.+)", content)
            blocked_by = match.group(1).strip() if match else "none"
            if blocked_by == "none":
                results.append({"task_id": task_file.stem, "dept": dept_dir.name})
                continue

            # Check if all blockers are VERIFIED
            blocker_ids = [b.strip() for b in blocked_by.split(",")]
            all_clear = True
            for bid in blocker_ids:
                bpath = _find_task_file(project_dir, bid)
                if bpath and "**Status**: VERIFIED" not in bpath.read_text():
                    all_clear = False
                    break
            if all_clear:
                results.append({"task_id": task_file.stem, "dept": dept_dir.name})

    return json.dumps({"unblocked": results, "count": len(results)}, indent=2)


def get_department_status(project_dir: str, dept: str) -> str:
    """Count tasks by status for a department."""
    dept_dir = Path(project_dir) / "project-ledger" / "tasks" / dept
    if not dept_dir.exists():
        return json.dumps({"error": f"Department {dept} not found"})

    counts: dict[str, int] = {}
    for task_file in dept_dir.glob("*.md"):
        content = task_file.read_text()
        for status in TASK_STATUSES:
            if f"**Status**: {status}" in content:
                counts[status] = counts.get(status, 0) + 1
                break

    return json.dumps({"department": dept, "counts": counts, "total": sum(counts.values())}, indent=2)


def get_outcomes(project_dir: str, dept: str = "", verdict: str = "") -> str:
    """Read outcomes.jsonl with optional filtering."""
    outcomes_path = Path(project_dir) / "project-ledger" / "outcomes" / "outcomes.jsonl"
    if not outcomes_path.exists():
        return json.dumps({"outcomes": [], "count": 0})

    results = []
    for line in outcomes_path.read_text().strip().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if dept and entry.get("dept") != dept:
            continue
        if verdict and entry.get("verdict") != verdict:
            continue
        results.append(entry)

    return json.dumps({"outcomes": results, "count": len(results)}, indent=2)


# ── Tool-Level Outcome Learning ──────────────────────────────────────────

def record_tool_outcome(
    project_dir: str,
    tool_name: str,
    task_id: str,
    action: str,
    success: bool,
    context: str = "",
) -> str:
    """Record whether a specific tool succeeded/failed for a task action.
    This powers the tool-level learning loop — tools that fail often get
    scored lower for similar actions.
    """
    if not isinstance(tool_name, str) or not tool_name:
        return json.dumps({"error": "tool_name must be a non-empty string"})
    if not isinstance(action, str) or not action:
        return json.dumps({"error": "action must be a non-empty string"})
    if not isinstance(success, bool):
        return json.dumps({"error": "success must be a boolean (true/false)"})
    outcomes_path = Path(project_dir) / "project-ledger" / "outcomes" / "tool_outcomes.jsonl"
    outcomes_path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "tool": tool_name,
        "task_id": task_id,
        "action": action,
        "success": success,
        "context": context,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    with open(outcomes_path, "a") as f:
        f.write(json.dumps(entry) + "\n")

    return json.dumps({"recorded": True, **entry})


def get_tool_scores(project_dir: str, tool_name: str = "") -> str:
    """Get success rates per tool, optionally filtered to a specific tool.
    Returns win_rate used by the scoring engine to adjust tool rankings.
    """
    outcomes_path = Path(project_dir) / "project-ledger" / "outcomes" / "tool_outcomes.jsonl"
    if not outcomes_path.exists():
        return json.dumps({"tools": {}, "note": "No tool outcomes recorded yet"})

    # Aggregate
    tools: dict[str, dict[str, int]] = {}
    for line in outcomes_path.read_text().strip().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        tn = entry["tool"]
        if tool_name and tn != tool_name:
            continue
        if tn not in tools:
            tools[tn] = {"success": 0, "failure": 0}
        if entry["success"]:
            tools[tn]["success"] += 1
        else:
            tools[tn]["failure"] += 1

    result = {}
    for tn, counts in tools.items():
        total = counts["success"] + counts["failure"]
        result[tn] = {
            "success": counts["success"],
            "failure": counts["failure"],
            "total": total,
            "win_rate": round(counts["success"] / total, 3) if total > 0 else 0.5,
        }

    return json.dumps({"tools": result}, indent=2)


# ── Project Knowledge ───────────────────────────────────────────────────
# These capture what the system IS, not just what tasks are in flight.
# Together with the task lifecycle, they form a living project description.

def record_architecture(
    project_dir: str,
    component: str,
    module: str,
    status: str = "OK",
    wired: bool = True,
    notes: str = "",
) -> str:
    """Record a system component — what exists, where it lives, whether it's wired.
    Call this as you discover or build components. The architecture file becomes
    the definitive map of the system.

    Args:
        component: Component name (e.g. "EXECUTOR", "AUTH_MIDDLEWARE", "DATABASE")
        module: Python/JS module path (e.g. "engine.executor.WorkflowExecutor")
        status: OK | BROKEN | STUB | NOT_IMPLEMENTED
        wired: Whether it's connected in the boot path
        notes: Additional context
    """
    arch_path = Path(project_dir) / "project-ledger" / "architecture.md"
    arch_path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    if not arch_path.exists():
        arch_path.write_text("# System Architecture\n\n"
                             "| Component | Module | Status | Wired | Notes | Updated |\n"
                             "|-----------|--------|--------|-------|-------|--------|\n")

    entry = f"| {component} | `{module}` | {status} | {'Yes' if wired else 'No'} | {notes} | {ts} |\n"
    with open(arch_path, "a") as f:
        f.write(entry)

    return json.dumps({
        "recorded": True,
        "component": component,
        "module": module,
        "status": status,
        "file": str(arch_path),
    })


def record_decision(
    project_dir: str,
    question: str,
    decision: str,
    reasoning: str = "",
    alternatives: str = "",
    decided_by: str = "",
) -> str:
    """Record a design decision — what was decided, why, and what alternatives were rejected.
    These accumulate into a decision log that explains why the system is shaped this way.

    Args:
        question: What question was being answered (e.g. "Which database for user sessions?")
        decision: What was decided (e.g. "SQLite for dev, Postgres for prod")
        reasoning: Why this was chosen
        alternatives: What was considered and rejected
        decided_by: Who/what made the call (e.g. "researcher agent", "user", "planner")
    """
    decisions_path = Path(project_dir) / "project-ledger" / "decisions.md"
    decisions_path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    if not decisions_path.exists():
        decisions_path.write_text("# Decision Log\n\n")

    entry = f"""### {question}
- **Decision**: {decision}
- **Reasoning**: {reasoning or 'Not recorded'}
- **Alternatives**: {alternatives or 'None recorded'}
- **Decided by**: {decided_by or 'Unknown'}
- **Date**: {ts}

"""
    with open(decisions_path, "a") as f:
        f.write(entry)

    return json.dumps({
        "recorded": True,
        "question": question,
        "decision": decision,
        "file": str(decisions_path),
    })


def update_project_state(
    project_dir: str,
    category: str,
    key: str,
    value: str,
    notes: str = "",
) -> str:
    """Record a project state observation — test results, bug found, feature completed,
    dependency added, etc. These form a timeline of what happened to the project.

    Args:
        category: bugs | tests | features | dependencies | deployments | other
        key: What specifically (e.g. "test_auth_flow", "CVE-2024-1234", "v2.1.0")
        value: The state (e.g. "PASSING", "FIXED", "DEPLOYED", "ADDED")
        notes: Context
    """
    valid_categories = {"bugs", "tests", "features", "dependencies", "deployments", "other"}
    if category not in valid_categories:
        return json.dumps({"error": f"Invalid category. Use: {', '.join(sorted(valid_categories))}"})

    state_path = Path(project_dir) / "project-ledger" / "state.jsonl"
    state_path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "category": category,
        "key": key,
        "value": value,
        "notes": notes,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    with open(state_path, "a") as f:
        f.write(json.dumps(entry) + "\n")

    return json.dumps({"recorded": True, **entry})


def get_project_knowledge(project_dir: str) -> str:
    """Read the full project knowledge — architecture, decisions, and recent state.
    This is what you'd read to understand the project at a glance.
    """
    base = Path(project_dir) / "project-ledger"
    result: dict[str, Any] = {}

    # Goal
    result["goal"] = get_project_goal(project_dir)

    # Architecture
    arch_path = base / "architecture.md"
    if arch_path.exists():
        result["architecture"] = arch_path.read_text()

    # Decisions
    decisions_path = base / "decisions.md"
    if decisions_path.exists():
        result["decisions"] = decisions_path.read_text()

    # Recent state (last 20 entries)
    state_path = base / "state.jsonl"
    if state_path.exists():
        lines = state_path.read_text().strip().split("\n")
        recent = [json.loads(l) for l in lines[-20:] if l.strip()]
        result["recent_state"] = recent

    # Task summary
    tasks_dir = base / "tasks"
    if tasks_dir.exists():
        counts: dict[str, int] = {}
        for dept_dir in tasks_dir.iterdir():
            if not dept_dir.is_dir():
                continue
            for tf in dept_dir.glob("*.md"):
                content = tf.read_text()
                for status in TASK_STATUSES:
                    if f"**Status**: {status}" in content:
                        counts[status] = counts.get(status, 0) + 1
                        break
        result["task_summary"] = counts

    return json.dumps(result, indent=2)


def log_failure(project_dir: str, task_id: str, check_name: str, expected: str, actual: str, severity: str = "major") -> str:
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


# ── Internal Helpers ─────────────────────────────────────────────────────

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


def _set_status(content: str, new_status: str) -> str:
    """Replace the **Status**: line in task content."""
    return re.sub(r"\*\*Status\*\*: \w+", f"**Status**: {new_status}", content)


def _record_outcome(project_dir: str, task_id: str, verdict: str, notes: str):
    """Append to outcomes.jsonl."""
    outcomes_path = Path(project_dir) / "project-ledger" / "outcomes" / "outcomes.jsonl"
    outcomes_path.parent.mkdir(parents=True, exist_ok=True)

    # Extract dept from task_id (ENG-001 → engineering)
    prefix = task_id.split("-")[0]
    dept = next((k for k, v in DEPARTMENTS.items() if v == prefix), "unknown")

    entry = {
        "task_id": task_id,
        "dept": dept,
        "verdict": verdict,
        "notes": notes,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    with open(outcomes_path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def _update_dep_graph(project_dir: str, task_id: str, blocked_by: list[str], blocks: list[str]):
    """Append to the dependency graph markdown."""
    graph_path = Path(project_dir) / "project-ledger" / "dependency-graph.md"
    if not graph_path.exists():
        return

    lines = []
    for dep in blocked_by:
        lines.append(f"  {dep} --> {task_id}")
    for dep in blocks:
        lines.append(f"  {task_id} --> {dep}")

    if lines:
        content = graph_path.read_text()
        insert = "\n".join(lines) + "\n"
        content = content.replace("(empty)\n```", f"{insert}```")
        graph_path.write_text(content)
