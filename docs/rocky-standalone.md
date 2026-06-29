# Rocky Linux 9/10 Standalone Docker Install

This runbook installs a single Greenbone Community master on Rocky Linux 9 or 10
using Docker mode.

## Target Host Requirements

- Rocky Linux 9.x or 10.x on x86_64 or aarch64
  - For Rocky Linux 10, x86_64 means Rocky's x86-64-v3 baseline; older
    x86-64-v2 hardware is not a Rocky Linux 10 support target.
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
Greenbone container registry before installation. For Rocky Linux 10 x86_64,
the host must already meet Rocky's x86-64-v3 CPU baseline. Preflight validates
the required CPU flag groups, accepting Linux aliases such as `pni`/`sse3` and
`abm`/`lzcnt`; it does not make older x86-64-v2 hardware capable of running Rocky Linux 10. It also verifies that
Docker's CentOS RPM package metadata publishes the required Docker Engine and
Compose packages for the target Rocky major version and architecture. By
default, the free-disk check uses the parent filesystem of `greenbone_work_dir`;
set `greenbone_rocky_preflight_disk_check_path` when a different mount point
should be checked.

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
backend runtime status, controller `ansible-core` version, Rocky 10 x86_64
x86-64-v3 CPU flag proof, install mode, official Docker repo setting, and the localhost web bind
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

After a live acceptance run, validate the evidence and print a concise JSON
acceptance summary from the same checked reports:

```bash
python3 scripts/dev/Test-RockyAcceptanceEvidence.py --max-age-hours 24 --summary-json
```

For release acceptance, run the install and validation playbook once on Rocky 9
and once on Rocky 10.

Before live acceptance, you can validate that Rocky's official BaseOS/AppStream
metadata publishes the role prerequisites, including `python3-dnf` and
`python3-libdnf`, Docker's CentOS RPM GPG key is available, and Docker's
package index publishes the required x86_64 and aarch64 packages for Rocky 9
and 10. This check also verifies that the Rocky smoke-test container images
`quay.io/rockylinux/rockylinux:9` and `quay.io/rockylinux/rockylinux:10`
publish both `linux/amd64` and `linux/arm64` manifests:

```bash
python3 scripts/dev/Test-RockyDockerRepoMetadata.py
```

You can also validate that the official Greenbone Community container images in
the current compose file publish both `linux/amd64` and `linux/arm64` manifests:

```bash
python3 scripts/dev/Test-GreenboneContainerPlatforms.py
```

When Docker is available on the controller, you can run the same containerized
Rocky package-resolution smoke check that CI uses. On Linux or macOS:

```bash
bash scripts/dev/Test-RockyDockerRepo.sh
```

On Windows PowerShell:

```powershell
.\scripts\dev\Test-RockyDockerRepo.ps1
```

If Docker Desktop or a local corporate proxy intercepts TLS inside the smoke
container, the smoke can fail before it reaches Docker's RPM package checks.
Keep TLS verification enabled by default; for that local smoke-only case, rerun
with `ROCKY_DOCKER_REPO_SMOKE_TLS_VERIFY=false`.

## Local Acceptance Runner

When the Ansible controller can SSH to clean Rocky 9 and Rocky 10 hosts, run the
same live acceptance path locally without GitHub Actions:

```bash
export ROCKY9_HOST=192.0.2.9
export ROCKY10_HOST=192.0.2.10
export ROCKY_SSH_USER=rocky
export ROCKY_SSH_PRIVATE_KEY_FILE="$HOME/.ssh/id_ed25519"
bash scripts/dev/Run-RockyStandaloneAcceptance.sh
```

On Windows PowerShell with WSL:

```powershell
$env:ROCKY9_HOST = "192.0.2.9"
$env:ROCKY10_HOST = "192.0.2.10"
$env:ROCKY_SSH_USER = "rocky"
$env:ROCKY_SSH_PRIVATE_KEY_FILE = "$HOME\.ssh\id_ed25519"
.\scripts\dev\Run-RockyStandaloneAcceptance.ps1 -Distro Ubuntu
```

The PowerShell wrapper uses `WSLENV` so secrets are not placed on the WSL command
line, and it path-translates `ROCKY_SSH_PRIVATE_KEY_FILE`,
`ROCKY_SSH_KNOWN_HOSTS_FILE`, and `ROCKY_ACCEPTANCE_SSH_DIR` for the selected
WSL distribution. Set `ROCKY_ACCEPTANCE_WSL_DISTRO` when the target WSL distro is
not `Ubuntu`.

The runner also accepts `ROCKY_SSH_PRIVATE_KEY` when the private key is supplied
as environment content instead of a file. Set `ROCKY_BECOME_PASSWORD` when the
SSH user needs a sudo password, `ROCKY_SSH_PORT` when SSH is not on port `22`,
and either `ROCKY_SSH_KNOWN_HOSTS_FILE` or `ROCKY_SSH_KNOWN_HOSTS` for pinned
host keys. If no known-hosts input is supplied, the runner collects host keys
with `ssh-keyscan -T 10` and validates them with `ssh-keygen`.

`scripts/dev/Run-RockyStandaloneAcceptance.sh` installs required Ansible
collections unless `ROCKY_ACCEPTANCE_SKIP_GALAXY=1` is set, renders the temporary
two-host acceptance inventory, verifies SSH and sudo access with Ansible `raw`,
rejects hosts where `/opt/greenbone-community` or known Greenbone containers
already exist, runs `playbooks/preflight-rocky-standalone.yml`, runs `site.yml`,
runs `playbooks/validate-rocky-standalone.yml`, and validates the generated
evidence with `scripts/dev/Test-RockyAcceptanceEvidence.py --max-age-hours`.
If a playbook fails after the inventory is rendered, the runner also executes
`playbooks/collect-rocky-standalone-diagnostics.yml`.

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

Before dispatching the live workflow, you can check GitHub-side readiness from
the repository checkout. This command requires the GitHub CLI `gh`; it checks
authentication, that the remote acceptance workflow is active, that required repository secret names are configured, and that
`ROCKY_SSH_PORT` is valid when the optional variable is set:

```bash
python3 scripts/dev/Test-RockyAcceptanceReadiness.py
```

For stricter acceptance runs, set `ROCKY_SSH_KNOWN_HOSTS` to pinned host-key
entries for both Rocky hosts. If that secret is omitted, the workflow collects
each host key with `ssh-keyscan -T 10`, rejects empty or invalid `known_hosts`
data, and then runs Ansible with `StrictHostKeyChecking=yes` against the
generated known-hosts file.

Trigger the workflow manually from GitHub Actions against clean target hosts.
It requires different `ROCKY9_HOST` and `ROCKY10_HOST` values, renders a
temporary inventory with one Rocky 9 host and one Rocky 10 host, verifies SSH
and sudo access with an Ansible `raw` command that does not require target
Python yet, rejects hosts where `/opt/greenbone-community` or known Greenbone
containers already exist, runs
`playbooks/preflight-rocky-standalone.yml`, runs `site.yml`, runs
`playbooks/validate-rocky-standalone.yml`, verifies that the evidence contains
one valid Rocky 9 report and one valid Rocky 10 report with parseable
`validated_at` timestamps from the last 24 hours and matching GitHub workflow
run ID and attempt values, including proof that GSA
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
