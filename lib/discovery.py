"""Capability discovery — finds and indexes all available tools.

Sources:
1. Tool catalog JSON (from tool-catalog MCP)
2. Skills directory (~/.claude/skills/)
3. Agent profiles
4. MCP servers (from ~/.mcp.json)
5. VS Code MCP tools (Playwright, Serena, GitHub, HuggingFace, Pylance, Azure)
6. PATH-installed CLI tools
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


# ── Discovery Constants ──────────────────────────────────────────────────

# Primary: local catalog/ directory (v1 catalog with use_when arrays)
# Fallback: tool-catalog MCP's catalog.json
_LOCAL_CATALOG_PATH = Path(__file__).resolve().parent.parent / "catalog" / "catalog.json"
DEFAULT_CATALOG_PATH = _LOCAL_CATALOG_PATH if _LOCAL_CATALOG_PATH.exists() else (
    Path.home() / ".claude" / "mcp-servers" / "tool-catalog" / "catalog.json"
)
DEFAULT_SKILLS_DIR = Path.home() / ".claude" / "skills"
DEFAULT_MCP_CONFIG = Path.home() / ".mcp.json"

# CLI tools we know about and should check for
KNOWN_CLI_TOOLS = [
    "git", "docker", "python3", "node", "npm", "pip3",
    "curl", "jq", "yq", "grep", "rg", "fd", "fzf",
    "make", "cmake", "cargo", "go", "rustc",
    "ssh", "scp", "rsync",
    "nmap", "nikto", "semgrep", "trivy", "grype",
    "terraform", "ansible", "kubectl", "helm",
    "sqlite3", "psql", "mongosh",
    "ffmpeg", "convert", "pandoc",
    "black", "pylint", "mypy", "ruff",
    "eslint", "prettier", "tsc",
    "htop", "ss", "netstat", "lsof", "strace",
    "tmux", "screen",
]

# VS Code MCP tool categories (available when running in VS Code)
VSCODE_MCP_TOOLS = {
    "playwright": {
        "name": "playwright",
        "type": "mcp",
        "description": "Browser automation — click, type, navigate, screenshot, evaluate JS",
        "categories": ["web", "testing", "automation", "browser"],
        "actions": ["test", "observe", "verify"],
        "use_when": "Need to interact with web pages, test UIs, or automate browser tasks",
    },
    "serena": {
        "name": "serena",
        "type": "mcp",
        "description": "Symbolic code intelligence — find symbols, references, rename across codebase",
        "categories": ["code", "refactoring", "analysis"],
        "actions": ["analyze", "transform", "observe"],
        "use_when": "Need to find symbol definitions, references, or do structural code edits",
    },
    "github": {
        "name": "github",
        "type": "mcp",
        "description": "GitHub operations — issues, PRs, repos, code search, branch management",
        "categories": ["git", "collaboration", "code"],
        "actions": ["observe", "transform", "plan"],
        "use_when": "Need to work with GitHub issues, pull requests, or repository management",
    },
    "huggingface": {
        "name": "huggingface",
        "type": "mcp",
        "description": "HuggingFace Hub — search models, datasets, papers, spaces",
        "categories": ["ai", "ml", "data"],
        "actions": ["observe", "analyze"],
        "use_when": "Need to find AI models, datasets, or research papers",
    },
    "pylance": {
        "name": "pylance",
        "type": "mcp",
        "description": "Python language intelligence — type checking, imports, diagnostics",
        "categories": ["python", "code", "analysis"],
        "actions": ["analyze", "verify"],
        "use_when": "Need Python type checking, import management, or syntax analysis",
    },
    "azure": {
        "name": "azure",
        "type": "mcp",
        "description": "Azure cloud services — deploy, manage, monitor Azure resources",
        "categories": ["cloud", "infrastructure", "deployment"],
        "actions": ["transform", "observe", "verify"],
        "use_when": "Need to deploy to Azure, manage Azure resources, or use Azure services",
    },
}


# ── Index Builder ────────────────────────────────────────────────────────

def build_index(
    catalog_path: Path | None = None,
    skills_dir: Path | None = None,
    mcp_config: Path | None = None,
    include_cli: bool = True,
    include_vscode: bool = True,
) -> list[dict[str, Any]]:
    """Build the unified tool index from all sources."""
    index: list[dict[str, Any]] = []

    # 1. Tool catalog
    cat_path = catalog_path or DEFAULT_CATALOG_PATH
    if cat_path.exists():
        try:
            catalog = json.loads(cat_path.read_text())
            entries = catalog if isinstance(catalog, list) else catalog.get("tools", catalog.get("entries", []))
            for entry in entries:
                entry.setdefault("type", "cli")
                entry.setdefault("source", "catalog")
                index.append(entry)
        except (json.JSONDecodeError, KeyError):
            pass

    # 2. Skills
    sk_dir = skills_dir or DEFAULT_SKILLS_DIR
    if sk_dir.exists():
        for skill_dir in sorted(sk_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                content = skill_md.read_text()
                # Extract description from first line or paragraph
                lines = content.strip().splitlines()
                desc = lines[0].lstrip("# ").strip() if lines else skill_dir.name
                # Look for USE WHEN or similar
                use_when = ""
                for line in lines:
                    if any(trigger in line.lower() for trigger in ["use when", "use for", "when:"]):
                        use_when = line.strip()
                        break

                index.append({
                    "name": skill_dir.name,
                    "type": "skill",
                    "source": "skills_dir",
                    "description": desc[:200],
                    "use_when": use_when[:300],
                    "categories": _infer_skill_categories(skill_dir.name, desc),
                    "actions": _infer_skill_actions(desc),
                    "path": str(skill_md),
                })

    # 3. MCP servers
    mcp_path = mcp_config or DEFAULT_MCP_CONFIG
    if mcp_path.exists():
        try:
            mcp_data = json.loads(mcp_path.read_text())
            servers = mcp_data.get("mcpServers", {})
            for name, config in servers.items():
                index.append({
                    "name": name,
                    "type": "mcp_server",
                    "source": "mcp_config",
                    "description": f"MCP server: {name}",
                    "command": config.get("command", ""),
                    "categories": _infer_mcp_categories(name),
                    "actions": ["observe", "transform"],
                })
        except (json.JSONDecodeError, KeyError):
            pass

    # 4. VS Code MCP tools
    if include_vscode:
        for tool in VSCODE_MCP_TOOLS.values():
            tool_copy = dict(tool)
            tool_copy["source"] = "vscode_mcp"
            index.append(tool_copy)

    # 5. CLI tools from PATH
    if include_cli:
        for tool_name in KNOWN_CLI_TOOLS:
            path = shutil.which(tool_name)
            if path:
                index.append({
                    "name": tool_name,
                    "type": "cli",
                    "source": "path",
                    "path": path,
                    "description": f"CLI tool: {tool_name}",
                    "categories": _infer_cli_categories(tool_name),
                    "actions": _infer_cli_actions(tool_name),
                    "installed": True,
                })

    return index


# ── Category/Action Inference ────────────────────────────────────────────

def _infer_skill_categories(name: str, desc: str) -> list[str]:
    """Infer categories from skill name and description."""
    cats = []
    text = f"{name} {desc}".lower()
    mapping = {
        "security": ["security", "secops", "vuln", "threat", "red-team", "ciso", "incident", "vibesec"],
        "code": ["code", "engineering", "prompt", "agent"],
        "devops": ["observability", "runbook", "incident-commander"],
        "research": ["research", "autoresearch", "scientific"],
        "testing": ["spec", "test"],
    }
    for cat, keywords in mapping.items():
        if any(kw in text for kw in keywords):
            cats.append(cat)
    return cats or ["general"]


def _infer_skill_actions(desc: str) -> list[str]:
    """Infer actions from skill description."""
    actions = []
    desc_lower = desc.lower()
    if any(w in desc_lower for w in ["analyze", "review", "audit", "scan"]):
        actions.append("analyze")
    if any(w in desc_lower for w in ["create", "build", "generate", "write"]):
        actions.append("transform")
    if any(w in desc_lower for w in ["test", "verify", "check"]):
        actions.append("test")
    if any(w in desc_lower for w in ["plan", "design", "spec"]):
        actions.append("plan")
    if any(w in desc_lower for w in ["monitor", "observe", "detect"]):
        actions.append("observe")
    return actions or ["analyze"]


def _infer_mcp_categories(name: str) -> list[str]:
    """Infer categories from MCP server name."""
    mapping = {
        "docker": ["container", "devops"],
        "postgres": ["database", "data"],
        "redis": ["cache", "data"],
        "duckdb": ["database", "data", "analytics"],
        "filesystem": ["file", "general"],
        "fetch": ["web", "http"],
        "exa": ["web", "search"],
        "memory": ["general", "persistence"],
        "sequential-thinking": ["reasoning", "planning"],
        "semgrep": ["security", "code", "analysis"],
    }
    return mapping.get(name, ["general"])


def _infer_cli_categories(name: str) -> list[str]:
    """Infer categories for known CLI tools."""
    mapping = {
        "git": ["code", "version_control"],
        "docker": ["container", "devops"],
        "python3": ["python", "code"],
        "node": ["javascript", "code"],
        "npm": ["javascript", "package_management"],
        "pip3": ["python", "package_management"],
        "nmap": ["security", "network"],
        "nikto": ["security", "web"],
        "semgrep": ["security", "code", "analysis"],
        "trivy": ["security", "container"],
        "grype": ["security", "vulnerability"],
        "terraform": ["infrastructure", "devops"],
        "ansible": ["infrastructure", "devops", "automation"],
        "kubectl": ["kubernetes", "devops", "container"],
        "helm": ["kubernetes", "devops"],
        "psql": ["database", "postgres"],
        "sqlite3": ["database"],
        "jq": ["data", "json"],
        "rg": ["search", "code"],
        "fd": ["search", "file"],
        "ssh": ["network", "remote"],
        "make": ["build", "code"],
        "cargo": ["rust", "code", "build"],
        "go": ["golang", "code"],
        "black": ["python", "formatting"],
        "ruff": ["python", "linting"],
        "eslint": ["javascript", "linting"],
        "prettier": ["javascript", "formatting"],
        "ffmpeg": ["media", "transform"],
        "pandoc": ["document", "transform"],
        "tmux": ["terminal", "general"],
        "htop": ["monitoring", "system"],
        "ss": ["network", "monitoring"],
        "strace": ["debugging", "system"],
    }
    return mapping.get(name, ["general"])


def _infer_cli_actions(name: str) -> list[str]:
    """Infer actions for known CLI tools."""
    mapping = {
        "git": ["observe", "transform", "verify"],
        "docker": ["transform", "observe"],
        "nmap": ["observe", "analyze"],
        "semgrep": ["analyze", "verify"],
        "trivy": ["analyze", "verify"],
        "terraform": ["transform", "plan", "verify"],
        "ansible": ["transform"],
        "kubectl": ["observe", "transform"],
        "psql": ["observe", "transform"],
        "rg": ["observe"],
        "black": ["transform"],
        "ruff": ["analyze", "transform"],
        "htop": ["observe", "measure"],
    }
    return mapping.get(name, ["observe"])


# ── Index Querying ───────────────────────────────────────────────────────

def query_index(
    index: list[dict[str, Any]],
    query: str = "",
    tool_type: str = "",
    category: str = "",
    action: str = "",
    source: str = "",
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Filter the index by various criteria."""
    results = index
    query_lower = query.lower()

    if tool_type:
        results = [t for t in results if t.get("type") == tool_type]
    if source:
        results = [t for t in results if t.get("source") == source]
    if category:
        results = [t for t in results if category.lower() in [c.lower() for c in t.get("categories", [])]]
    if action:
        results = [t for t in results if action.lower() in [a.lower() for a in t.get("actions", [])]]
    if query:
        def relevance(t: dict) -> int:
            text = f"{t.get('name', '')} {t.get('description', '')} {t.get('use_when', '')}".lower()
            return sum(1 for w in query_lower.split() if w in text)
        results = [t for t in results if relevance(t) > 0]
        results.sort(key=lambda t: -relevance(t))

    return results[:limit]


def load_skill_registry() -> list[dict]:
    """Load the skill registry from catalog/skill_registry.json."""
    registry_path = Path(__file__).resolve().parent.parent / "catalog" / "skill_registry.json"
    if not registry_path.exists():
        return []
    with open(registry_path) as f:
        return json.load(f)


def get_index_stats(index: list[dict[str, Any]]) -> dict[str, Any]:
    """Return summary statistics about the index."""
    by_type: dict[str, int] = {}
    by_source: dict[str, int] = {}
    by_category: dict[str, int] = {}
    has_use_when = 0

    for tool in index:
        t = tool.get("type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1
        s = tool.get("source", "unknown")
        by_source[s] = by_source.get(s, 0) + 1
        for cat in tool.get("categories", []):
            by_category[cat] = by_category.get(cat, 0) + 1
        if tool.get("use_when"):
            has_use_when += 1

    return {
        "total": len(index),
        "by_type": by_type,
        "by_source": by_source,
        "by_category": dict(sorted(by_category.items(), key=lambda x: -x[1])),
        "has_use_when": has_use_when,
        "missing_use_when": len(index) - has_use_when,
    }
