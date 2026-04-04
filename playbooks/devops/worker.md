# DevOps Worker Playbook

## Before You Start
1. Understand the infrastructure change required
2. Check current system state (system_snapshot)
3. Identify blast radius of the change
4. Run impact_analysis before modifying infra

## Execution Checklist
- [ ] Infrastructure as code (Terraform/Bicep/Docker) — no manual changes
- [ ] Secrets in environment variables, never in files
- [ ] Health checks defined for services
- [ ] Rollback plan documented
- [ ] Resource limits set (memory, CPU, disk)
- [ ] Monitoring/alerting configured for new services
- [ ] DNS/networking changes validated

## Output
- files_changed: IaC files, Dockerfiles, config
- commands_run: terraform plan, docker build, etc.
- rollback_plan: how to undo the change
- monitoring: what to watch post-deploy
