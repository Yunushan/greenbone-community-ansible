# Security Policy

## Reporting issues

Open a GitHub issue for general security hardening suggestions. For vulnerabilities in Greenbone itself, report to Greenbone through their official channels.

## Secure deployment notes

- Keep `greenbone_web_bind_address` set to `127.0.0.1` unless access is controlled.
- Use Ansible Vault or another secret manager for production passwords.
- Do not expose worker OSPD ports to the internet.
- Review firewall rules before running scans.
- Obtain authorization before scanning networks you do not own or administer.
