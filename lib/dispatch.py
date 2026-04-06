"""Multi-model dispatch — route agents to the right model CLI.

Model Routing Strategy:
- Claude CLI: reasoning, planning, QA, management, research, security analysis
- Codex CLI: code generation, execution, file operations, refactoring, tests

Both are subscription models — no API keys needed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from lib.ledger import DEPARTMENTS

# ── Config Loading ──────────────────────────────────────────────────────

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


def _load_dispatch_config() -> dict:
    """Load dispatch config from setup, with sensible defaults."""
    defaults = {
        "permission_mode": "bypassPermissions",
        "timeout_seconds": 300,
        "max_parallel": 4,
    }
    if _CONFIG_PATH.exists():
        try:
            config = json.loads(_CONFIG_PATH.read_text())
            return {**defaults, **config.get("dispatch", {})}
        except (json.JSONDecodeError, KeyError):
            pass
    return defaults


_DISPATCH_CONFIG = _load_dispatch_config()

# ── Model Registry ───────────────────────────────────────────────────────

MODELS = {
    "claude": {
        "binary": "claude",
        "exec_flag": "-p",  # piped prompt mode
        "strengths": ["reasoning", "planning", "analysis", "qa", "review", "security",
                       "architecture", "decomposition", "natural_language", "research"],
        "models": {
            "opus": "opus",
            "sonnet": "sonnet",
            "haiku": "haiku",
        },
        "check": lambda: shutil.which("claude") is not None,
    },
    "codex": {
        "binary": "codex",
        "exec_flag": "exec",  # non-interactive mode
        "strengths": ["code_generation", "execution", "refactoring", "testing",
                       "file_operations", "debugging", "code_review", "implementation"],
        "models": {
            "gpt-5.4": "gpt-5.4",
            "o4-mini": "o4-mini",
            "o3": "o3",
            "gpt-4.1": "gpt-4.1",
        },
        "check": lambda: shutil.which("codex") is not None,
    },
}

# ── Agent → Model Routing ────────────────────────────────────────────────

# Detect Codex availability once at import time
_CODEX_AVAILABLE = shutil.which("codex") is not None

# When Codex is available, use it for execution. Otherwise, all roles use Claude.
if _CODEX_AVAILABLE:
    AGENT_ROUTING = {
        "researcher": ("claude", "sonnet"),
        "planner": ("claude", "opus"),
        "executor": ("codex", "gpt-5.4"),
        "verifier": ("claude", "sonnet"),
        "reviewer": ("claude", "opus"),
    }
else:
    # Codex not installed — route everything through Claude
    AGENT_ROUTING = {
        "researcher": ("claude", "sonnet"),
        "planner": ("claude", "opus"),
        "executor": ("claude", "sonnet"),   # Claude handles execution when Codex unavailable
        "verifier": ("claude", "sonnet"),
        "reviewer": ("claude", "opus"),
    }

# Override for specific task types — respects Codex availability
def _route_for_type(preferred: str) -> str:
    """Return preferred model if available, else fallback to claude."""
    if preferred == "codex" and not _CODEX_AVAILABLE:
        return "claude"
    return preferred

TASK_TYPE_ROUTING = {
    "code_generation": _route_for_type("codex"),
    "refactoring": _route_for_type("codex"),
    "test_writing": _route_for_type("codex"),
    "implementation": _route_for_type("codex"),
    "code_review": _route_for_type("codex"),
    "security_scan": "claude",
    "architecture": "claude",
    "research": "claude",
    "planning": "claude",
    "qa_verification": "claude",
    "documentation": "claude",
    "analysis": "claude",
}

# ── QA Step-Down Map ─────────────────────────────────────────────────────
# QA runs at one level below the worker for cost efficiency
QA_LEVEL_DOWN = {
    "opus": "sonnet",
    "sonnet": "haiku",
    "haiku": "haiku",
    "gpt-5.4": "o4-mini",
    "o3": "o4-mini",
    "o4-mini": "o4-mini",
    "gpt-4.1": "o4-mini",
}


# ── Prompt Templates ─────────────────────────────────────────────────────

def _load_playbook(playbook_dir: str, dept: str, role: str) -> str:
    """Load a department playbook file."""
    if dept not in DEPARTMENTS:
        return f"(Unknown department '{dept}' — use your best judgment)"
    path = Path(playbook_dir) / dept / f"{role}.md"
    if path.exists():
        return path.read_text()
    return f"(No {role} playbook for {dept})"


def _get_reasoning_depth(level: str) -> str:
    """Return depth instruction based on reasoning level."""
    depths = {
        "haiku": "Be concise. One-pass solution. Skip edge cases unless obvious.",
        "sonnet": "Standard depth. Cover main cases. Note edge cases but don't over-engineer.",
        "opus": "Deep analysis. Consider edge cases, failure modes, alternatives. Be thorough.",
        "gpt-5.4": "Full-capability implementation. Leverage deep understanding for correctness, style, and completeness.",
        "o4-mini": "Efficient implementation. Focus on correctness and clean code.",
        "o3": "Thorough implementation with edge case handling and optimization.",
        "gpt-4.1": "Comprehensive implementation with full test coverage.",
    }
    return depths.get(level, depths["sonnet"])


# ── Agent Prompt Crafting ─────────────────────────────────────────────────

def craft_worker_prompt(
    task_id: str,
    task_content: str,
    playbook_dir: str,
    reasoning_level: str = "sonnet",
) -> dict[str, Any]:
    """Craft a dispatch packet for the worker agent.
    Returns model, prompt, and execution config.
    """
    # Extract dept from task content
    dept = _extract_dept(task_content)
    playbook = _load_playbook(playbook_dir, dept, "worker")

    model_cli, default_level = AGENT_ROUTING["executor"]
    level = reasoning_level or default_level

    prompt = f"""You are a *worker agent* executing task {task_id}.

