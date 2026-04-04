# QA/Testing Worker Playbook

## Before You Start
1. Understand what's being tested and why
2. Review existing test coverage
3. Identify test framework in use (pytest, jest, etc.)

## Execution Checklist
- [ ] Test plan covers happy path AND edge cases
- [ ] Tests are independent (no order dependency)
- [ ] Tests clean up after themselves
- [ ] Meaningful assertions (not just "no error")
- [ ] Test names describe the behavior being tested
- [ ] Mock external dependencies (no network calls in unit tests)
- [ ] Coverage report generated if tooling exists

## Output
- files_changed: test files created/modified
- test_plan: what was tested
- coverage: line/branch coverage numbers
- gaps: known untested areas
