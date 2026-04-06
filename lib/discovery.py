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

# Claude Code native tools — always available in the runtime
CLAUDE_CODE_NATIVE_TOOLS = [
    {
        "name": "Read",
        "type": "native",
        "description": "Read file contents from the filesystem with line numbers",
        "categories": ["development/general", "code"],
        "actions": ["observe"],
        "use_when": "Need to read a file, view source code, inspect configuration",
        "do_not_use_when": "Need to search across files (use Grep/Glob instead)",
    },
    {
        "name": "Edit",
        "type": "native",
        "description": "Perform exact string replacements in files",
        "categories": ["development/general", "code"],
        "actions": ["transform"],
        "use_when": "Need to modify existing files, fix code, update configuration",
        "do_not_use_when": "Creating a new file from scratch (use Write instead)",
    },
    {
        "name": "Write",
        "type": "native",
        "description": "Create or overwrite files on the filesystem",
        "categories": ["development/general", "code"],
        "actions": ["transform"],
        "use_when": "Need to create a new file or completely rewrite an existing one",
        "do_not_use_when": "Making small edits to existing files (use Edit instead)",
    },
    {
        "name": "Glob",
        "type": "native",
        "description": "Fast file pattern matching — find files by name patterns",
        "categories": ["development/general", "search"],
        "actions": ["observe"],
        "use_when": "Need to find files by name or extension pattern like *.py or src/**/*.ts",
        "do_not_use_when": "Searching file contents (use Grep instead)",
    },
    {
        "name": "Grep",
        "type": "native",
        "description": "Search file contents with regex — powered by ripgrep",
        "categories": ["development/general", "search", "code"],
        "actions": ["observe", "analyze"],
        "use_when": "Need to search for text patterns, find function definitions, locate code",
        "do_not_use_when": "Searching for files by name (use Glob instead)",
    },
    {
        "name": "Bash",
        "type": "native",
        "description": "Execute shell commands — system operations, builds, tests, git",
        "categories": ["development/general", "development/cli"],
        "actions": ["observe", "transform", "test", "verify"],
        "use_when": "Need to run commands, execute tests, build projects, git operations",
        "do_not_use_when": "Reading/editing files (use Read/Edit instead), searching (use Grep/Glob)",
    },
    {
        "name": "Agent",
        "type": "native",
        "description": "Launch subagents for complex multi-step tasks — research, explore, plan",
        "categories": ["development/general", "agent/reasoning"],
        "actions": ["analyze", "plan", "transform"],
        "use_when": "Complex tasks needing multiple steps, parallel research, deep codebase exploration",
        "do_not_use_when": "Simple single-step operations, direct file reads or edits",
    },
    {
        "name": "WebSearch",
        "type": "native",
        "description": "Search the web for information, documentation, and answers",
        "categories": ["search", "development/general"],
        "actions": ["observe"],
        "use_when": "Need to search for documentation, find solutions, look up APIs",
        "do_not_use_when": "Searching local codebase (use Grep/Glob instead)",
    },
    {
        "name": "WebFetch",
        "type": "native",
        "description": "Fetch content from URLs — web pages, APIs, documentation",
        "categories": ["development/general", "data/scraping"],
        "actions": ["observe"],
        "use_when": "Need to fetch a specific URL, read documentation, call an API",
        "do_not_use_when": "Searching the web broadly (use WebSearch instead)",
    },
    {
        "name": "TodoWrite",
        "type": "native",
        "description": "Track task progress with structured todo lists",
        "categories": ["development/general", "agent/reasoning"],
        "actions": ["plan"],
        "use_when": "Complex multi-step tasks requiring progress tracking",
        "do_not_use_when": "Single trivial tasks",
    },
]