## Reasoning Depth
{_get_reasoning_depth(level)}

## Department Playbook
{playbook}

## Task
{task_content}

## Rules
- You do NOT see the project goal. You execute THIS task only.
- Follow the playbook's report schema exactly.
- If you're blocked, say so clearly and list what you need.
- Do not guess at requirements. Implement what is described.

## Output
Write your worker report following the department playbook format.
"""
    return {
        "agent": "executor",
        "model_cli": model_cli,
        "reasoning_level": level,
        "prompt": prompt,
        "task_id": task_id,
        "dept": dept,
    }


def craft_qa_prompt(
    task_id: str,
    task_content: str,
    worker_report: str,
    playbook_dir: str,
    reasoning_level: str = "sonnet",
) -> dict[str, Any]:
    """Craft a dispatch packet for the QA agent.
    QA runs one reasoning level below the worker.
    """
    dept = _extract_dept(task_content)
    playbook = _load_playbook(playbook_dir, dept, "qa")
    qa_level = QA_LEVEL_DOWN.get(reasoning_level, "sonnet")

    model_cli, _ = AGENT_ROUTING["verifier"]

    prompt = f"""You are a *QA verification agent* reviewing task {task_id}.

## Reasoning Depth
{_get_reasoning_depth(qa_level)}

## Department QA Playbook
{playbook}

## Task Description
{task_content}

## Worker Report to Verify
{worker_report}

## Rules
- Assume the executor may have made mistakes. Verify independently.
- Check each claim against actual evidence (files, test output, etc.)
- Score: count PASS items / total items.
- If score < 0.9, list each failure clearly: check_name, expected, actual, severity.

## Output
1. Verification checklist with PASS/FAIL for each item.
2. Overall score (0.0+).
3. If failures exist, structured failure list.
"""
    return {
        "agent": "verifier",
        "model_cli": model_cli,
        "reasoning_level": qa_level,
        "prompt": prompt,
        "task_id": task_id,
        "dept": dept,
    }


def craft_researcher_prompt(
    task_id: str,
    task_content: str,
    playbook_dir: str,
    project_goal: str = "",
) -> dict[str, Any]:
    """Craft a dispatch packet for the researcher agent."""
    dept = _extract_dept(task_content)
    model_cli, level = AGENT_ROUTING["researcher"]

    prompt = f"""You are a *research agent* investigating requirements for task {task_id}.

## Reasoning Depth
{_get_reasoning_depth(level)}

