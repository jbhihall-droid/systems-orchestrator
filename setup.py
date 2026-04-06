#!/usr/bin/env python3
"""Interactive first-run setup for the Dobby MCP server.

Run: python3 setup.py
  or: python3 setup.py --check   (non-interactive status check)
  or: python3 setup.py --install (install missing tools from saved config)

Asks what you do, suggests tool packs, offers to install missing ones.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SERVER_DIR / "config.json"
CATALOG_PATH = SERVER_DIR / "catalog" / "catalog.json"

# ── Default Config ──────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "version": 2,
    "setup_complete": False,
    "persona": "",                       # what the user does
    "catalog_profile": "full",           # full | development | security | data
    "selected_packs": [],                # which tool packs were chosen
    "dispatch": {
        "permission_mode": "bypassPermissions",
        "timeout_seconds": 300,
        "max_parallel": 4,
    },
    "models": {
        "preferred_executor": "claude",
        "default_level": "sonnet",
    },
}

# ── Tool Packs ──────────────────────────────────────────────────────────
# Curated sets of tools for different workflows

TOOL_PACKS = {
    "core-dev": {
        "label": "Core Development",
        "description": "Essential dev tools everyone needs",
        "tools": ["git", "rg", "fd", "jq", "fzf", "bat", "eza", "delta", "htop"],
        "default": True,
    },
    "python": {
        "label": "Python Development",
        "description": "Python runtime, linting, testing, formatting",
        "tools": ["python3", "pip3", "uv", "ruff", "black", "mypy", "pytest", "pre-commit"],
    },
    "node-frontend": {
        "label": "Node.js & Frontend",
        "description": "Node, npm, linting, formatting, build tools",
        "tools": ["node", "npm", "eslint", "prettier"],
    },
    "rust": {
        "label": "Rust Development",
        "description": "Rust toolchain and Cargo tools",
        "tools": ["just", "tokei", "hyperfine", "watchexec", "gitui", "difftastic", "typos"],
    },
    "data-ml": {
        "label": "Data & ML",
        "description": "Data analysis, ML experiment tracking, notebooks",
        "tools": ["sqlite3", "psql", "ollama"],
    },
    "devops": {
        "label": "DevOps & Infrastructure",
        "description": "Containers, cloud CLIs, infrastructure as code",
        "tools": ["docker", "terraform", "gh"],
    },
    "security": {
        "label": "Security & Pentesting",
        "description": "Network scanning, packet analysis, vulnerability assessment",
        "tools": ["nmap", "wireshark", "tshark", "tcpdump", "openssl"],
    },
    "modern-cli": {
        "label": "Modern CLI Replacements",
        "description": "Fast, colorful replacements for classic Unix tools",
        "tools": ["bat", "eza", "dust", "bottom", "zellij", "xh", "delta", "difftastic"],
    },
}

# ── MCP Server Packs ────────────────────────────────────────────────────
# MCP servers installed via `claude mcp add`

MCP_PACKS = {
    "core-mcp": {
        "label": "Core MCP Servers",
        "description": "Essential MCP servers for reasoning and development",
        "servers": {
            "sequential-thinking": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
            },
            "fetch": {
                "command": "uvx",
                "args": ["mcp-server-fetch"],
            },
            "memory": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-memory"],
            },
        },
    },
    "dev-mcp": {
        "label": "Development MCP Servers",
        "description": "Git, filesystem, code intelligence",
        "servers": {
            "context7": {
                "command": "npx",
                "args": ["-y", "@upstash/context7-mcp@latest"],
            },
        },
    },
    "data-mcp": {
        "label": "Data MCP Servers",
        "description": "Database access and Python execution",
        "servers": {
            "sqlite": {
                "command": "uvx",
                "args": ["mcp-server-sqlite", "--db-path", "~/.local/share/dobby/memory.db"],
            },
            "run-python": {
                "command": "uvx",
                "args": ["mcp-run-python"],
            },
        },
    },
    "security-mcp": {
        "label": "Security MCP Servers",
        "description": "Security scanning and threat intelligence",
        "servers": {
            "semgrep": {
                "command": "semgrep",
                "args": ["mcp"],
                "requires_cli": "semgrep",
            },
        },
    },
}

# ── Workflow Templates ───────────────────────────────────────────────────
# Common workflow chains that Dobby can guide users through

WORKFLOW_TEMPLATES = {
    "feature-dev": {
        "label": "Feature Development",
        "description": "Full feature lifecycle: think → plan → build → verify",
        "steps": [
            {"name": "Think", "invoke": "sequential-thinking MCP or /brainstorming", "description": "Explore approaches, consider tradeoffs"},
            {"name": "Plan", "invoke": "/writing-plans", "description": "Turn design into implementation steps"},
            {"name": "Build", "invoke": "/subagent-driven-development", "description": "Execute plan task-by-task with review"},
            {"name": "Verify", "invoke": "/verification-before-completion", "description": "Run tests, verify output"},
            {"name": "Ship", "invoke": "/finishing-a-development-branch", "description": "Merge, PR, cleanup"},
        ],
        "requires_mcp": ["sequential-thinking"],
        "requires_skills": ["/brainstorming", "/writing-plans", "/subagent-driven-development"],
    },
    "bug-fix": {
        "label": "Bug Fix",
        "description": "Diagnose → test → fix → verify",
        "steps": [
            {"name": "Diagnose", "invoke": "/systematic-debugging", "description": "Find root cause before touching code"},
            {"name": "Test", "invoke": "/test-driven-development", "description": "Write failing test that reproduces bug"},
            {"name": "Fix", "invoke": "implement the fix", "description": "Make the test pass"},
            {"name": "Verify", "invoke": "/verification-before-completion", "description": "Ensure fix doesn't break anything"},
        ],
        "requires_mcp": [],
        "requires_skills": ["/systematic-debugging", "/test-driven-development"],
    },
    "security-audit": {
        "label": "Security Audit",
        "description": "Threat model → scan → review → remediate",
        "steps": [
            {"name": "Threat Model", "invoke": "/senior-security", "description": "STRIDE analysis, identify attack surface"},
            {"name": "Scan", "invoke": "/senior-secops", "description": "SAST/DAST scan, CVE check"},
            {"name": "Review", "invoke": "/trailofbits:differential-review", "description": "Security-focused code review"},
            {"name": "Remediate", "invoke": "/engineering-skills:focused-fix", "description": "Fix vulnerabilities found"},
        ],
        "requires_mcp": [],
        "requires_skills": ["/senior-security", "/senior-secops"],
    },
    "code-review": {
        "label": "Code Review",
        "description": "Multi-angle review: quality → security → second opinion",
        "steps": [
            {"name": "Quality", "invoke": "/hex-tools:code-auditor", "description": "Style, maintainability, correctness"},
            {"name": "Security", "invoke": "/trailofbits:differential-review", "description": "Security implications of changes"},
            {"name": "Tests", "invoke": "/trailofbits:mutation-testing", "description": "Are the tests actually good?"},
            {"name": "Second Opinion", "invoke": "/trailofbits:second-opinion", "description": "Independent external review"},
        ],
        "requires_mcp": [],
        "requires_skills": [],
    },
    "quick-task": {
        "label": "Quick Task",
        "description": "Think briefly → do it → verify",
        "steps": [
            {"name": "Think", "invoke": "sequential-thinking MCP", "description": "Brief analysis of approach"},
            {"name": "Do", "invoke": "execute directly", "description": "Implement the change"},
            {"name": "Verify", "invoke": "/verification-before-completion", "description": "Quick sanity check"},
        ],
        "requires_mcp": ["sequential-thinking"],
        "requires_skills": [],
    },
}

# ── Persona → Pack Suggestions ──────────────────────────────────────────

PERSONA_SUGGESTIONS = {
    "fullstack": {
        "label": "Full-Stack Developer",
        "packs": ["core-dev", "python", "node-frontend", "devops"],
        "mcp_packs": ["core-mcp", "dev-mcp"],
        "workflows": ["feature-dev", "bug-fix", "quick-task"],
        "profile": "development",
    },
    "backend": {
        "label": "Backend Developer",
        "packs": ["core-dev", "python", "devops", "data-ml"],
        "mcp_packs": ["core-mcp", "dev-mcp", "data-mcp"],
        "workflows": ["feature-dev", "bug-fix", "quick-task"],
        "profile": "development",
    },
    "frontend": {
        "label": "Frontend Developer",
        "packs": ["core-dev", "node-frontend", "modern-cli"],
        "mcp_packs": ["core-mcp", "dev-mcp"],
        "workflows": ["feature-dev", "quick-task"],
        "profile": "development",
    },
    "data": {
        "label": "Data Scientist / ML Engineer",
        "packs": ["core-dev", "python", "data-ml"],
        "mcp_packs": ["core-mcp", "data-mcp"],
        "workflows": ["feature-dev", "quick-task"],
        "profile": "development",
    },
    "devops": {
        "label": "DevOps / SRE / Platform Engineer",
        "packs": ["core-dev", "devops", "security", "modern-cli"],
        "mcp_packs": ["core-mcp", "dev-mcp"],
        "workflows": ["feature-dev", "security-audit", "quick-task"],
        "profile": "full",
    },
    "security": {
        "label": "Security Engineer / Pentester",
        "packs": ["core-dev", "security", "devops"],
        "mcp_packs": ["core-mcp", "security-mcp"],
        "workflows": ["security-audit", "bug-fix", "quick-task"],
        "profile": "security",
    },
    "student": {
        "label": "Student / Learning",
        "packs": ["core-dev", "python"],
        "mcp_packs": ["core-mcp"],
        "workflows": ["quick-task", "bug-fix"],
        "profile": "development",
    },
    "everything": {
        "label": "Everything (power user)",
        "packs": ["core-dev", "python", "node-frontend", "rust", "data-ml", "devops", "security", "modern-cli"],
        "mcp_packs": ["core-mcp", "dev-mcp", "data-mcp", "security-mcp"],
        "workflows": ["feature-dev", "bug-fix", "security-audit", "code-review", "quick-task"],
        "profile": "full",
    },
}

# ── Install Recipes ─────────────────────────────────────────────────────

INSTALL_RECIPES = {
    "git":       {"pacman": "git", "apt": "git", "brew": "git"},
    "python3":   {"pacman": "python", "apt": "python3", "brew": "python3"},
    "node":      {"pacman": "nodejs", "apt": "nodejs", "brew": "node"},
    "npm":       {"pacman": "npm", "apt": "npm", "brew": "node"},
    "pip3":      {"pacman": "python-pip", "apt": "python3-pip", "brew": "python3"},
    "jq":        {"pacman": "jq", "apt": "jq", "brew": "jq"},
    "rg":        {"pacman": "ripgrep", "apt": "ripgrep", "brew": "ripgrep"},
    "fd":        {"pacman": "fd", "apt": "fd-find", "brew": "fd"},
    "fzf":       {"pacman": "fzf", "apt": "fzf", "brew": "fzf"},
    "htop":      {"pacman": "htop", "apt": "htop", "brew": "htop"},
    "tmux":      {"pacman": "tmux", "apt": "tmux", "brew": "tmux"},
    "strace":    {"pacman": "strace", "apt": "strace"},
    "lsof":      {"pacman": "lsof", "apt": "lsof", "brew": "lsof"},
    "docker":    {"pacman": "docker", "apt": "docker.io", "brew": "docker"},
    "gh":        {"pacman": "github-cli", "brew": "gh"},
    "uv":        {"pip": "uv"},
    "ruff":      {"pacman": "ruff", "pip": "ruff", "brew": "ruff"},
    "black":     {"pip": "black"},
    "mypy":      {"pip": "mypy"},
    "pytest":    {"pip": "pytest"},
    "pre-commit":{"pip": "pre-commit"},
    "eslint":    {"npm": "eslint"},
    "prettier":  {"npm": "prettier"},
    "bat":       {"pacman": "bat", "apt": "bat", "brew": "bat"},
    "eza":       {"pacman": "eza", "brew": "eza"},
    "dust":      {"pacman": "dust", "brew": "dust", "cargo": "du-dust"},
    "tokei":     {"pacman": "tokei", "brew": "tokei", "cargo": "tokei"},
    "hyperfine": {"pacman": "hyperfine", "brew": "hyperfine", "cargo": "hyperfine"},
    "delta":     {"pacman": "git-delta", "brew": "git-delta", "cargo": "git-delta"},
    "bottom":    {"pacman": "bottom", "brew": "bottom", "cargo": "bottom"},
    "zellij":    {"pacman": "zellij", "brew": "zellij", "cargo": "zellij"},
    "just":      {"pacman": "just", "brew": "just", "cargo": "just"},
    "watchexec": {"pacman": "watchexec", "brew": "watchexec", "cargo": "watchexec-cli"},
    "xh":        {"pacman": "xh", "brew": "xh", "cargo": "xh"},
    "typos":     {"cargo": "typos-cli", "brew": "typos-cli"},
    "gitui":     {"pacman": "gitui", "brew": "gitui", "cargo": "gitui"},
    "difftastic":{"pacman": "difftastic", "brew": "difftastic", "cargo": "difftastic"},
    "nmap":      {"pacman": "nmap", "apt": "nmap", "brew": "nmap"},
    "wireshark": {"pacman": "wireshark-qt", "apt": "wireshark", "brew": "wireshark"},
    "tshark":    {"pacman": "wireshark-cli", "apt": "tshark", "brew": "wireshark"},
    "tcpdump":   {"pacman": "tcpdump", "apt": "tcpdump", "brew": "tcpdump"},
    "openssl":   {"pacman": "openssl", "apt": "openssl", "brew": "openssl"},
    "sqlite3":   {"pacman": "sqlite", "apt": "sqlite3", "brew": "sqlite"},
    "psql":      {"pacman": "postgresql", "apt": "postgresql-client", "brew": "postgresql"},
    "terraform": {"pacman": "terraform", "brew": "terraform"},
    "ollama":    {"pacman": "ollama"},
}


# ── Helpers ─────────────────────────────────────────────────────────────

def detect_package_manager() -> str:
    for pm in ["pacman", "apt", "brew", "dnf"]:
        if shutil.which(pm):
            return pm
    return ""


def get_install_cmd(tool: str, pm: str) -> str | None:
    recipe = INSTALL_RECIPES.get(tool, {})
    pkg = recipe.get(pm)
    if pkg:
        sudo = "sudo " if pm != "brew" else ""
        cmds = {"pacman": f"{sudo}pacman -S --noconfirm {pkg}",
                "apt": f"{sudo}apt install -y {pkg}",
                "brew": f"brew install {pkg}",
                "dnf": f"{sudo}dnf install -y {pkg}"}
        return cmds.get(pm)
    # Fallbacks
    if recipe.get("pip"):
        uv = shutil.which("uv")
        return f"uv tool install {recipe['pip']}" if uv else f"pip3 install {recipe['pip']}"
    if recipe.get("npm"):
        return f"npm install -g {recipe['npm']}"
    if recipe.get("cargo") and shutil.which("cargo"):
        return f"cargo install {recipe['cargo']}"
    return None


def install_mcp_server(name: str, server_config: dict) -> tuple[bool, str]:
    """Install an MCP server via claude mcp add. Returns (success, message)."""
    # Check if prereq CLI is needed
    requires = server_config.get("requires_cli")
    if requires and not shutil.which(requires):
        return False, f"requires {requires} CLI (not installed)"

    claude_bin = shutil.which("claude")
    if not claude_bin:
        return False, "claude CLI not found"

    # Build: claude mcp add <name> -- <command> <args...>
    command = server_config["command"]
    args = server_config.get("args", [])
    cmd = [claude_bin, "mcp", "add", name, "--", command] + args

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return True, "installed"
        return False, r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "failed"
    except subprocess.TimeoutExpired:
        return False, "timed out"
    except Exception as e:
        return False, str(e)


def get_installed_mcp_servers() -> set[str]:
    """Get names of currently configured MCP servers from ~/.mcp.json."""
    mcp_path = Path.home() / ".mcp.json"
    if not mcp_path.exists():
        return set()
    try:
        data = json.loads(mcp_path.read_text())
        return set(data.get("mcpServers", {}).keys())
    except (json.JSONDecodeError, KeyError):
        return set()


def print_header(text: str):
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}\n")


def ok(name: str, detail: str = ""):
    c, r = "\033[32m", "\033[0m"
    print(f"  {c}✓{r}  {name}" + (f"  ({detail})" if detail else ""))

def fail(name: str, detail: str = ""):
    c, r = "\033[31m", "\033[0m"
    print(f"  {c}✗{r}  {name}" + (f"  ({detail})" if detail else ""))


def ask(question: str, options: list[str], default: str = "") -> str:
    opts = "/".join(f"[{o}]" if o == default else o for o in options)
    while True:
        a = input(f"  {question} ({opts}): ").strip().lower()
        if not a and default:
            return default
        if a in [o.lower() for o in options]:
            return a
        print(f"    Choose: {', '.join(options)}")


def ask_yn(question: str, default: bool = True) -> bool:
    d = "Y/n" if default else "y/N"
    a = input(f"  {question} [{d}]: ").strip().lower()
    if not a:
        return default
    return a in ("y", "yes")


def check_model(name: str, binary: str) -> dict:
    path = shutil.which(binary)
    if not path:
        return {"installed": False, "path": None, "version": ""}
    try:
        r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
        v = r.stdout.strip().splitlines()[0] if r.stdout.strip() else ""
    except Exception:
        v = ""
    return {"installed": True, "path": path, "version": v}


# ── Main Setup Flow ────────────────────────────────────────────────────

def run_setup():
    print_header("Systems Orchestrator — Setup")

    config = dict(DEFAULT_CONFIG)
    pm = detect_package_manager()

    # ── Step 1: What do you do? ─────────────────────────────────────
    print("Step 1: What do you mainly use Claude for?\n")
    for i, (key, persona) in enumerate(PERSONA_SUGGESTIONS.items(), 1):
        print(f"  {i}. {persona['label']}")

    while True:
        choice = input("\n  Pick a number (or type your own description): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(PERSONA_SUGGESTIONS):
            persona_key = list(PERSONA_SUGGESTIONS.keys())[int(choice) - 1]
            persona = PERSONA_SUGGESTIONS[persona_key]
            config["persona"] = persona["label"]
            config["catalog_profile"] = persona["profile"]
            suggested_packs = persona["packs"]
            print(f"\n  → {persona['label']}")
            break
        elif choice:
            config["persona"] = choice
            config["catalog_profile"] = "full"
            suggested_packs = ["core-dev"]
            print(f"\n  → Custom: {choice}")
            break

    # ── Step 2: Model Detection ─────────────────────────────────────
    print("\n\nStep 2: Detecting AI models\n")

    claude = check_model("Claude", "claude")
    codex = check_model("Codex", "codex")

    if claude["installed"]:
        ok("Claude Code", claude["version"])
    else:
        fail("Claude Code", "REQUIRED — npm install -g @anthropic-ai/claude-code")
        sys.exit(1)

    if codex["installed"]:
        ok("Codex", codex["version"])
        config["models"]["preferred_executor"] = "codex"
    else:
        fail("Codex", "not installed — Claude will handle all tasks")
        config["models"]["preferred_executor"] = "claude"

    # ── Step 3: Tool Packs ──────────────────────────────────────────
    print("\n\nStep 3: Tool packs\n")
    print(f"  Based on your role, I suggest these packs:\n")

    selected_packs = []
    for pack_key in suggested_packs:
        pack = TOOL_PACKS[pack_key]
        installed = sum(1 for t in pack["tools"] if shutil.which(t))
        total = len(pack["tools"])
        print(f"    {pack['label']:30s}  {installed}/{total} installed  — {pack['description']}")

    print()
    if ask_yn("Accept these suggestions?"):
        selected_packs = list(suggested_packs)
    else:
        print("\n  Available packs:\n")
        for key, pack in TOOL_PACKS.items():
            installed = sum(1 for t in pack["tools"] if shutil.which(t))
            total = len(pack["tools"])
            marker = "  *" if key in suggested_packs else "   "
            print(f"  {marker} {key:20s}  {pack['label']:30s}  {installed}/{total}")

        picks = input("\n  Enter pack names (space-separated, or 'all'): ").strip()
        if picks.lower() == "all":
            selected_packs = list(TOOL_PACKS.keys())
        else:
            selected_packs = [p.strip() for p in picks.split() if p.strip() in TOOL_PACKS]
        if not selected_packs:
            selected_packs = ["core-dev"]

    config["selected_packs"] = selected_packs
    print(f"\n  Selected: {', '.join(selected_packs)}")

    # ── Step 4: Install missing tools ───────────────────────────────
    # Collect all tools from selected packs
    needed_tools = []
    for pack_key in selected_packs:
        pack = TOOL_PACKS.get(pack_key, {})
        for tool in pack.get("tools", []):
            if tool not in needed_tools:
                needed_tools.append(tool)

    missing = [t for t in needed_tools if not shutil.which(t)]

    if missing:
        print(f"\n\nStep 4: Install missing tools ({len(missing)} not found)\n")
        if pm:
            print(f"  Package manager detected: {pm}\n")
        else:
            print("  No package manager detected. Showing manual install commands.\n")

        # Group by installable vs not
        installable = []
        manual = []
        for tool in missing:
            cmd = get_install_cmd(tool, pm) if pm else None
            if cmd:
                installable.append((tool, cmd))
            else:
                manual.append(tool)

        if installable:
            print(f"  Can auto-install ({len(installable)}):")
            for tool, cmd in installable:
                print(f"    {tool:20s}  →  {cmd}")

            print()
            if ask_yn(f"Install all {len(installable)} tools now?"):
                for tool, cmd in installable:
                    print(f"\n  Installing {tool}...")
                    try:
                        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
                        if result.returncode == 0:
                            ok(tool, "installed")
                        else:
                            fail(tool, result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "failed")
                    except subprocess.TimeoutExpired:
                        fail(tool, "timed out")
                    except Exception as e:
                        fail(tool, str(e))
            else:
                print("  Skipping installs. You can run 'python3 setup.py --install' later.")

        if manual:
            print(f"\n  Manual install needed ({len(manual)}):")
            for tool in manual:
                recipe = INSTALL_RECIPES.get(tool, {})
                hint = recipe.get("other", "check your package manager")
                print(f"    {tool:20s}  →  {hint}")
    else:
        print(f"\n\nStep 4: All {len(needed_tools)} tools already installed!")

    # ── Step 5: Dispatch Config ─────────────────────────────────────
    print("\n\nStep 5: Agent configuration\n")

    print("  Permission mode controls how subagents (researcher, executor, QA)")
    print("  access tools when dispatched.\n")
    perm = ask("Permission mode?", ["bypassPermissions", "dontAsk", "default"], "bypassPermissions")
    config["dispatch"]["permission_mode"] = perm

    level = ask("Default reasoning level?", ["haiku", "sonnet", "opus"], "sonnet")
    config["models"]["default_level"] = level

    # ── Save ────────────────────────────────────────────────────────
    config["setup_complete"] = True
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")

    print_header("Setup Complete")
    print(f"  Persona:         {config['persona']}")
    print(f"  Profile:         {config['catalog_profile']}")
    print(f"  Tool packs:      {', '.join(config['selected_packs'])}")
    print(f"  Executor:        {config['models']['preferred_executor']}")
    print(f"  Permission mode: {config['dispatch']['permission_mode']}")
    print(f"  Reasoning level: {config['models']['default_level']}")
    print(f"\n  Config saved to: {CONFIG_PATH}")
    print(f"  Re-run setup:    python3 {__file__}")
    print()


# ── Install-only mode ───────────────────────────────────────────────────

def run_install():
    """Install missing tools from saved config."""
    if not CONFIG_PATH.exists():
        print("No config found. Run setup first: python3 setup.py")
        sys.exit(1)

    config = json.loads(CONFIG_PATH.read_text())
    packs = config.get("selected_packs", ["core-dev"])
    pm = detect_package_manager()

    if not pm:
        print("No package manager found.")
        sys.exit(1)

    needed = []
    for pk in packs:
        pack = TOOL_PACKS.get(pk, {})
        for tool in pack.get("tools", []):
            if tool not in needed:
                needed.append(tool)

    missing = [t for t in needed if not shutil.which(t)]
    if not missing:
        print("All tools already installed!")
        return

    print(f"Installing {len(missing)} missing tools with {pm}...\n")
    for tool in missing:
        cmd = get_install_cmd(tool, pm)
        if cmd:
            print(f"  {tool}... ", end="", flush=True)
            try:
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
                print("✓" if r.returncode == 0 else f"✗ ({r.stderr.strip().splitlines()[-1] if r.stderr else 'failed'})")
            except Exception as e:
                print(f"✗ ({e})")
        else:
            print(f"  {tool}... no recipe for {pm}")


# ── Status Check ────────────────────────────────────────────────────────

def run_check():
    print_header("Systems Orchestrator — Status")

    claude = check_model("Claude", "claude")
    codex = check_model("Codex", "codex")

    print("Models:")
    (ok if claude["installed"] else fail)("Claude", claude.get("version", ""))
    (ok if codex["installed"] else fail)("Codex", codex.get("version", "") or "not installed")

    if CONFIG_PATH.exists():
        config = json.loads(CONFIG_PATH.read_text())
        print(f"\nConfig:")
        print(f"  Persona:    {config.get('persona', 'not set')}")
        print(f"  Profile:    {config.get('catalog_profile', 'not set')}")
        print(f"  Packs:      {', '.join(config.get('selected_packs', []))}")
        print(f"  Executor:   {config.get('models', {}).get('preferred_executor', 'not set')}")
        print(f"  Permissions: {config.get('dispatch', {}).get('permission_mode', 'not set')}")
        print(f"  Level:      {config.get('models', {}).get('default_level', 'not set')}")

        packs = config.get("selected_packs", [])
        if packs:
            print(f"\nTool pack status:")
            for pk in packs:
                pack = TOOL_PACKS.get(pk, {})
                tools = pack.get("tools", [])
                installed = sum(1 for t in tools if shutil.which(t))
                missing = [t for t in tools if not shutil.which(t)]
                label = pack.get("label", pk)
                print(f"  {label}: {installed}/{len(tools)}", end="")
                if missing:
                    print(f"  (missing: {', '.join(missing)})")
                else:
                    print("  ✓ complete")
    else:
        print(f"\n⚠  No config. Run: python3 {__file__}")
    print()


# ── Config Loader (for use by other modules) ────────────────────────────

def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except (json.JSONDecodeError, KeyError):
            pass
    return dict(DEFAULT_CONFIG)


def is_setup_complete() -> bool:
    return load_config().get("setup_complete", False)


# ── Main ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--check" in sys.argv:
        run_check()
    elif "--install" in sys.argv:
        run_install()
    else:
        run_setup()
