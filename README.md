# greenbone-community-ansible

An Ansible project for installing **Greenbone Community Edition** on a default **single master node**, with an optional path for **multiple scanner worker nodes**.

The project is designed for:

- Ubuntu
- Debian
- Kali Linux
- Red Hat Enterprise Linux
- AlmaLinux
- Rocky Linux
- Oracle Linux
- Alpine Linux

The default topology is one Greenbone master. Worker nodes are opt-in by adding hosts to the `greenbone_workers` inventory group.

> **Important:** Greenbone Community Edition feed loading can take minutes to hours after the first start. Do not expect scans to be complete until the feed status is current.

## Multilingual documentation

- [English](docs/README.en.md)
- [简体中文](docs/README.zh.md)
- [हिन्दी](docs/README.hi.md)
- [Español](docs/README.es.md)
- [العربية](docs/README.ar.md)

## What this repository provides

- Single-master installation by default.
- Optional Docker-based installation using the official Greenbone Community Containers compose file.
- Optional native `gvm` package installation where native packages are practical, especially Kali Linux.
- Optional scanner worker role for advanced multi-node deployments.
- Secure-by-default local web bind for container mode: `127.0.0.1`.
- Generated admin password stored locally under `.secrets/` on the Ansible controller.
- MIT license.
- GitHub Actions workflow for Ansible linting.

## Quick start

```bash
git clone https://github.com/YOUR_ORG/greenbone-community-ansible.git
cd greenbone-community-ansible
python3 -m pip install --user ansible-core
ansible-galaxy collection install -r requirements.yml
```

Edit the default single-master inventory:

```bash
$EDITOR inventories/single-master/hosts.yml
```

Run:

```bash
ansible-playbook -i inventories/single-master/hosts.yml site.yml
```

The generated admin password is saved on your Ansible controller in:

```text
.secrets/greenbone_admin_password
```

For Docker mode, the default web UI is bound to the target host only:

```text
https://127.0.0.1
https://127.0.0.1:9392
```

To expose the UI on the network, override:

```yaml
greenbone_web_bind_address: "0.0.0.0"
```

Use a firewall, VPN, or reverse proxy when exposing GSA.

## Default installation mode

`greenbone_install_mode` defaults to `auto`:

- Kali Linux defaults to native `gvm` packages.
- Ubuntu, Debian, RHEL, AlmaLinux, Rocky Linux, Oracle Linux, and Alpine default to Docker mode for portability.

You can force a mode:

```yaml
greenbone_install_mode: docker
```

or:

```yaml
greenbone_install_mode: native
```

Native mode is intentionally conservative. Native package names and packaging quality vary by distribution. Docker mode is the broadest cross-distribution path.

## Inventory examples

### Single master

```yaml
all:
  children:
    greenbone_masters:
      hosts:
        greenbone-master-01:
          ansible_host: 192.0.2.10
          ansible_user: ubuntu
    greenbone_workers:
      hosts: {}
```

### Multi-node layout

```yaml
all:
  children:
    greenbone_masters:
      hosts:
        greenbone-master-01:
          ansible_host: 192.0.2.10
    greenbone_workers:
      hosts:
        greenbone-worker-01:
          ansible_host: 192.0.2.21
        greenbone-worker-02:
          ansible_host: 192.0.2.22
```

Worker nodes deploy scanner components. Registering remote scanners into `gvmd` requires certificate handling and is disabled by default. See [docs/architecture.md](docs/architecture.md).

## Useful commands

Install:

```bash
ansible-playbook -i inventories/single-master/hosts.yml site.yml
```

Update container feeds and restart updated containers:

```bash
ansible-playbook -i inventories/single-master/hosts.yml playbooks/update-feeds.yml
```

Stop Docker stack:

```bash
ansible-playbook -i inventories/single-master/hosts.yml playbooks/uninstall.yml -e greenbone_uninstall_keep_data=true
```

Remove Docker stack and volumes:

```bash
ansible-playbook -i inventories/single-master/hosts.yml playbooks/uninstall.yml -e greenbone_uninstall_keep_data=false
```

## Main variables

See [docs/variables.md](docs/variables.md) for the full list.

Common overrides:

```yaml
greenbone_install_mode: auto          # auto, docker, native
greenbone_web_bind_address: 127.0.0.1
greenbone_web_https_port: 443
greenbone_web_gsad_port: 9392
greenbone_admin_user: admin
```

## Security notes

- Keep the web UI bound to localhost unless you have a secure access path.
- Change or securely store the generated admin password.
- Treat scanner workers as privileged systems: they generate network traffic and need raw socket capabilities in Docker mode.
- Review Greenbone Community Feed licensing and usage expectations before large-scale scanning.

## License

MIT. See [LICENSE](LICENSE).
