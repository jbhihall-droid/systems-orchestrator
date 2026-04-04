# Security Worker Playbook

## Before You Start
1. Understand the scope of the security assessment
2. Review existing security controls and policies
3. Check available scanning tools (semgrep, trivy, nmap, nikto)
4. Identify the threat model for the target system

## Execution Checklist
- [ ] Static analysis (SAST) with semgrep or equivalent
- [ ] Dependency scanning (trivy, grype, or npm audit)
- [ ] Secret scanning (no leaked credentials)
- [ ] OWASP Top 10 check against the target
- [ ] Input validation review
- [ ] Authentication/authorization review
- [ ] Encryption at rest and in transit verified
- [ ] Logging of security events (no PII in logs)

## Output
- files_changed: security configs, scan results
- vulnerabilities_found: CVE-ID, severity, location
- recommendations: prioritized fix list
- scan_reports: raw tool output
- risk_assessment: overall risk level
