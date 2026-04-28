# greenbone-community-ansible — English

This project installs Greenbone Community Edition with Ansible.

## Default topology

The default is a single master node. The `greenbone_workers` group is empty.

## Supported distributions

Ubuntu, Debian, Kali Linux, RHEL, AlmaLinux, Rocky Linux, Oracle Linux, and Alpine Linux.

## Installation modes

`greenbone_install_mode: auto` chooses native installation on Kali and Docker installation on other supported systems. You can force `docker` or `native`.

```yaml
greenbone_install_mode: docker
```

## Install

```bash
ansible-galaxy collection install -r requirements.yml
ansible-playbook -i inventories/single-master/hosts.yml site.yml
```

The admin password is generated locally in `.secrets/greenbone_admin_password`.

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
