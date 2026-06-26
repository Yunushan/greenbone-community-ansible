# greenbone-community-ansible — English

This project installs Greenbone Community Edition with Ansible.

## Default topology

The default is a single master node. The `greenbone_workers` group is empty.

## Supported distributions

Ubuntu, Debian, Kali Linux, RHEL, AlmaLinux, Rocky Linux 9/10, Oracle Linux, and Alpine Linux.

## Installation modes

`greenbone_install_mode: auto` chooses native installation on Kali and Docker
installation on most other supported systems. Rocky Linux 9/10 standalone
installs must set `greenbone_install_mode: docker` explicitly. You can force
`docker` or `native`.

```yaml
greenbone_install_mode: docker
```

## Install

```bash
ansible-galaxy collection install -r requirements.yml
ansible-playbook -i inventories/single-master/hosts.yml site.yml
```

The admin password is generated locally in `.secrets/greenbone_admin_password`.

## Rocky Linux 9/10 standalone Docker

Rocky Linux 9 and 10 are Docker-only standalone master targets on x86_64 and
aarch64 in this project. Keep `greenbone_docker_use_official_repo: true` when
the role installs Docker:

```bash
ansible-playbook -i inventories/rocky-standalone/hosts.yml site.yml
```

See [rocky-standalone.md](rocky-standalone.md) for the full runbook.

## Web UI

Docker mode binds to localhost by default:

```text
https://127.0.0.1
https://127.0.0.1:9392
```

To expose it:

```yaml
greenbone_web_bind_address: "0.0.0.0"
```

Use firewall or VPN protection.

## Workers

Add hosts to `greenbone_workers` for optional scanner worker nodes. Remote scanner registration is disabled until OSP certificates are configured.
