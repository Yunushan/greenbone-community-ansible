# Rocky Linux 9/10 Standalone Docker Install

This runbook installs a single Greenbone Community master on Rocky Linux 9 or 10
using Docker mode.

## Target Host Requirements

- Rocky Linux 9.x or 10.x on x86_64 or aarch64
- SSH access from the Ansible controller
- A user with passwordless sudo or a working Ansible become password
- Network access from the target host to:
  - `download.docker.com`
  - `greenbone.github.io`
  - `registry.community.greenbone.net`
- At least the Greenbone Community Containers recommended resources:
  - 4 CPU cores
  - 8 GB RAM
  - 60 GB free disk

## Inventory

Start from:

```bash
cp inventories/rocky-standalone/hosts.yml inventories/rocky-standalone/hosts.local.yml
```

Edit the copied inventory:

```yaml
all:
  vars:
    greenbone_install_mode: docker
    greenbone_docker_use_official_repo: true
    greenbone_web_bind_address: "127.0.0.1"
  children:
    greenbone_masters:
      hosts:
        greenbone-rocky-standalone:
          ansible_host: 192.0.2.10
          ansible_user: rocky
    greenbone_workers:
      hosts: {}
```

Keep `greenbone_install_mode: docker` on Rocky Linux. Native `gvm` package mode
is not supported by this project on Rocky Linux. When this role installs Docker
Engine, keep `greenbone_docker_use_official_repo: true` so Docker is installed
from Docker's CentOS RPM repository.

## Install

From the Ansible controller:

```bash
ansible-galaxy collection install -r requirements.yml
ansible-playbook -i inventories/rocky-standalone/hosts.local.yml site.yml
```

Or with `make`:

```bash
make rocky-standalone ROCKY_INVENTORY=inventories/rocky-standalone/hosts.local.yml
```

The role installs Docker Engine from Docker's CentOS RPM repository, downloads
the official Greenbone Community Containers compose file, starts the stack, and
sets the admin password. If `greenbone_admin_password` is empty, a password is
generated on the Ansible controller.

The generated password is stored on the Ansible controller:

```text
.secrets/greenbone_admin_password
```

## Access

The default web bind is localhost on the Rocky host:

```text
https://127.0.0.1
https://127.0.0.1:9392
```

Use SSH port forwarding, VPN, or a reverse proxy for remote access. Avoid
binding GSA directly to an untrusted network.

Example SSH tunnel:

```bash
ssh -L 8443:127.0.0.1:443 rocky@192.0.2.10
```

Then open:

```text
https://127.0.0.1:8443
```

## Verify

On the Rocky host:

```bash
sudo systemctl status docker
sudo docker compose -f /opt/greenbone-community/compose.yaml ps
sudo docker compose -f /opt/greenbone-community/compose.yaml logs -f
```

Initial feed synchronization can take minutes to hours. In the web UI, check
feed status before treating scan results as complete.

From the Ansible controller, run the post-install validation playbook:

```bash
ansible-playbook -i inventories/rocky-standalone/hosts.local.yml playbooks/validate-rocky-standalone.yml
```

Or with `make`:

```bash
make rocky-validate ROCKY_INVENTORY=inventories/rocky-standalone/hosts.local.yml
```

The validation playbook checks that the target is Rocky Linux 9 or 10, Docker is
running, the Greenbone compose file exists and parses, required core compose
services are running, and the local HTTPS endpoint answers. It waits up to five
minutes for the required core services because the first container start can take
some time. When using the generated password path, it also verifies that the
controller-side password file exists, is non-empty, and is mode `0600` without
writing the password into evidence.
It also writes a local evidence report on the Ansible controller:

```text
.secrets/rocky-standalone-evidence/<inventory-hostname>.json
```

For release acceptance, run the install and validation playbook once on Rocky 9
and once on Rocky 10.

Before live acceptance, you can validate that Docker's CentOS RPM package index
publishes the required x86_64 and aarch64 packages for Rocky 9 and 10:

```bash
python3 scripts/dev/Test-RockyDockerRepoMetadata.py
```

You can also validate that the official Greenbone Community container images in
the current compose file publish both `linux/amd64` and `linux/arm64` manifests:

```bash
python3 scripts/dev/Test-GreenboneContainerPlatforms.py
```

## GitHub Acceptance Workflow

The repository includes a manual GitHub Actions workflow for live acceptance on
real Rocky Linux hosts:

```text
.github/workflows/rocky-standalone-acceptance.yml
```

Configure these repository secrets before running it:

- `ROCKY9_HOST`: SSH hostname or IP address for a clean Rocky Linux 9 host
- `ROCKY10_HOST`: SSH hostname or IP address for a clean Rocky Linux 10 host
- `ROCKY_SSH_USER`: SSH user with passwordless sudo on both hosts
- `ROCKY_SSH_PRIVATE_KEY`: private SSH key for that user
- `ROCKY_SSH_KNOWN_HOSTS`: optional pinned known-hosts entries

You may also configure repository variable `ROCKY_SSH_PORT`; it defaults to
`22` when omitted.

Trigger the workflow manually from GitHub Actions. It renders a temporary
inventory with one Rocky 9 host and one Rocky 10 host, runs `site.yml`, runs
`playbooks/validate-rocky-standalone.yml`, verifies that the evidence contains
one valid Rocky 9 report and one valid Rocky 10 report, and uploads the JSON
reports as the `rocky-standalone-evidence` artifact.
Use the `runner_label` input to choose a runner that can SSH to both hosts.
For private networks, use a self-hosted runner with access to the Rocky hosts.

## Troubleshooting

If Docker package installation fails, confirm the target host can resolve and
reach Docker's RPM repository:

```bash
curl -I https://download.docker.com/linux/centos/docker-ce.repo
```

If container image pulls fail, confirm registry access:

```bash
sudo docker pull registry.community.greenbone.net/community/gvmd:stable
```

If the web UI is unreachable, keep the bind address private and use an SSH
tunnel first. Only set `greenbone_web_bind_address: "0.0.0.0"` when firewall,
VPN, or reverse-proxy controls are already in place.
