# Engineering Worker Playbook

## Before You Start
1. Read the full task description
2. Check for dependency tasks — are they VERIFIED?
3. Read relevant source files before modifying them
4. Identify the test suite for the affected area

## Execution Checklist
- [ ] Create a working branch or checkpoint (git stash/commit)
- [ ] Write/modify code following existing project conventions
- [ ] Run existing tests to establish baseline
- [ ] Write new tests for new behavior
- [ ] Run full test suite — all must pass
- [ ] Run linter (black/ruff for Python, eslint/prettier for JS/TS)
- [ ] No hardcoded secrets, credentials, or API keys
- [ ] Check for common security issues (OWASP Top 10)

## Code Standards
- Match the project's existing style (indentation, naming, patterns)
- Prefer small, focused changes over large rewrites
- Add type hints (Python) or TypeScript types where the project uses them
- Don't add unnecessary dependencies
- Don't refactor code outside the task scope

## Output
Produce a worker report with:
- files_changed: every file you touched
- commands_run: build/test/lint commands executed
- tests_passed: bool
- blockers: anything that prevented full completion
