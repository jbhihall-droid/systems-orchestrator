#!/usr/bin/env python3
"""Expand the catalog with more development, data, and infrastructure tools
to balance the security-heavy coverage."""

import json
from pathlib import Path

CATALOG = Path(__file__).parent / "catalog" / "catalog.json"

NEW_ENTRIES = [
    # ── Development / Testing ────────────────────────────────────────
    {
        "name": "pytest",
        "type": "cli",
        "binary": "pytest",
        "category": "development/testing",
        "description": "Python test framework — fixtures, parametrize, plugins, coverage",
        "capabilities": ["unit-test", "integration-test", "fixtures", "parametrize", "coverage"],
        "common_commands": {
            "run": "pytest -v",
            "coverage": "pytest --cov=src --cov-report=html",
            "single": "pytest tests/test_foo.py::test_bar -v",
            "parallel": "pytest -n auto"
        },
        "use_when": ["run Python tests", "write unit tests", "test Python code", "pytest fixtures"],
        "do_not_use_when": ["not Python", "JavaScript tests"],
        "categories": ["development/testing", "development/python"],
        "actions": ["test", "verify"],
        "tags": ["test", "python", "coverage", "fixtures", "parametrize"]
    },
    {
        "name": "jest",
        "type": "cli",
        "binary": "jest",
        "category": "development/testing",
        "description": "JavaScript test framework — snapshots, mocks, coverage, watch mode",
        "capabilities": ["unit-test", "snapshot-test", "mocking", "coverage", "watch"],
        "common_commands": {
            "run": "npx jest",
            "watch": "npx jest --watch",
            "coverage": "npx jest --coverage",
            "single": "npx jest tests/foo.test.js"
        },
        "use_when": ["run JavaScript tests", "Jest snapshot tests", "test React components", "JS unit tests"],
        "do_not_use_when": ["not JavaScript", "Python tests"],
        "categories": ["development/testing", "development/frontend"],
        "actions": ["test", "verify"],
        "tags": ["test", "javascript", "react", "snapshot", "coverage"]
    },
    {
        "name": "vitest",
        "type": "cli",
        "binary": "vitest",
        "category": "development/testing",
        "description": "Vite-native test framework — fast, ESM-first, Jest-compatible API",
        "capabilities": ["unit-test", "component-test", "coverage", "watch", "esm"],
        "common_commands": {
            "run": "npx vitest run",
            "watch": "npx vitest",
            "coverage": "npx vitest run --coverage"
        },
        "use_when": ["Vite project tests", "fast JavaScript tests", "ESM test framework", "TypeScript tests"],
        "do_not_use_when": ["not using Vite", "legacy CommonJS project"],
        "categories": ["development/testing", "development/frontend"],
        "actions": ["test", "verify"],
        "tags": ["test", "vite", "typescript", "esm", "fast"]
    },
    {
        "name": "playwright-cli",
        "type": "cli",
        "binary": "playwright",
        "category": "testing/browser",
        "description": "End-to-end browser testing — Chromium, Firefox, WebKit, codegen, trace viewer",
        "capabilities": ["e2e-test", "browser-test", "codegen", "trace", "screenshot"],
        "common_commands": {
            "test": "npx playwright test",
            "codegen": "npx playwright codegen localhost:3000",
            "show_report": "npx playwright show-report"
        },
        "use_when": ["end-to-end browser tests", "test web application", "generate test from browser", "cross-browser testing"],
        "do_not_use_when": ["unit tests", "API-only testing", "no browser needed"],
        "categories": ["testing/browser", "development/testing"],
        "actions": ["test", "verify", "observe"],
        "tags": ["e2e", "browser", "chromium", "firefox", "webkit"]
    },
    {
        "name": "cypress",
        "type": "cli",
        "binary": "cypress",
        "category": "testing/browser",
        "description": "E2E testing framework — interactive test runner, time-travel debugging, screenshots",
        "capabilities": ["e2e-test", "component-test", "interactive-debug", "screenshot", "video"],
        "common_commands": {
            "open": "npx cypress open",
            "run": "npx cypress run",
            "component": "npx cypress run --component"
        },
        "use_when": ["interactive E2E testing", "Cypress test suite", "component testing in browser"],
        "do_not_use_when": ["API testing", "unit tests", "not web app"],
        "categories": ["testing/browser", "development/frontend"],
        "actions": ["test", "verify"],
        "tags": ["e2e", "browser", "interactive", "component"]
    },
    # ── Development / Backend ────────────────────────────────────────
    {
        "name": "uvicorn",
        "type": "cli",
        "binary": "uvicorn",
        "category": "development/backend",
        "description": "ASGI server for Python — runs FastAPI, Starlette, Django async apps",
        "capabilities": ["serve-app", "hot-reload", "asgi"],
        "common_commands": {
            "dev": "uvicorn app.main:app --reload",
            "prod": "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4"
        },
        "use_when": ["run FastAPI app", "Python ASGI server", "serve Python web app", "hot-reload Python server"],
        "do_not_use_when": ["not Python", "static site", "Node.js app"],
        "categories": ["development/backend", "development/python"],
        "actions": ["transform"],
        "tags": ["server", "fastapi", "asgi", "python", "web"]
    },
    {
        "name": "gunicorn",
        "type": "cli",
        "binary": "gunicorn",
        "category": "development/backend",
        "description": "WSGI server for Python — runs Flask, Django sync apps in production",
        "capabilities": ["serve-app", "wsgi", "process-manager"],
        "common_commands": {
            "flask": "gunicorn -w 4 app:app",
            "django": "gunicorn -w 4 project.wsgi:application"
        },
        "use_when": ["run Flask in production", "Python WSGI server", "Django production server"],
        "do_not_use_when": ["FastAPI/async", "development only", "not Python"],
        "categories": ["development/backend", "development/python"],
        "actions": ["transform"],
        "tags": ["server", "flask", "django", "wsgi", "production"]
    },
    # ── Development / Frontend ───────────────────────────────────────
    {
        "name": "vite",
        "type": "cli",
        "binary": "vite",
        "category": "development/frontend",
        "description": "Frontend build tool — instant HMR, ESM-native, React/Vue/Svelte support",
        "capabilities": ["dev-server", "hmr", "build", "preview"],
        "common_commands": {
            "dev": "npx vite",
            "build": "npx vite build",
            "preview": "npx vite preview"
        },
        "use_when": ["start frontend dev server", "build frontend", "React/Vue/Svelte project", "fast HMR development"],
        "do_not_use_when": ["backend only", "no frontend", "legacy webpack project"],
        "categories": ["development/frontend"],
        "actions": ["transform"],
        "tags": ["frontend", "build", "hmr", "react", "vue", "svelte"]
    },
    {
        "name": "next",
        "type": "cli",
        "binary": "next",
        "category": "development/frontend",
        "description": "Next.js framework CLI — SSR, SSG, API routes, App Router",
        "capabilities": ["dev-server", "build", "ssr", "ssg", "api-routes"],
        "common_commands": {
            "dev": "npx next dev",
            "build": "npx next build",
            "start": "npx next start"
        },
        "use_when": ["Next.js project", "React SSR", "full-stack React", "server components"],
        "do_not_use_when": ["not React", "SPA only", "no SSR needed"],
        "categories": ["development/frontend", "development/backend"],
        "actions": ["transform"],
        "tags": ["nextjs", "react", "ssr", "ssg", "fullstack"]
    },
    {
        "name": "tailwindcss",
        "type": "cli",
        "binary": "tailwindcss",
        "category": "development/frontend",
        "description": "Utility-first CSS framework CLI — generate styles, purge unused CSS",
        "capabilities": ["css-generate", "purge", "jit"],
        "common_commands": {
            "build": "npx tailwindcss -i src/input.css -o dist/output.css",
            "watch": "npx tailwindcss -i src/input.css -o dist/output.css --watch"
        },
        "use_when": ["generate Tailwind CSS", "utility CSS framework", "purge unused styles"],
        "do_not_use_when": ["no CSS needed", "using different CSS framework"],
        "categories": ["development/frontend"],
        "actions": ["transform"],
        "tags": ["css", "tailwind", "utility", "styling"]
    },
    # ── Data / ML ────────────────────────────────────────────────────
    {
        "name": "jupyter",
        "type": "cli",
        "binary": "jupyter",
        "category": "data/ml",
        "description": "Interactive notebook server — Python, data analysis, visualization, ML experiments",
        "capabilities": ["notebook", "interactive", "visualization", "data-analysis"],
        "common_commands": {
            "lab": "jupyter lab",
            "notebook": "jupyter notebook",
            "convert": "jupyter nbconvert --to html notebook.ipynb"
        },
        "use_when": ["interactive data analysis", "run Jupyter notebook", "ML experiments", "data visualization"],
        "do_not_use_when": ["production code", "no interactive analysis needed"],
        "categories": ["data/ml", "data/analysis"],
        "actions": ["analyze", "observe"],
        "tags": ["notebook", "data", "ml", "python", "visualization"]
    },
    {
        "name": "dvc",
        "type": "cli",
        "binary": "dvc",
        "category": "data/ml",
        "description": "Data Version Control — track datasets, ML models, pipelines with Git",
        "capabilities": ["data-versioning", "pipeline", "model-tracking", "remote-storage"],
        "common_commands": {
            "add": "dvc add data/dataset.csv",
            "push": "dvc push",
            "pull": "dvc pull",
            "repro": "dvc repro"
        },
        "use_when": ["version control datasets", "track ML models", "ML pipeline management", "data versioning"],
        "do_not_use_when": ["no ML data", "small files in git"],
        "categories": ["data/ml", "development/git"],
        "actions": ["transform", "observe"],
        "tags": ["data", "versioning", "ml", "pipeline", "models"]
    },
    {
        "name": "mlflow",
        "type": "cli",
        "binary": "mlflow",
        "category": "data/ml",
        "description": "ML experiment tracking — log metrics, parameters, artifacts, model registry",
        "capabilities": ["experiment-tracking", "model-registry", "serving", "projects"],
        "common_commands": {
            "ui": "mlflow ui",
            "run": "mlflow run .",
            "serve": "mlflow models serve -m models:/model/Production"
        },
        "use_when": ["track ML experiments", "compare model metrics", "ML model registry", "serve ML model"],
        "do_not_use_when": ["no ML", "simple scripts"],
        "categories": ["data/ml"],
        "actions": ["observe", "transform"],
        "tags": ["ml", "tracking", "experiments", "models", "metrics"]
    },
    {
        "name": "huggingface-cli",
        "type": "cli",
        "binary": "huggingface-cli",
        "category": "data/ml",
        "description": "HuggingFace Hub CLI — download models, upload datasets, manage repos",
        "capabilities": ["model-download", "dataset-upload", "repo-manage", "login"],
        "common_commands": {
            "download": "huggingface-cli download meta-llama/Llama-3-8B",
            "upload": "huggingface-cli upload my-model ./model",
            "login": "huggingface-cli login"
        },
        "use_when": ["download HuggingFace model", "upload to HuggingFace", "manage HF repos"],
        "do_not_use_when": ["no ML models", "not using HuggingFace"],
        "categories": ["data/ml"],
        "actions": ["transform", "observe"],
        "tags": ["huggingface", "models", "datasets", "download"]
    },
    # ── Data / Analysis ──────────────────────────────────────────────
    {
        "name": "csvkit",
        "type": "cli",
        "binary": "csvkit",
        "category": "data/analysis",
        "description": "CSV processing suite — convert, query, stats, join CSV files from CLI",
        "capabilities": ["csv-convert", "csv-query", "csv-stats", "csv-join"],
        "common_commands": {
            "in2csv": "in2csv data.xlsx > data.csv",
            "csvstat": "csvstat data.csv",
            "csvsql": "csvsql --query 'SELECT * FROM data WHERE age > 30' data.csv"
        },
        "use_when": ["process CSV files", "query CSV with SQL", "convert Excel to CSV", "CSV statistics"],
        "do_not_use_when": ["JSON data", "binary data", "database queries"],
        "categories": ["data/analysis"],
        "actions": ["analyze", "transform"],
        "tags": ["csv", "data", "analysis", "convert", "sql"]
    },
    {
        "name": "xsv",
        "type": "cli",
        "binary": "xsv",
        "category": "data/analysis",
        "description": "Fast CSV toolkit in Rust — search, slice, sort, join, stats on large CSVs",
        "capabilities": ["csv-search", "csv-sort", "csv-stats", "csv-join", "csv-slice"],
        "common_commands": {
            "stats": "xsv stats data.csv",
            "search": "xsv search 'pattern' data.csv",
            "frequency": "xsv frequency -s column data.csv"
        },
        "use_when": ["fast CSV processing", "large CSV analysis", "CSV search and filter"],
        "do_not_use_when": ["small data", "not CSV format"],
        "categories": ["data/analysis"],
        "actions": ["analyze", "observe"],
        "tags": ["csv", "fast", "rust", "data", "analysis"]
    },
    {
        "name": "visidata",
        "type": "cli",
        "binary": "vd",
        "category": "data/analysis",
        "description": "Terminal spreadsheet — explore CSV, JSON, SQLite, pandas interactively in TUI",
        "capabilities": ["data-explore", "pivot", "aggregate", "multi-format"],
        "common_commands": {
            "open": "vd data.csv",
            "json": "vd data.json",
            "sqlite": "vd database.db"
        },
        "use_when": ["explore data interactively", "TUI spreadsheet", "quick data inspection", "pivot table in terminal"],
        "do_not_use_when": ["need GUI", "scripted processing"],
        "categories": ["data/analysis"],
        "actions": ["observe", "analyze"],
        "tags": ["tui", "spreadsheet", "csv", "json", "explore"]
    },
    # ── Data / Pipeline ──────────────────────────────────────────────
    {
        "name": "dbt",
        "type": "cli",
        "binary": "dbt",
        "category": "data/pipeline",
        "description": "Data build tool — SQL transformations, testing, documentation for data warehouses",
        "capabilities": ["sql-transform", "data-test", "data-docs", "lineage"],
        "common_commands": {
            "run": "dbt run",
            "test": "dbt test",
            "docs": "dbt docs generate && dbt docs serve"
        },
        "use_when": ["SQL data transformations", "data warehouse modeling", "dbt project", "data testing"],
        "do_not_use_when": ["no data warehouse", "application code", "not SQL"],
        "categories": ["data/pipeline"],
        "actions": ["transform", "test"],
        "tags": ["sql", "warehouse", "transform", "analytics", "lineage"]
    },
    {
        "name": "airbyte",
        "type": "cli",
        "binary": "airbyte",
        "category": "data/pipeline",
        "description": "ELT data integration — 300+ connectors for extracting and loading data",
        "capabilities": ["data-extract", "data-load", "connectors", "sync"],
        "common_commands": {
            "list": "airbyte source list",
            "sync": "airbyte connection sync"
        },
        "use_when": ["ETL pipeline", "data integration", "sync data sources", "extract and load data"],
        "do_not_use_when": ["simple file copy", "no data integration needed"],
        "categories": ["data/pipeline"],
        "actions": ["transform"],
        "tags": ["etl", "integration", "connectors", "sync", "data"]
    },
    # ── Infrastructure / Cloud ───────────────────────────────────────
    {
        "name": "aws",
        "type": "cli",
        "binary": "aws",
        "category": "infra/cloud",
        "description": "AWS CLI — manage all AWS services from the command line",
        "capabilities": ["s3", "ec2", "lambda", "iam", "cloudformation", "ecs"],
        "common_commands": {
            "s3_ls": "aws s3 ls",
            "s3_sync": "aws s3 sync ./build s3://bucket/",
            "ec2_list": "aws ec2 describe-instances",
            "lambda_invoke": "aws lambda invoke --function-name my-func output.json"
        },
        "use_when": ["manage AWS resources", "S3 operations", "deploy to AWS", "AWS Lambda", "EC2 management"],
        "do_not_use_when": ["not using AWS", "local development only"],
        "categories": ["infra/cloud"],
        "actions": ["observe", "transform"],
        "tags": ["aws", "cloud", "s3", "ec2", "lambda", "iam"]
    },
    {
        "name": "gcloud",
        "type": "cli",
        "binary": "gcloud",
        "category": "infra/cloud",
        "description": "Google Cloud CLI — manage GCP projects, compute, storage, Kubernetes",
        "capabilities": ["compute", "storage", "gke", "cloud-run", "iam"],
        "common_commands": {
            "projects": "gcloud projects list",
            "deploy": "gcloud run deploy --source .",
            "compute": "gcloud compute instances list"
        },
        "use_when": ["manage Google Cloud", "deploy to GCP", "Cloud Run deployment", "GKE cluster management"],
        "do_not_use_when": ["not using GCP", "local development only"],
        "categories": ["infra/cloud"],
        "actions": ["observe", "transform"],
        "tags": ["gcp", "cloud", "compute", "kubernetes", "cloud-run"]
    },
    {
        "name": "flyctl",
        "type": "cli",
        "binary": "fly",
        "category": "infra/cloud",
        "description": "Fly.io CLI — deploy apps globally, Postgres, volumes, machines",
        "capabilities": ["deploy", "scale", "postgres", "volumes"],
        "common_commands": {
            "launch": "fly launch",
            "deploy": "fly deploy",
            "status": "fly status",
            "postgres": "fly postgres create"
        },
        "use_when": ["deploy to Fly.io", "global app deployment", "Fly Postgres", "edge deployment"],
        "do_not_use_when": ["not using Fly.io", "local only"],
        "categories": ["infra/cloud"],
        "actions": ["transform", "observe"],
        "tags": ["fly", "deploy", "edge", "postgres", "global"]
    },
    {
        "name": "vercel",
        "type": "cli",
        "binary": "vercel",
        "category": "infra/cloud",
        "description": "Vercel CLI — deploy frontend/fullstack apps, preview deployments, edge functions",
        "capabilities": ["deploy", "preview", "edge-functions", "domains"],
        "common_commands": {
            "deploy": "vercel",
            "prod": "vercel --prod",
            "env": "vercel env pull"
        },
        "use_when": ["deploy to Vercel", "Next.js deployment", "preview deployment", "frontend hosting"],
        "do_not_use_when": ["not using Vercel", "backend-only service"],
        "categories": ["infra/cloud", "development/frontend"],
        "actions": ["transform"],
        "tags": ["vercel", "deploy", "nextjs", "frontend", "edge"]
    },
    {
        "name": "pulumi",
        "type": "cli",
        "binary": "pulumi",
        "category": "infra/cloud",
        "description": "Infrastructure as Code in real programming languages — Python, TypeScript, Go",
        "capabilities": ["iac", "deploy", "preview", "stack-management"],
        "common_commands": {
            "up": "pulumi up",
            "preview": "pulumi preview",
            "stack": "pulumi stack ls"
        },
        "use_when": ["infrastructure as code", "Pulumi project", "IaC in Python/TypeScript", "cloud provisioning"],
        "do_not_use_when": ["using Terraform", "no cloud infrastructure"],
        "categories": ["infra/cloud"],
        "actions": ["transform", "plan"],
        "tags": ["iac", "cloud", "python", "typescript", "provisioning"]
    },
    # ── Infrastructure / Containers ──────────────────────────────────
    {
        "name": "podman",
        "type": "cli",
        "binary": "podman",
        "category": "infra/containers",
        "description": "Rootless container runtime — Docker-compatible, daemonless, OCI-compliant",
        "capabilities": ["container-run", "build", "pod-manage", "rootless"],
        "common_commands": {
            "run": "podman run -it ubuntu bash",
            "build": "podman build -t myapp .",
            "ps": "podman ps -a"
        },
        "use_when": ["run containers rootless", "Docker alternative", "build container images", "no Docker daemon"],
        "do_not_use_when": ["need Docker Compose", "Docker swarm"],
        "categories": ["infra/containers"],
        "actions": ["transform", "observe"],
        "tags": ["container", "rootless", "oci", "docker-compatible"]
    },
    {
        "name": "docker-compose",
        "type": "cli",
        "binary": "docker-compose",
        "category": "infra/containers",
        "description": "Multi-container orchestration — define and run multi-service apps",
        "capabilities": ["compose-up", "compose-build", "service-manage", "network"],
        "common_commands": {
            "up": "docker compose up -d",
            "down": "docker compose down",
            "logs": "docker compose logs -f",
            "build": "docker compose build"
        },
        "use_when": ["multi-container app", "docker compose stack", "local dev environment", "run services together"],
        "do_not_use_when": ["single container", "Kubernetes deployment"],
        "categories": ["infra/containers"],
        "actions": ["transform", "observe"],
        "tags": ["compose", "multi-container", "services", "orchestration"]
    },
    {
        "name": "lazydocker",
        "type": "cli",
        "binary": "lazydocker",
        "category": "infra/containers",
        "description": "TUI for Docker — manage containers, images, volumes, logs interactively",
        "capabilities": ["container-manage", "log-view", "image-manage", "tui"],
        "common_commands": {
            "start": "lazydocker"
        },
        "use_when": ["interactive Docker management", "Docker TUI", "view container logs", "manage Docker visually"],
        "do_not_use_when": ["scripted Docker ops", "no Docker"],
        "categories": ["infra/containers"],
        "actions": ["observe"],
        "tags": ["docker", "tui", "containers", "interactive"]
    },
    # ── Development / General ────────────────────────────────────────
    {
        "name": "gh",
        "type": "cli",
        "binary": "gh",
        "category": "development/git",
        "description": "GitHub CLI — create PRs, manage issues, run workflows, browse repos",
        "capabilities": ["pr-create", "issue-manage", "workflow-run", "repo-browse", "codespace"],
        "common_commands": {
            "pr_create": "gh pr create --fill",
            "pr_list": "gh pr list",
            "issue_create": "gh issue create",
            "run_list": "gh run list",
            "browse": "gh browse"
        },
        "use_when": ["create GitHub PR", "manage GitHub issues", "trigger GitHub Actions", "GitHub CLI operations"],
        "do_not_use_when": ["not using GitHub", "GitLab/Bitbucket"],
        "categories": ["development/git"],
        "actions": ["observe", "transform"],
        "tags": ["github", "pr", "issues", "actions", "cli"]
    },
    {
        "name": "pre-commit",
        "type": "cli",
        "binary": "pre-commit",
        "category": "development/git",
        "description": "Git hook manager — run linters, formatters, checks before every commit",
        "capabilities": ["git-hooks", "lint", "format", "auto-fix"],
        "common_commands": {
            "install": "pre-commit install",
            "run_all": "pre-commit run --all-files",
            "autoupdate": "pre-commit autoupdate"
        },
        "use_when": ["setup git hooks", "pre-commit checks", "auto-format on commit", "enforce code quality"],
        "do_not_use_when": ["no git repo", "manual checks preferred"],
        "categories": ["development/git", "development/general"],
        "actions": ["verify", "transform"],
        "tags": ["git", "hooks", "lint", "format", "quality"]
    },
    {
        "name": "direnv",
        "type": "cli",
        "binary": "direnv",
        "category": "development/general",
        "description": "Per-directory environment variables — auto-load .envrc on cd",
        "capabilities": ["env-manage", "auto-load", "project-isolation"],
        "common_commands": {
            "allow": "direnv allow",
            "edit": "direnv edit ."
        },
        "use_when": ["per-project env vars", "auto-load environment", "manage .envrc", "project isolation"],
        "do_not_use_when": ["global env sufficient", "no env vars needed"],
        "categories": ["development/general"],
        "actions": ["transform"],
        "tags": ["env", "environment", "dotenv", "project", "isolation"]
    },
    {
        "name": "act",
        "type": "cli",
        "binary": "act",
        "category": "development/general",
        "description": "Run GitHub Actions locally — test CI workflows without pushing",
        "capabilities": ["local-ci", "github-actions", "workflow-test"],
        "common_commands": {
            "run": "act",
            "list": "act -l",
            "job": "act -j build"
        },
        "use_when": ["test GitHub Actions locally", "debug CI workflow", "run CI without pushing"],
        "do_not_use_when": ["not using GitHub Actions", "GitLab CI"],
        "categories": ["development/general", "development/git"],
        "actions": ["test"],
        "tags": ["github-actions", "ci", "local", "workflow", "test"]
    },
    # ── System / Monitoring ──────────────────────────────────────────
    {
        "name": "systemctl",
        "type": "cli",
        "binary": "systemctl",
        "category": "system/monitoring",
        "description": "Systemd service manager — start, stop, enable, status system services",
        "capabilities": ["service-manage", "enable", "status", "logs"],
        "common_commands": {
            "status": "systemctl status nginx",
            "restart": "sudo systemctl restart nginx",
            "enable": "sudo systemctl enable nginx",
            "list": "systemctl list-units --type=service"
        },
        "use_when": ["manage system services", "check service status", "restart service", "enable service on boot"],
        "do_not_use_when": ["not Linux", "no systemd", "container-only"],
        "categories": ["system/monitoring"],
        "actions": ["observe", "transform"],
        "tags": ["systemd", "service", "linux", "daemon"]
    },
    {
        "name": "journalctl",
        "type": "cli",
        "binary": "journalctl",
        "category": "system/monitoring",
        "description": "Systemd journal reader — query structured system and service logs",
        "capabilities": ["log-read", "log-filter", "log-follow"],
        "common_commands": {
            "follow": "journalctl -f",
            "service": "journalctl -u nginx --since today",
            "errors": "journalctl -p err --since '1 hour ago'"
        },
        "use_when": ["read system logs", "follow service logs", "filter logs by service", "debug service errors"],
        "do_not_use_when": ["not Linux", "application logs only"],
        "categories": ["system/monitoring"],
        "actions": ["observe"],
        "tags": ["logs", "systemd", "journal", "debugging"]
    },
    # ── Database ─────────────────────────────────────────────────────
    {
        "name": "redis-cli",
        "type": "cli",
        "binary": "redis-cli",
        "category": "data/cache",
        "description": "Redis CLI — key-value operations, pub/sub, cluster management",
        "capabilities": ["key-value", "pub-sub", "cluster", "monitor"],
        "common_commands": {
            "connect": "redis-cli",
            "get": "redis-cli GET key",
            "monitor": "redis-cli MONITOR",
            "info": "redis-cli INFO"
        },
        "use_when": ["Redis operations", "check Redis keys", "Redis monitoring", "pub/sub debugging"],
        "do_not_use_when": ["no Redis server", "not using cache"],
        "categories": ["data/cache", "data/database"],
        "actions": ["observe", "transform"],
        "tags": ["redis", "cache", "key-value", "pub-sub"]
    },
    {
        "name": "mongosh",
        "type": "cli",
        "binary": "mongosh",
        "category": "data/database",
        "description": "MongoDB shell — query, aggregate, manage MongoDB databases",
        "capabilities": ["query", "aggregate", "index-manage", "admin"],
        "common_commands": {
            "connect": "mongosh mongodb://localhost:27017",
            "find": "db.collection.find({})",
            "aggregate": "db.collection.aggregate([...])"
        },
        "use_when": ["query MongoDB", "MongoDB administration", "MongoDB aggregation", "manage MongoDB indexes"],
        "do_not_use_when": ["not MongoDB", "SQL database"],
        "categories": ["data/database"],
        "actions": ["observe", "transform"],
        "tags": ["mongodb", "nosql", "query", "aggregate"]
    },
]