# Live MCP servers connected in the current session (populated from ~/.mcp.json + VS Code)
# These are MCP servers actually providing tools right now
LIVE_MCP_SERVERS = {
    "claude_ai_Hugging_Face": {
        "name": "Hugging Face (claude.ai)",
        "type": "mcp",
        "description": "HuggingFace Hub — search models, datasets, papers, spaces, read docs",
        "categories": ["data/ml", "ai"],
        "actions": ["observe", "analyze"],
        "use_when": "Search AI models, datasets, papers on HuggingFace Hub",
        "tools": ["hf_hub_query", "hf_doc_search", "hf_doc_fetch", "paper_search",
                  "space_search", "hub_repo_search", "hub_repo_details", "dynamic_space"],
    },
    "claude_ai_Notion": {
        "name": "Notion (claude.ai)",
        "type": "mcp",
        "description": "Notion workspace — search, create, update pages, databases, comments",
        "categories": ["collaboration", "data"],
        "actions": ["observe", "transform"],
        "use_when": "Manage Notion pages, search workspace, create databases",
        "tools": ["notion-search", "notion-create-pages", "notion-update-page",
                  "notion-create-database", "notion-fetch"],
    },
    "claude_ai_Linear": {
        "name": "Linear (claude.ai)",
        "type": "mcp",
        "description": "Linear project management — issues, projects, cycles",
        "categories": ["collaboration", "development/general"],
        "actions": ["observe", "transform"],
        "use_when": "Track issues, manage projects in Linear",
    },
    "claude_ai_GoDaddy": {
        "name": "GoDaddy (claude.ai)",
        "type": "mcp",
        "description": "GoDaddy domains — check availability, get suggestions",
        "categories": ["infra/web"],
        "actions": ["observe"],
        "use_when": "Check domain availability, find domain names",
    },
}

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
    include_native: bool = True,
    include_live_mcp: bool = True,
    include_skill_registry: bool = True,
) -> list[dict[str, Any]]:
    """Build the unified tool index from all sources.

    Sources (in order):
    1. Tool catalog JSON (CLI tools, MCP tools, workflows)
    2. Skills directory (~/.claude/skills/)
    3. Skill registry (catalog/skill_registry.json)
    4. MCP servers (from ~/.mcp.json)
    5. VS Code MCP tools
    6. Live MCP servers (connected in current session)
    7. Claude Code native tools (Read, Edit, Bash, etc.)
    8. PATH-installed CLI tools
    """
    index: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    def _add(entry: dict) -> None:
        """Add entry, deduplicating by name (first source wins).
        Also checks installed status for CLI tools."""
        name = entry.get("name", "")
        # Normalize categories to use hierarchical form
        if "categories" in entry:
            entry["categories"] = [_normalize_category(c) for c in entry["categories"]]
        # Check installed status for CLI tools from catalog
        if entry.get("type") == "cli" and "installed" not in entry:
            binary = entry.get("binary", name)
            entry["installed"] = shutil.which(binary) is not None
        if name and name not in seen_names:
            seen_names.add(name)
            index.append(entry)

    # 1. Tool catalog
    cat_path = catalog_path or DEFAULT_CATALOG_PATH
    if cat_path.exists():
        try:
            catalog = json.loads(cat_path.read_text())
            entries = catalog if isinstance(catalog, list) else catalog.get("tools", catalog.get("entries", []))
            for entry in entries:
                entry.setdefault("type", "cli")
                entry.setdefault("source", "catalog")
                _add(entry)
        except (json.JSONDecodeError, KeyError):
            pass

    # 2. Skills from ~/.claude/skills/
    sk_dir = skills_dir or DEFAULT_SKILLS_DIR
    if sk_dir.exists():
        for skill_dir in sorted(sk_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                content = skill_md.read_text()
                lines = content.strip().splitlines()
                desc = lines[0].lstrip("# ").strip() if lines else skill_dir.name
                use_when = ""
                for line in lines:
                    if any(trigger in line.lower() for trigger in ["use when", "use for", "when:"]):
                        use_when = line.strip()
                        break

                _add({
                    "name": skill_dir.name,
                    "type": "skill",
                    "source": "skills_dir",
                    "description": desc[:200],
                    "use_when": use_when[:300],
                    "categories": _infer_skill_categories(skill_dir.name, desc),
                    "actions": _infer_skill_actions(desc),
                    "path": str(skill_md),
                })

    # 3. Skill registry (workflow skills from catalog/skill_registry.json)
    if include_skill_registry:
        for skill in load_skill_registry():
            _add({
                "name": skill["name"],
                "type": "skill",
                "source": "skill_registry",
                "description": skill.get("description", ""),
                "use_when": skill.get("use_when", []),
                "do_not_use_when": skill.get("do_not_use_when", []),
                "categories": [skill.get("category", "general")],
                "actions": [skill.get("phase", "execute")],
                "phase": skill.get("phase", ""),
                "sequence_order": skill.get("sequence_order", 0),
                "requires": skill.get("requires", []),
                "produces": skill.get("produces", []),
            })

    # 4. MCP servers from ~/.mcp.json
    mcp_path = mcp_config or DEFAULT_MCP_CONFIG
    if mcp_path.exists():
        try:
            mcp_data = json.loads(mcp_path.read_text())
            servers = mcp_data.get("mcpServers", {})
            for name, config in servers.items():
                _add({
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

    # 5. VS Code MCP tools
    if include_vscode:
        for tool in VSCODE_MCP_TOOLS.values():
            tool_copy = dict(tool)
            tool_copy["source"] = "vscode_mcp"
            _add(tool_copy)

    # 6. Live MCP servers (connected in current session)
    if include_live_mcp:
        for key, server in LIVE_MCP_SERVERS.items():
            server_copy = dict(server)
            server_copy["source"] = "live_mcp"
            server_copy["installed"] = True
            _add(server_copy)

    # 7. Claude Code native tools
    if include_native:
        for tool in CLAUDE_CODE_NATIVE_TOOLS:
            tool_copy = dict(tool)
            tool_copy["source"] = "native"
            tool_copy["installed"] = True
            _add(tool_copy)

    # 8. CLI tools from PATH
    if include_cli:
        for tool_name in KNOWN_CLI_TOOLS:
            path = shutil.which(tool_name)
            if path:
                _add({
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


# ── Category Normalization ───────────────────────────────────────────────

# Map flat/duplicate categories to canonical hierarchical forms
_CATEGORY_ALIASES = {
    "python": "development/python",
    "javascript": "development/frontend",
    "rust": "development/backend",
    "golang": "development/backend",
    "code": "development/general",
    "git": "development/git",
    "version_control": "development/git",
    "testing": "development/testing",
    "refactoring": "development/general",
    "build": "development/general",
    "linting": "development/general",
    "formatting": "development/general",
    "debugging": "development/general",
    "search": "development/general",
    "file": "development/general",
    "general": "general",
    "container": "infra/containers",
    "devops": "infra/containers",
    "kubernetes": "infra/containers",
    "cloud": "infra/cloud",
    "infrastructure": "infra/cloud",
    "deployment": "infra/cloud",
    "database": "data/database",
    "data": "data/general",
    "analytics": "data/analysis",
    "json": "data/general",
    "cache": "data/cache",
    "web": "development/frontend",
    "http": "development/frontend",
    "browser": "testing/browser",
    "automation": "infra/scheduling",
    "security": "security/general",
    "vulnerability": "security/scanning",
    "network": "network/general",
    "monitoring": "system/monitoring",
    "system": "system/general",
    "terminal": "system/general",
    "document": "data/general",
    "remote": "network/general",
    "media": "data/general",
    "transform": "data/general",
    "collaboration": "development/general",
    "ai": "data/ml",
    "ml": "data/ml",
    "reasoning": "agent/reasoning",
    "planning": "agent/reasoning",
    "persistence": "agent/memory",
}


def _normalize_category(cat: str) -> str:
    """Normalize a category to its canonical hierarchical form."""
    return _CATEGORY_ALIASES.get(cat, cat)


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
    installed_count = 0

    for tool in index:
        t = tool.get("type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1
        s = tool.get("source", "unknown")
        by_source[s] = by_source.get(s, 0) + 1
        for cat in tool.get("categories", []):
            by_category[cat] = by_category.get(cat, 0) + 1
        if tool.get("use_when"):
            has_use_when += 1
        if tool.get("installed") or tool.get("source") in ("native", "live_mcp"):
            installed_count += 1

    return {
        "total": len(index),
        "installed": installed_count,
        "by_type": by_type,
        "by_source": by_source,
        "by_category": dict(sorted(by_category.items(), key=lambda x: -x[1])),
        "has_use_when": has_use_when,
        "missing_use_when": len(index) - has_use_when,
    }