{"## Project Goal" + chr(10) + project_goal + chr(10) if project_goal else ""}

## Task
{task_content}

## Your Job
1. Identify unknowns and open questions.
2. Research the technical landscape. What tools, patterns, prior art exist?
3. Identify risks and potential blockers.
4. Recommend an approach but DO NOT implement.

## Output
A structured research report with: findings, risks, recommendations, and time estimate.
"""
    return {
        "agent": "researcher",
        "model_cli": model_cli,
        "reasoning_level": level,
        "prompt": prompt,
        "task_id": task_id,
        "dept": dept,
    }


def craft_planner_prompt(
    task_id: str,
    task_content: str,
    playbook_dir: str,
    project_goal: str = "",
    research_report: str = "",
) -> dict[str, Any]:
    """Craft a dispatch packet for the planner agent."""
    dept = _extract_dept(task_content)
    model_cli, level = AGENT_ROUTING["planner"]

    prompt = f"""You are a *planning agent* for task {task_id}.

## Reasoning Depth
{_get_reasoning_depth(level)}

## Project Goal
{project_goal or "(not provided)"}

## Task
{task_content}

{f"## Research Report{chr(10)}{research_report}{chr(10)}" if research_report else ""}

## Your Job
1. Break the task into ordered, concrete steps.
2. For each step: what tool/command to use, what file to create/modify, what test confirms it's done.
3. Identify dependencies between steps.
4. Flag anything that needs user input before proceeding.

## Output
An ordered plan with: step number, description, tool/command, expected output, dependencies.
"""
    return {
        "agent": "planner",
        "model_cli": model_cli,
        "reasoning_level": level,
        "prompt": prompt,
        "task_id": task_id,
        "dept": dept,
    }


def craft_manager_prompt(
    task_id: str,
    task_content: str,
    worker_report: str,
    qa_report: str,
    rework_count: int,
    project_goal: str = "",
) -> dict[str, Any]:
    """Craft a dispatch packet for the manager/reviewer agent."""
    model_cli, level = AGENT_ROUTING["reviewer"]

    escalation_warning = ""
    if rework_count >= 2:
        escalation_warning = (
            "\n⚠️ This task has been reworked twice already. "
            "Consider ESCALATED if the pattern isn't converging.\n"
        )

    prompt = f"""You are a *manager/reviewer* making the final call on task {task_id}.

## Reasoning Depth
{_get_reasoning_depth(level)}

## Project Goal
{project_goal or "(not provided)"}
{escalation_warning}

## Task
{task_content}

## Worker Report
{worker_report}

## QA Report
{qa_report}

## Rework Count: {rework_count}

## Your Job
Issue a verdict:
- **VERIFIED**: Task meets requirements. QA passes. Ship it.
- **REWORK**: Specific issues need fixing. List exactly what.
- **ESCALATED**: Fundamental problem. Needs human intervention.