def main():
    catalog = json.loads(CATALOG.read_text())
    entries = catalog if isinstance(catalog, list) else catalog.get("tools", catalog.get("entries", []))

    existing_names = {e["name"] for e in entries}
    added = 0

    for new_entry in NEW_ENTRIES:
        if new_entry["name"] not in existing_names:
            new_entry.setdefault("source", "catalog")
            new_entry.setdefault("profiles", ["all"])
            # Ensure tags include action words
            entries.append(new_entry)
            existing_names.add(new_entry["name"])
            added += 1
            print(f"  + {new_entry['name']:25s} [{new_entry['category']}]")
        else:
            print(f"  = {new_entry['name']:25s} (already exists)")

    # Write back
    if isinstance(catalog, list):
        CATALOG.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n")
    else:
        key = "tools" if "tools" in catalog else "entries"
        catalog[key] = entries
        CATALOG.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n")

    # Stats
    from collections import Counter
    cats = Counter()
    for e in entries:
        top = e.get("categories", [e.get("category", "unknown")])[0].split("/")[0]
        cats[top] += 1

    print(f"\nAdded {added} new entries. Total: {len(entries)}")
    print("\nTop-level category breakdown:")
    for cat, count in cats.most_common():
        print(f"  {cat:20s} {count}")


if __name__ == "__main__":
    main()
