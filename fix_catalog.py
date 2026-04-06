#!/usr/bin/env python3
"""Populate use_when/do_not_use_when for catalog entries missing them,
and fix workflow inputs/element_types."""

import json
from pathlib import Path

CATALOG = Path(__file__).parent / "catalog" / "catalog.json"

# ── use_when / do_not_use_when data for all 133 missing entries ──────────

USE_WHEN_DATA = {
    # Security/Scanning
    "masscan": {
        "use_when": ["fast port scan", "scan entire subnet", "mass port discovery", "sweep large IP ranges"],
        "do_not_use_when": ["service version detection", "OS fingerprinting", "need detailed scan"]
    },
    # Security/Wireless
    "airodump-ng": {
        "use_when": ["scan WiFi networks", "capture handshake", "find access points", "detect WiFi clients"],
        "do_not_use_when": ["wired network", "web application scan"]
    },
    "aireplay-ng": {
        "use_when": ["deauth WiFi client", "force handshake capture", "WiFi injection attack", "replay ARP packets"],
        "do_not_use_when": ["passive scanning", "wired network"]
    },
    "kismet": {
        "use_when": ["passive WiFi recon", "wireless IDS", "bluetooth scanning", "device tracking", "SDR monitoring"],
        "do_not_use_when": ["active scanning", "web application testing"]
    },
    "wifite": {
        "use_when": ["automated WiFi cracking", "batch WiFi attack", "quick WPA crack"],
        "do_not_use_when": ["need fine control", "specific attack technique"]
    },
    "macchanger": {
        "use_when": ["change MAC address", "spoof MAC", "anonymize network interface"],
        "do_not_use_when": ["not doing wireless", "no need for anonymity"]
    },
    # Security/Cracking
    "hashcat": {
        "use_when": ["crack password hash", "GPU password cracking", "WPA handshake crack", "NTLM hash crack", "brute force hash"],
        "do_not_use_when": ["online brute force", "network login attack"]
    },
    "john": {
        "use_when": ["crack shadow file", "CPU password crack", "crack ZIP password", "crack SSH key passphrase"],
        "do_not_use_when": ["need GPU acceleration", "mass hash cracking"]
    },
    "hydra": {
        "use_when": ["brute force SSH login", "brute force web login", "online credential attack", "credential spraying", "FTP brute force"],
        "do_not_use_when": ["offline hash cracking", "need to crack captured hashes"]
    },
    # Security/Exploitation
    "metasploit": {
        "use_when": ["exploit vulnerability", "generate payload", "post-exploitation", "reverse shell", "pivot through network"],
        "do_not_use_when": ["passive recon only", "static code analysis"]
    },
    # Security/MITM
    "bettercap": {
        "use_when": ["ARP spoofing", "DNS spoofing", "man-in-the-middle attack", "WiFi deauth", "BLE scanning", "credential sniffing"],
        "do_not_use_when": ["passive monitoring only", "web application testing"]
    },
    "ettercap": {
        "use_when": ["ARP poisoning", "MITM attack", "credential sniffing", "DNS spoofing on LAN"],
        "do_not_use_when": ["WiFi attacks", "web application testing"]
    },
    "responder": {
        "use_when": ["capture NTLM hashes", "LLMNR poisoning", "NBT-NS poisoning", "WPAD attack", "Windows credential capture"],
        "do_not_use_when": ["non-Windows network", "web application testing"]
    },
    "proxychains": {
        "use_when": ["route traffic through proxy", "anonymize connections", "pivot through compromised host"],
        "do_not_use_when": ["direct connection is fine", "no proxy needed"]
    },
    # Security/Forensics
    "wireshark": {
        "use_when": ["analyze packets GUI", "inspect pcap file", "deep protocol analysis", "follow TCP stream"],
        "do_not_use_when": ["need CLI packet analysis", "scripted analysis"]
    },
    "tshark": {
        "use_when": ["CLI packet capture", "extract fields from pcap", "filter packets", "script packet analysis", "extract DNS queries"],
        "do_not_use_when": ["need visual GUI analysis", "interactive inspection"]
    },
    "tcpdump": {
        "use_when": ["quick packet capture", "lightweight packet sniff", "capture traffic to file", "live traffic debug"],
        "do_not_use_when": ["need deep protocol decode", "need field extraction"]
    },
    "p0f": {
        "use_when": ["passive OS fingerprinting", "identify OS from traffic", "stealthy host identification"],
        "do_not_use_when": ["active scanning OK", "need service detection"]
    },
    "binwalk": {
        "use_when": ["analyze firmware", "extract embedded files", "reverse engineer binary", "find hidden data in files"],
        "do_not_use_when": ["source code analysis", "web application testing"]
    },
    "foremost": {
        "use_when": ["recover deleted files", "carve files from disk image", "forensic file recovery"],
        "do_not_use_when": ["file is not deleted", "live system analysis"]
    },
    "exiftool": {
        "use_when": ["read image metadata", "extract EXIF data", "analyze file metadata", "strip metadata"],
        "do_not_use_when": ["binary analysis", "network forensics"]
    },
    # Security/Web
    "sqlmap": {
        "use_when": ["SQL injection test", "database enumeration", "exploit SQLi vulnerability", "dump database tables"],
        "do_not_use_when": ["no web application", "network scanning"]
    },
    "sslscan": {
        "use_when": ["test SSL/TLS configuration", "check cipher suites", "find SSL vulnerabilities", "certificate inspection"],
        "do_not_use_when": ["no HTTPS service", "application-level testing"]
    },
    # Security/Wireless tools
    "reaver": {
        "use_when": ["WPS brute force", "crack WPS PIN", "recover WPA via WPS"],
        "do_not_use_when": ["WPS not enabled", "no WiFi interface"]
    },
    "bully": {
        "use_when": ["WPS Pixie Dust attack", "WPS PIN brute force", "alternative WPS cracker"],
        "do_not_use_when": ["WPS not enabled", "need handshake attack"]
    },
    # Security/Network
    "enum4linux": {
        "use_when": ["enumerate SMB shares", "enumerate Windows users", "SMB recon", "Active Directory enumeration"],
        "do_not_use_when": ["no SMB/Windows targets", "web application testing"]
    },
    "smbclient": {
        "use_when": ["connect to SMB share", "browse Windows shares", "download files from share", "upload to SMB"],
        "do_not_use_when": ["no SMB service", "need enumeration only"]
    },
    # Security/Bluetooth
    "hcitool": {
        "use_when": ["scan bluetooth devices", "BLE device discovery", "bluetooth recon", "HCI interface control"],
        "do_not_use_when": ["no bluetooth adapter", "WiFi only"]
    },
    # Security/Defense
    "strace": {
        "use_when": ["trace system calls", "debug process behavior", "monitor file access", "diagnose crashes"],
        "do_not_use_when": ["high-level debugging", "code review"]
    },
    "auditd": {
        "use_when": ["Linux audit logging", "monitor file access", "track user actions", "compliance logging"],
        "do_not_use_when": ["not Linux", "no audit requirements"]
    },
    "inotifywait": {
        "use_when": ["watch file changes", "monitor directory modifications", "trigger on file events"],
        "do_not_use_when": ["not Linux", "one-time file check"]
    },
    # Security/Evasion
    "mdk4": {
        "use_when": ["WiFi denial of service test", "beacon flood test", "deauth flood test", "WiFi stress test"],
        "do_not_use_when": ["legitimate WiFi use", "passive recon"]
    },
    # Security/Social Engineering
    "setoolkit": {
        "use_when": ["social engineering attack", "phishing campaign", "credential harvester", "SE framework"],
        "do_not_use_when": ["technical exploit", "network attack"]
    },
    # Development/CLI — Modern CLI tools
    "bat": {
        "use_when": ["view file with syntax highlighting", "better cat replacement", "colored file output"],
        "do_not_use_when": ["piping to other commands", "need plain output"]
    },
    "ripgrep": {
        "use_when": ["fast code search", "search file contents", "grep replacement", "regex search codebase"],
        "do_not_use_when": ["search by filename", "binary file search"]
    },
    "fzf": {
        "use_when": ["fuzzy find files", "interactive selection", "filter command output"],
        "do_not_use_when": ["exact match needed", "scripted non-interactive"]
    },
    "delta": {
        "use_when": ["better git diff", "syntax-highlighted diff", "side-by-side diff"],
        "do_not_use_when": ["need machine-readable diff", "scripted diff"]
    },
    "eza": {
        "use_when": ["list files with icons", "better ls replacement", "tree view with git status"],
        "do_not_use_when": ["need plain ls output", "scripting"]
    },
    "dust": {
        "use_when": ["disk usage analysis", "find large directories", "better du replacement"],
        "do_not_use_when": ["need exact byte counts", "scripted disk check"]
    },
    "procs": {
        "use_when": ["list processes", "better ps replacement", "find processes by name"],
        "do_not_use_when": ["need standard ps output", "scripting"]
    },
    "zoxide": {
        "use_when": ["smart directory navigation", "cd replacement", "jump to frequent directories"],
        "do_not_use_when": ["need exact cd path", "scripting"]
    },
    "tokei": {
        "use_when": ["count lines of code", "code statistics", "language breakdown"],
        "do_not_use_when": ["need file content", "code search"]
    },
    "gping": {
        "use_when": ["visual ping graph", "monitor latency", "compare ping to multiple hosts"],
        "do_not_use_when": ["need standard ping output", "scripted monitoring"]
    },
    "hyperfine": {
        "use_when": ["benchmark commands", "compare execution times", "measure command performance"],
        "do_not_use_when": ["simple timing", "application profiling"]
    },
    "ruff": {
        "use_when": ["Python linting", "fast Python formatter", "Python code quality check", "replace flake8/isort"],
        "do_not_use_when": ["not Python", "type checking"]
    },
    # Development tools
    "uv": {
        "use_when": ["Python package install", "fast pip replacement", "Python virtual env", "Python project management"],
        "do_not_use_when": ["not Python", "need npm/node"]
    },
    "just": {
        "use_when": ["run project commands", "task runner", "Makefile alternative", "justfile recipes"],
        "do_not_use_when": ["need Make compatibility", "C/C++ build system"]
    },
    "starship": {
        "use_when": ["configure shell prompt", "custom terminal prompt", "cross-shell prompt"],
        "do_not_use_when": ["not configuring shell", "no terminal customization"]
    },
    "cargo-binstall": {
        "use_when": ["install Rust binaries fast", "skip Rust compilation", "install cargo tools"],
        "do_not_use_when": ["not Rust", "need to compile from source"]
    },
    "mold": {
        "use_when": ["fast linker", "speed up C/C++/Rust builds", "replace ld linker"],
        "do_not_use_when": ["not compiling native code", "cross-compiling"]
    },
    "zellij": {
        "use_when": ["terminal multiplexer", "split terminal panes", "tmux alternative"],
        "do_not_use_when": ["single terminal sufficient", "already using tmux"]
    },
    "gitui": {
        "use_when": ["TUI git interface", "interactive git staging", "visual git log"],
        "do_not_use_when": ["need CLI git", "scripted git operations"]
    },
    "difftastic": {
        "use_when": ["structural diff", "syntax-aware diff", "AST-based code comparison"],
        "do_not_use_when": ["need line-based diff", "binary diff"]
    },
    "bottom": {
        "use_when": ["system monitor TUI", "CPU/memory/network graphs", "htop alternative"],
        "do_not_use_when": ["need machine-readable output", "scripted monitoring"]
    },
    "watchexec": {
        "use_when": ["watch files and rerun command", "auto-reload on save", "live development loop"],
        "do_not_use_when": ["one-time execution", "no file watching needed"]
    },
    "xh": {
        "use_when": ["HTTP requests", "API testing CLI", "curl alternative with colors"],
        "do_not_use_when": ["need curl compatibility", "scripted HTTP"]
    },
    "sccache": {
        "use_when": ["compile cache", "speed up Rust/C++ rebuilds", "shared build cache"],
        "do_not_use_when": ["not compiling", "first build only"]
    },
    "bandwhich": {
        "use_when": ["monitor bandwidth per process", "find which app uses network", "live bandwidth usage"],
        "do_not_use_when": ["need historical data", "no network monitoring needed"]
    },
    "typos": {
        "use_when": ["find typos in code", "spell check source files", "fix identifier typos"],
        "do_not_use_when": ["prose spell checking", "not code"]
    },
    "hexyl": {
        "use_when": ["hex dump file", "binary file inspection", "colored hex viewer"],
        "do_not_use_when": ["text file viewing", "need plain hexdump"]
    },
    "grex": {
        "use_when": ["generate regex from examples", "create regex pattern", "regex builder"],
        "do_not_use_when": ["simple pattern", "already know regex"]
    },
    "git-cliff": {
        "use_when": ["generate changelog", "changelog from git history", "release notes from commits"],
        "do_not_use_when": ["manual changelog", "no git history"]
    },
    "fnm": {
        "use_when": ["manage Node.js versions", "switch Node version", "nvm alternative"],
        "do_not_use_when": ["not using Node.js", "single Node version"]
    },
    # MCP servers in catalog
    "playwright": {
        "use_when": ["browser automation", "test web UI", "take screenshot", "fill web form", "evaluate JavaScript in browser"],
        "do_not_use_when": ["no browser needed", "API-only testing"]
    },
    "github-mcp": {
        "use_when": ["manage GitHub issues", "create pull request", "search GitHub code", "list commits"],
        "do_not_use_when": ["local git only", "no GitHub repo"]
    },
    "figma-mcp": {
        "use_when": ["read Figma designs", "design-to-code", "get design screenshots", "extract design tokens"],
        "do_not_use_when": ["no Figma designs", "code-only project"]
    },
    "deepwiki": {
        "use_when": ["query repo documentation", "understand GitHub project", "explain open source code"],
        "do_not_use_when": ["local project docs", "private repo"]
    },
    "context7": {
        "use_when": ["get library documentation", "API reference lookup", "framework docs in context"],
        "do_not_use_when": ["general web search", "no specific library"]
    },
    "serena": {
        "use_when": ["find symbol definitions", "code references", "structural rename", "code intelligence"],
        "do_not_use_when": ["text search", "grep-style search"]
    },
    "shodan-mcp": {
        "use_when": ["IP recon via Shodan", "find exposed devices", "CVE lookup", "DNS lookup", "internet device search"],
        "do_not_use_when": ["local network scan", "no internet recon needed"]
    },
    "virustotal-mcp": {
        "use_when": ["scan URL for malware", "check file hash", "analyze suspicious domain", "IOC enrichment"],
        "do_not_use_when": ["local file analysis", "network scanning"]
    },
    "pentest-mcp": {
        "use_when": ["full pentest suite", "automated security scan", "vulnerability scan", "web fuzzing"],
        "do_not_use_when": ["single tool needed", "passive recon only"]
    },
    "postgres-mcp": {
        "use_when": ["query PostgreSQL", "inspect database schema", "explain query plan", "database health check"],
        "do_not_use_when": ["not PostgreSQL", "file-based data"]
    },
    "dbhub": {
        "use_when": ["query multiple databases", "multi-DB schema inspect", "MySQL or SQLite or Postgres"],
        "do_not_use_when": ["single database type", "no database needed"]
    },
    "sqlite-mcp": {
        "use_when": ["query SQLite database", "inspect SQLite schema", "local database operations"],
        "do_not_use_when": ["not SQLite", "need PostgreSQL/MySQL"]
    },
    "filesystem-mcp": {
        "use_when": ["file operations via MCP", "read write search files", "directory tree"],
        "do_not_use_when": ["Claude Code native tools available", "simple file read"]
    },
    "fetch-mcp": {
        "use_when": ["fetch web page as markdown", "convert HTML for LLM", "read web documentation"],
        "do_not_use_when": ["local file reading", "API call"]
    },
    "git-mcp": {
        "use_when": ["git operations via MCP", "git log diff blame", "repository inspection"],
        "do_not_use_when": ["git CLI available", "simple git command"]
    },
    "sequential-thinking": {
        "use_when": ["complex reasoning", "step-by-step analysis", "multi-step problem solving"],
        "do_not_use_when": ["simple task", "direct answer available"]
    },
    "memory-mcp": {
        "use_when": ["persist information across sessions", "knowledge graph", "entity relationships"],
        "do_not_use_when": ["temporary data", "session-only context"]
    },
    "qdrant-mcp": {
        "use_when": ["vector search", "semantic similarity", "embedding-based retrieval"],
        "do_not_use_when": ["keyword search", "no embeddings"]
    },
    "mcp-language-server": {
        "use_when": ["language server features", "code completion", "diagnostics", "hover info"],
        "do_not_use_when": ["simple text editing", "no IDE features needed"]
    },
    "antv-chart-mcp": {
        "use_when": ["create charts", "data visualization", "generate graphs"],
        "do_not_use_when": ["no visualization needed", "raw data only"]
    },
    "mcp-run-python": {
        "use_when": ["run Python code", "execute Python snippets", "Python REPL"],
        "do_not_use_when": ["Bash available", "not Python"]
    },
    # Catalog plugins/skills
    "pr-review-toolkit": {
        "use_when": ["review pull request", "comprehensive PR review", "PR quality check"],
        "do_not_use_when": ["no PR exists", "simple code review"]
    },
    "feature-dev": {
        "use_when": ["guided feature development", "architecture-focused feature", "structured feature build"],
        "do_not_use_when": ["simple task", "bug fix"]
    },
    "superpowers": {
        "use_when": ["enhanced Claude capabilities", "advanced tool usage", "power features"],
        "do_not_use_when": ["simple tasks", "basic operations"]
    },
    "hookify": {
        "use_when": ["create hooks from conversation", "prevent unwanted behaviors", "automate rules"],
        "do_not_use_when": ["no behavior to prevent", "manual control preferred"]
    },
    "security-guidance": {
        "use_when": ["security best practices", "secure coding guidance", "OWASP reference"],
        "do_not_use_when": ["not security related"]
    },
    "frontend-design": {
        "use_when": ["build web UI", "frontend components", "landing page design", "dashboard layout"],
        "do_not_use_when": ["backend only", "no UI"]
    },
    "code-review": {
        "use_when": ["code review", "PR review", "code quality audit", "review changes"],
        "do_not_use_when": ["no code to review", "implementation task"]
    },
    "agent-sdk-dev": {
        "use_when": ["build Agent SDK app", "create Claude agent", "setup SDK project"],
        "do_not_use_when": ["not building agents", "using existing agent"]
    },
    "huggingface-skills": {
        "use_when": ["HuggingFace integration", "model deployment", "ML pipeline"],
        "do_not_use_when": ["no ML needed", "not HuggingFace"]
    },
    "data-engineering": {
        "use_when": ["data pipeline", "ETL process", "data transformation", "data processing"],
        "do_not_use_when": ["no data processing", "frontend work"]
    },
    "terraform": {
        "use_when": ["infrastructure as code", "provision cloud resources", "manage Terraform state", "deploy infrastructure"],
        "do_not_use_when": ["no cloud infrastructure", "manual deployment"]
    },
    "go": {
        "use_when": ["Go programming", "build Go project", "Go module management"],
        "do_not_use_when": ["not Go project"]
    },
    "psql": {
        "use_when": ["PostgreSQL CLI", "run SQL queries", "database administration", "inspect PostgreSQL"],
        "do_not_use_when": ["not PostgreSQL", "need GUI"]
    },
    # Network tools
    "socat": {
        "use_when": ["relay network connections", "port forwarding", "bidirectional data transfer", "socket debugging"],
        "do_not_use_when": ["simple HTTP request", "no network relay needed"]
    },
    "nc": {
        "use_when": ["netcat connection", "port check", "simple TCP/UDP client", "reverse shell listener"],
        "do_not_use_when": ["need encryption", "HTTP protocol"]
    },
    "mtr": {
        "use_when": ["traceroute with ping", "network path analysis", "find packet loss location"],
        "do_not_use_when": ["simple ping", "no routing issue"]
    },
    "whois": {
        "use_when": ["domain registration lookup", "IP ownership", "registrar information"],
        "do_not_use_when": ["DNS resolution", "no domain info needed"]
    },
    "host": {
        "use_when": ["DNS lookup", "resolve hostname", "find DNS records", "reverse DNS"],
        "do_not_use_when": ["need detailed dig output", "no DNS needed"]
    },
    "openssl": {
        "use_when": ["SSL certificate inspection", "generate certificates", "test TLS connection", "encrypt/decrypt data"],
        "do_not_use_when": ["no crypto needed", "application-level security"]
    },
    "lsof": {
        "use_when": ["list open files", "find process using port", "find file locks", "debug file descriptors"],
        "do_not_use_when": ["process listing only", "no file investigation"]
    },
    "htop": {
        "use_when": ["interactive process monitor", "CPU/memory usage", "kill processes", "system resource overview"],
        "do_not_use_when": ["need machine-readable output", "scripted monitoring"]
    },
    "traceroute": {
        "use_when": ["trace network path", "find routing hops", "diagnose network routing"],
        "do_not_use_when": ["simple connectivity check", "ping sufficient"]
    },
    "ss": {
        "use_when": ["list network sockets", "find listening ports", "check TCP connections", "socket statistics"],
        "do_not_use_when": ["need packet inspection", "no network debugging"]
    },
    # Python tools
    "black": {
        "use_when": ["format Python code", "Python auto-formatter", "enforce Python style"],
        "do_not_use_when": ["not Python", "using ruff format"]
    },
    "mypy": {
        "use_when": ["Python type checking", "verify type annotations", "find type errors"],
        "do_not_use_when": ["not Python", "no type annotations"]
    },
    "pgcli": {
        "use_when": ["PostgreSQL CLI with autocomplete", "interactive SQL", "better psql"],
        "do_not_use_when": ["not PostgreSQL", "scripted SQL"]
    },
    # System tools
    "tmux": {
        "use_when": ["terminal multiplexer", "persistent terminal session", "split panes", "remote session management"],
        "do_not_use_when": ["single command", "no terminal management needed"]
    },
    # Build tools
    "gradle": {
        "use_when": ["Java/Kotlin build", "Android build", "run Gradle tasks"],
        "do_not_use_when": ["not JVM project", "using Maven"]
    },
    "npm": {
        "use_when": ["install Node packages", "run npm scripts", "Node.js project management"],
        "do_not_use_when": ["not JavaScript/TypeScript", "using yarn/pnpm"]
    },
    # ── Workflows ───────────────────────────────────────────────────────
    "WF01-wpa-handshake-crack": {
        "use_when": ["crack WPA password", "capture WiFi handshake", "WPA dictionary attack"],
        "do_not_use_when": ["WPS attack", "no WiFi interface"]
    },
    "WF02-pmkid-clientless": {
        "use_when": ["clientless WPA attack", "PMKID capture", "crack WiFi without client"],
        "do_not_use_when": ["need deauth attack", "no WiFi interface"]
    },
    "WF03-wps-pixie-bruteforce": {
        "use_when": ["WPS PIN attack", "Pixie Dust WiFi crack", "exploit WPS vulnerability"],
        "do_not_use_when": ["WPS disabled", "no WiFi"]
    },
    "WF04-evil-twin-credential-harvest": {
        "use_when": ["evil twin attack", "fake AP credential harvest", "WiFi phishing"],
        "do_not_use_when": ["no WiFi interface", "passive attack only"]
    },
    "WF05-arp-mitm": {
        "use_when": ["ARP spoof MITM", "intercept LAN traffic", "sniff credentials on LAN"],
        "do_not_use_when": ["WiFi attack", "no LAN access"]
    },
    "WF06-llmnr-poison": {
        "use_when": ["capture NTLM hash from Windows", "LLMNR poisoning", "Windows credential harvest"],
        "do_not_use_when": ["no Windows hosts", "non-Windows network"]
    },
    "WF07-eternalblue": {
        "use_when": ["exploit MS17-010", "EternalBlue SMB attack", "unpatched Windows RCE"],
        "do_not_use_when": ["patched Windows", "non-Windows target"]
    },
    "WF08-web-sqli-exfil": {
        "use_when": ["SQL injection attack", "web database exfiltration", "exploit web SQLi"],
        "do_not_use_when": ["no web application", "network-level attack"]
    },
    "WF09-service-bruteforce": {
        "use_when": ["brute force network service", "SSH brute force", "credential attack on services"],
        "do_not_use_when": ["hash cracking", "web application"]
    },
    "WF10-ble-recon-gatt-extract": {
        "use_when": ["BLE device recon", "enumerate GATT services", "extract BLE characteristics"],
        "do_not_use_when": ["no bluetooth adapter", "WiFi attack"]
    },
    "WF11-smb-relay-attack": {
        "use_when": ["SMB relay attack", "NTLM relay to shell", "relay without cracking"],
        "do_not_use_when": ["SMB signing enabled", "no Windows targets"]
    },
    "WF12-default-credential-spray": {
        "use_when": ["default credential check", "factory password spray", "vendor default login"],
        "do_not_use_when": ["custom credentials", "no network devices"]
    },
    "WF13-hidden-ssid-discovery": {
        "use_when": ["find hidden WiFi network", "discover hidden SSID", "reveal cloaked AP"],
        "do_not_use_when": ["SSID is visible", "no WiFi"]
    },
    "WF14-wpad-poisoning": {
        "use_when": ["WPAD proxy attack", "intercept via WPAD", "Windows proxy poisoning"],
        "do_not_use_when": ["no Windows hosts", "WPAD not in use"]
    },
    "WF15-dns-spoof-phishing": {
        "use_when": ["DNS spoofing attack", "redirect DNS to phishing", "DNS-based credential harvest"],
        "do_not_use_when": ["no LAN access", "DNS over HTTPS in use"]
    },
    "WF16-detect-arp-spoof": {
        "use_when": ["detect ARP spoofing", "ARP poisoning defense", "find MITM on LAN"],
        "do_not_use_when": ["attacking not defending", "no LAN"]
    },
    "WF17-detect-bruteforce-ban": {
        "use_when": ["detect brute force attack", "auto-ban failed logins", "defend against credential attack"],
        "do_not_use_when": ["offensive operation", "no server to defend"]
    },
    "WF18-detect-rogue-ap": {
        "use_when": ["detect rogue access point", "find unauthorized WiFi", "wireless IDS"],
        "do_not_use_when": ["attacking not defending", "no WiFi monitoring"]
    },
    "WF19-full-network-compromise": {
        "use_when": ["full penetration test", "network compromise chain", "recon to domain admin"],
        "do_not_use_when": ["single vulnerability", "web-only scope"]
    },
    "WF20-iot-device-exploitation": {
        "use_when": ["exploit IoT device", "firmware analysis", "IoT security test"],
        "do_not_use_when": ["no IoT devices", "standard IT network"]
    },
}

