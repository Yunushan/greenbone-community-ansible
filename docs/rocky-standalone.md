# Rocky Linux 9/10 Standalone Docker Install

This runbook installs a single Greenbone Community master on Rocky Linux 9 or 10
using Docker mode.

## Target Host Requirements

- Rocky Linux 9.x or 10.x on x86_64 or aarch64
- SSH access from the Ansible controller
- A user with passwordless sudo or a working Ansible become password
- `ansible-core` 2.19.0 or newer on the controller for Rocky Linux 10; the
  GitHub acceptance workflow installs the current release before running
  preflight, install, and validation
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
from Docker's CentOS RPM repository with Docker's RPM GPG key fingerprint
verified and imported.

## Install

From the Ansible controller:

```bash
python3 -m pip install --upgrade ansible-core
ansible-galaxy collection install -r requirements.yml
ansible-playbook -i inventories/rocky-standalone/hosts.local.yml playbooks/preflight-rocky-standalone.yml
ansible-playbook -i inventories/rocky-standalone/hosts.local.yml site.yml
```

Or with `make`:

```bash
make rocky-preflight ROCKY_INVENTORY=inventories/rocky-standalone/hosts.local.yml
make rocky-standalone ROCKY_INVENTORY=inventories/rocky-standalone/hosts.local.yml
```

Preflight and install both import `playbooks/bootstrap-rocky-standalone.yml`
before fact gathering. The bootstrap uses Ansible `raw` commands only on hosts
identified as Rocky Linux, ensures `python3`, `python3-dnf`, and
`python3-libdnf` are present, and also installs `python3-libdnf5` only if the
target's enabled Rocky repositories publish it.

The preflight playbook verifies Rocky Linux 9/10, the expected major version
when configured, x86_64 or aarch64 architecture, minimum CPU/RAM/disk
resources, Docker mode, Docker's official CentOS RPM repository setting, and
controller `ansible-core` compatibility for Rocky Linux 10, verifies that
Ansible reports a supported `dnf` or `dnf5` package manager, plus target-host
network access to Docker, Docker's RPM GPG key, Greenbone docs, and the
Greenbone container registry before installation. It also verifies that Docker's
CentOS RPM package metadata publishes the required Docker Engine and Compose
packages for the target Rocky major version and architecture. By default, the free-disk
check uses the parent filesystem of `greenbone_work_dir`; set
`greenbone_rocky_preflight_disk_check_path` when a different mount point should
be checked.

The role installs Docker Engine from Docker's CentOS RPM repository, downloads
the official Greenbone Community Containers compose file, starts the stack, and
sets the admin password. If `greenbone_admin_password` is empty, a password is
generated on the Ansible controller.
If a Rocky target reports `ansible_pkg_mgr=dnf5`, the common role verifies that
`python3-libdnf5` is installed before the first Ansible `dnf` module task.

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
running, the target still meets the minimum CPU/RAM/disk resources, Docker's
CentOS RPM repository, GPG checking, Docker's CentOS RPM GPG key URL, imported
Docker RPM GPG key ID, and required Docker RPM packages are present, the
Greenbone compose file exists and parses, required core compose services are
running, including `openvas`, `openvasd`, and `ospd-openvas`, and the local
HTTPS and GSAD endpoints answer. It waits up to 15 minutes for the required
core services by default because the first container start can take some time.
Override `greenbone_rocky_validate_service_retries` and
`greenbone_rocky_validate_service_delay` only when you intentionally want a
different release-acceptance readiness window.
When using the generated password path, it also verifies that the controller-side
password file exists, is non-empty, and is mode `0600` without writing the
password into evidence. The evidence includes the validation timestamp, CPU,
memory, free-disk facts, OS family, kernel, package manager, conditional DNF5
backend runtime status, controller `ansible-core` version, install mode,
official Docker repo setting, and the localhost web bind
address, Docker RPM repo GPG checking, Docker's CentOS RPM GPG key URL, Docker RPM GPG key
fingerprint and import status, HTTPS port, GSAD port, and proof that the compose
file contains the expected `127.0.0.1:443:443` and `127.0.0.1:9392:9392`
mappings. The service readiness gate passes before the compose service listing
is collected, and the evidence records the readiness retry count, delay, and
timeout.
It also writes a local evidence report on the Ansible controller:

```text
.secrets/rocky-standalone-evidence/<inventory-hostname>.json
```

For release acceptance, run the install and validation playbook once on Rocky 9
and once on Rocky 10.

Before live acceptance, you can validate that Rocky's official BaseOS/AppStream
metadata publishes the role prerequisites, including `python3-dnf` and
`python3-libdnf`, Docker's CentOS RPM GPG key is available, and Docker's
package index publishes the required x86_64 and aarch64 packages for Rocky 9
and 10:

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
- `ROCKY_SSH_USER`: SSH user with sudo privileges on both hosts
- `ROCKY_SSH_PRIVATE_KEY`: private SSH key for that user
- `ROCKY_BECOME_PASSWORD`: optional sudo/become password when the SSH user
  does not have passwordless sudo
- `ROCKY_SSH_KNOWN_HOSTS`: optional pinned known-hosts entries

You may also configure repository variable `ROCKY_SSH_PORT`; it defaults to
`22` when omitted.

For stricter acceptance runs, set `ROCKY_SSH_KNOWN_HOSTS` to pinned host-key
entries for both Rocky hosts. If that secret is omitted, the workflow collects
each host key with `ssh-keyscan -T 10`, rejects empty or invalid `known_hosts`
data, and then runs Ansible with `StrictHostKeyChecking=yes` against the
generated known-hosts file.

Trigger the workflow manually from GitHub Actions. It requires different
`ROCKY9_HOST` and `ROCKY10_HOST` values, renders a temporary inventory with one
Rocky 9 host and one Rocky 10 host, verifies SSH and sudo access with an
Ansible `raw` command that does not require target Python yet, runs
`playbooks/preflight-rocky-standalone.yml`, runs `site.yml`, runs
`playbooks/validate-rocky-standalone.yml`, verifies that the evidence contains
one valid Rocky 9 report and one valid Rocky 10 report, including proof that GSA
is bound to `127.0.0.1:443`, GSAD is bound to `127.0.0.1:9392`, and both endpoints respond locally,
and uploads the JSON reports as the
`rocky-standalone-evidence` artifact. If the acceptance job
fails, it also tries to collect Docker, Compose, service, disk, and recent
Compose log diagnostics from both hosts, including Docker info, SELinux,
firewalld, and repo trust facts, and uploads them as the
`rocky-standalone-diagnostics` artifact. The diagnostics report does not include
the generated admin password, but review logs before sharing the artifact
outside trusted operators.
Use the `runner_label` input to choose a runner that can SSH to both hosts.
For private networks, use a self-hosted runner with access to the Rocky hosts.
Self-hosted runners must be current enough for Node.js 24 based GitHub actions,
because this workflow uses `actions/checkout@v7`, `actions/setup-python@v6`,
and `actions/upload-artifact@v7`. Use runner version v2.327.1 or later.

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