## Output
1. Verdict: VERIFIED | REWORK | ESCALATED
2. Reasoning (brief).
3. If REWORK: ordered list of specific fixes needed.
4. If ESCALATED: what's fundamentally wrong and what decision the human must make.
"""
    return {
        "agent": "reviewer",
        "model_cli": model_cli,
        "reasoning_level": level,
        "prompt": prompt,
        "task_id": task_id,
    }


# ── Execution ────────────────────────────────────────────────────────────

def execute_dispatch(
    dispatch_packet: dict[str, Any],
    working_dir: str = ".",
    timeout: int = 300,
) -> dict[str, Any]:
    """Execute a dispatch packet by sending it to the appropriate model CLI.
    Returns the model's response.
    """
    model_cli = dispatch_packet["model_cli"]
    prompt = dispatch_packet["prompt"]
    level = dispatch_packet.get("reasoning_level", "sonnet")

    config = MODELS.get(model_cli)
    if not config:
        return {"error": f"Unknown model CLI: {model_cli}"}

    binary = config["binary"]
    if not shutil.which(binary):
        # Fallback to Claude if Codex unavailable
        if model_cli == "codex" and shutil.which("claude"):
            binary = "claude"
            config = MODELS["claude"]
        else:
            return {"error": f"{binary} not found in PATH"}

    try:
        if model_cli == "claude":
            # claude -p reads from stdin, with configured permission mode
            perm_mode = _DISPATCH_CONFIG.get("permission_mode", "bypassPermissions")
            cmd = [binary, "-p", "--permission-mode", perm_mode]
            if level in config["models"]:
                cmd.extend(["--model", config["models"][level]])
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=working_dir,
            )
        elif model_cli == "codex":
            # Codex requires a git repo. Find one.
            codex_dir = working_dir
            check_dir = Path(working_dir)
            while check_dir != check_dir.parent:
                if (check_dir / ".git").exists():
                    codex_dir = str(check_dir)
                    break
                check_dir = check_dir.parent
            # codex exec "prompt"
            cmd = [binary, "exec"]
            if level in config["models"]:
                cmd.extend(["-m", config["models"][level]])
            cmd.extend(["-C", codex_dir, prompt])
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=codex_dir,
            )
        else:
            return {"error": f"No execution strategy for {model_cli}"}

        output = result.stdout.strip() or result.stderr.strip()
        return {
            "agent": dispatch_packet.get("agent"),
            "model_cli": model_cli,
            "reasoning_level": level,
            "output": output,
            "exit_code": result.returncode,
            "task_id": dispatch_packet.get("task_id"),
        }

    except subprocess.TimeoutExpired:
        return {"error": "timeout", "model_cli": model_cli, "timeout_seconds": timeout}
    except Exception as e:
        return {"error": str(e), "model_cli": model_cli}


def dispatch_parallel(
    packets: list[dict[str, Any]],
    working_dir: str = ".",
    timeout: int = 300,
) -> list[dict[str, Any]]:
    """Execute multiple dispatch packets in parallel.
    Use for independent tasks that don't share state.
    """
    import concurrent.futures

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(packets), 4)) as pool:
        futures = {
            pool.submit(execute_dispatch, packet, working_dir, timeout): i
            for i, packet in enumerate(packets)
        }
        for future in concurrent.futures.as_completed(futures):
            idx = futures[future]
            try:
                result = future.result()
                result["parallel_index"] = idx
                results.append(result)
            except Exception as e:
                results.append({"error": str(e), "parallel_index": idx})

    results.sort(key=lambda x: x.get("parallel_index", 0))
    return results


# ── Helpers ──────────────────────────────────────────────────────────────

def _extract_dept(task_content: str) -> str:
    """Extract department from task markdown."""
    import re
    match = re.search(r"\*\*Department\*\*: (\S+)", task_content)
    return match.group(1) if match else "engineering"


def get_available_models() -> dict[str, Any]:
    """Check which model CLIs are installed and available."""
    result = {}
    for name, config in MODELS.items():
        binary = config["binary"]
        installed = shutil.which(binary) is not None
        version = ""
        if installed:
            try:
                r = subprocess.run(
                    [binary, "--version"],
                    capture_output=True, text=True, timeout=5,
                )
                version = r.stdout.strip().splitlines()[0] if r.stdout.strip() else ""
            except Exception:
                pass
        entry = {
            "installed": installed,
            "binary": binary,
            "path": shutil.which(binary),
            "version": version,
            "strengths": config["strengths"],
            "models": list(config["models"].keys()),
        }
        if not installed and name == "codex":
            entry["fallback"] = "claude"
            entry["note"] = "Codex not installed — all execution tasks routed to Claude"
        result[name] = entry
    return result


def route_task_to_model(task_type: str, agent_role: str) -> tuple[str, str]:
    """Determine which model CLI and level to use for a task+role combo.
    Task type can override the agent's default routing.
    """
    # Task type routing takes precedence if available
    model_override = TASK_TYPE_ROUTING.get(task_type)
    agent_default_cli, agent_default_level = AGENT_ROUTING.get(agent_role, ("claude", "sonnet"))

    if model_override:
        cli = model_override
        # Use appropriate level for the CLI
        if cli == "codex":
            level = "gpt-5.4"
        else:
            level = agent_default_level
    else:
        cli = agent_default_cli
        level = agent_default_level

    # Verify CLI is available, fallback to Claude
    if not MODELS[cli]["check"]():
        cli = "claude"
        level = agent_default_level

    return cli, level