# ── Workflow input fixes ─────────────────────────────────────────────────

WORKFLOW_INPUT_FIXES = {
    "WF01-wpa-handshake-crack": {
        "inputs": ["interface", "bssid", "wordlist"],
        "element_types": ["interface", "bssid", "wordlist"],
    },
    "WF02-pmkid-clientless": {
        "inputs": ["interface", "wordlist"],
        "element_types": ["interface", "wordlist"],
    },
    "WF03-wps-pixie-bruteforce": {
        "inputs": ["interface", "bssid"],
        "element_types": ["interface", "bssid"],
    },
    "WF04-evil-twin-credential-harvest": {
        "inputs": ["interface", "ssid", "bssid"],
        "element_types": ["interface", "ssid", "bssid"],
    },
    "WF10-ble-recon-gatt-extract": {
        "inputs": ["interface"],
        "element_types": ["interface"],
    },
    "WF13-hidden-ssid-discovery": {
        "inputs": ["interface"],
        "element_types": ["interface"],
    },
    # Also fix aireplay-ng which had wrong inputs
    "aireplay-ng": {
        "inputs": ["interface", "bssid", "client-mac"],
        "element_types": ["interface", "bssid", "client-mac"],
    },
}


def main():
    catalog = json.loads(CATALOG.read_text())
    entries = catalog if isinstance(catalog, list) else catalog.get("tools", catalog.get("entries", []))

    updated = 0
    input_fixed = 0

    for entry in entries:
        name = entry.get("name", "")

        # Add use_when/do_not_use_when
        if name in USE_WHEN_DATA and not entry.get("use_when"):
            data = USE_WHEN_DATA[name]
            entry["use_when"] = data["use_when"]
            entry["do_not_use_when"] = data.get("do_not_use_when", [])
            updated += 1

        # Fix workflow inputs
        if name in WORKFLOW_INPUT_FIXES:
            fixes = WORKFLOW_INPUT_FIXES[name]
            entry["inputs"] = fixes["inputs"]
            entry["element_types"] = fixes["element_types"]
            input_fixed += 1

    # Write back
    if isinstance(catalog, list):
        CATALOG.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n")
    else:
        catalog["tools" if "tools" in catalog else "entries"] = entries
        CATALOG.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n")

    # Summary
    total = len(entries)
    has_uw = sum(1 for e in entries if e.get("use_when"))
    missing = total - has_uw
    print(f"Total entries: {total}")
    print(f"Updated with use_when: {updated}")
    print(f"Input/element_types fixed: {input_fixed}")
    print(f"Now has use_when: {has_uw}")
    print(f"Still missing: {missing}")
    if missing:
        still_missing = [e["name"] for e in entries if not e.get("use_when")]
        print(f"Missing names: {still_missing}")


if __name__ == "__main__":
    main()
