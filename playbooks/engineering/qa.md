# Engineering QA Playbook

## Verification Steps
1. **Requirements Check**: Does the output satisfy EVERY requirement in the task?
2. **Test Verification**: Run `python3 -m pytest` or `npm test` — all pass?
3. **Lint Check**: Run linter — no new warnings?
4. **Security Scan**: Run semgrep or trivy if available
5. **Diff Review**: Read the actual changes — do they make sense?
6. **Edge Cases**: Are boundary conditions handled?
7. **Dependencies**: Any new dependencies? Are they justified?

## Scoring Guide
| Score | Meaning |
|-------|---------|
| 0.9-1.0 | All checks pass, clean implementation |
| 0.7-0.8 | Minor issues (style, missing edge case) — acceptable |
| 0.5-0.6 | Significant gaps — rework likely needed |
| 0.0-0.4 | Major failures or missing requirements |

## Red Flags (auto-fail)
- Tests don't pass
- New security vulnerabilities introduced
- Hardcoded secrets or credentials
- Changes outside task scope without justification
- Breaks existing functionality

## Output
Score each requirement individually, then produce overall score.
