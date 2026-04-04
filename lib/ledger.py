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
    path = _find_task_file(project_dir, task_id)
    if not path:
        return json.dumps({"error": f"Task {task_id} not found"})

    content = path.read_text()
    content = _set_status(content, "IN_REVIEW")
    content += f"\n## Worker Report\n{report}\n"
    path.write_text(content)

    return json.dumps({"task_id": task_id, "status": "IN_REVIEW", "next": "dispatch_qa"})


def submit_qa_report(project_dir: str, task_id: str, report: str, score: float) -> str:
    """Append QA report."""
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

    # If VERIFIED, unblock dependent tasks
    if verdict == "VERIFIED":
        _unblock_dependents(project_dir, task_id)

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


# ── Internal Helpers ─────────────────────────────────────────────────────

def _find_task_file(project_dir: str, task_id: str) -> Path | None:
    """Find a task file by ID across all department directories."""
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


def _unblock_dependents(project_dir: str, task_id: str):
    """When a task is VERIFIED, check if any tasks it blocks can now start."""
    # This is passive — get_unblocked_tasks does the real check.
    # But we could log it for visibility.
    pass


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
