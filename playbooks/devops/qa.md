# DevOps QA Playbook

## Verification Steps
1. **IaC Validity**: Does `terraform validate` / `docker build` succeed?
2. **Secrets**: No hardcoded secrets or credentials?
3. **Health Checks**: Service health endpoints defined?
4. **Resource Limits**: CPU/memory bounds set?
5. **Rollback**: Plan exists and is executable?
6. **Idempotency**: Can the change be applied twice safely?
7. **Security**: Least-privilege IAM/RBAC?

## Scoring
- 0.9+: Clean IaC, proper secrets, health checks, rollback
- 0.7-0.8: Functional with minor omissions
- <0.7: Security issues or no rollback plan
