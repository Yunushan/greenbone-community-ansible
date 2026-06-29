# Support Matrix

This project treats Greenbone Community Containers as the portable installation path.
Native package installation is intentionally conservative and is aimed at Kali or Debian-family lab hosts.

## Docker Standalone Targets

| Distribution | Versions | Architectures | Mode | Docker repository | Status |
|---|---:|---|---|---|---|
| Rocky Linux | 9.x | x86_64, aarch64 | Docker standalone master | Docker CentOS RPM repo | Supported by this project |
| Rocky Linux | 10.x | x86_64, aarch64 | Docker standalone master | Docker CentOS RPM repo | Supported by this project |

For Rocky Linux 10, x86_64 follows Rocky's x86-64-v3 baseline. Older
x86-64-v2 hardware is outside this support target even though Ansible reports
the installed architecture as `x86_64`.

For Rocky Linux 9/10, keep:

```yaml
greenbone_install_mode: docker
greenbone_docker_use_official_repo: true
```

Use:

```bash
ansible-playbook -i inventories/rocky-standalone/hosts.yml site.yml
```

## Support Boundary

Rocky Linux support means this project installs Docker Engine through the Docker RPM repo,
verifies and imports Docker's RPM GPG key, downloads the official Greenbone Community
Containers compose file, starts it with Docker Compose, and keeps the default
web bind on localhost.

It does not mean native `gvm` packages are supported on Rocky Linux.

The CI smoke check pulls `quay.io/rockylinux/rockylinux:9` and
`quay.io/rockylinux/rockylinux:10`, adds Docker's CentOS RPM repo,
verifies that Docker Engine and Docker Compose plugin packages resolve for both major versions,
then downloads Greenbone's official compose file and checks that Docker Compose can parse it.
CI also validates Rocky BaseOS/AppStream prerequisite package publication,
including `python3-dnf` and `python3-libdnf`, Docker's CentOS RPM GPG key, and
Docker's CentOS 9 and 10 RPM package publication for x86_64 and aarch64
directly so package publication failures are caught even before the container
smoke install. It also checks that the Rocky smoke-test container images and
Greenbone's current Community Container compose images publish both linux/amd64 and linux/arm64 manifests,
and that the official compose file still contains the core services and
localhost web mappings used by Rocky validation.
CI also runs `ansible-playbook --syntax-check` and `--list-hosts` against the
Rocky standalone inventory. A pre-install preflight playbook at
`playbooks/preflight-rocky-standalone.yml` validates the Rocky major version,
architecture, Rocky 10 x86_64 x86-64-v3 CPU flags, minimum CPU/RAM/disk
resources, Docker mode, official Docker RPM repo setting, and target-host
network access to Docker, Docker's RPM GPG key, Greenbone docs, and the
Greenbone container registry before installation. It
also checks Docker's CentOS RPM package metadata for the target Rocky major version and architecture.
Preflight and install import `playbooks/bootstrap-rocky-standalone.yml` before
fact gathering; that bootstrap uses `raw` commands on Rocky hosts to ensure
`python3`, `python3-dnf`, and `python3-libdnf` are present, and adds
`python3-libdnf5` only when the target's enabled Rocky repositories publish it.
Rocky 10 runs require `ansible-core` 2.19.0 or newer on the controller; the
GitHub acceptance workflow installs current `ansible-core` before running
preflight, install, and validation. Rocky validation accepts `ansible_pkg_mgr`
values of `dnf` or `dnf5`; if a target reports `dnf5`, validation records and
requires the target-side `python3-libdnf5` binding.
A post-install validation playbook is provided at
`playbooks/validate-rocky-standalone.yml` for live Rocky 9/10 targets.
It checks that the target still meets the minimum CPU/RAM/disk resources,
Docker's CentOS RPM repository and required Docker RPM packages are present,
Docker's RPM GPG key has the expected fingerprint and is imported,
waits for required core compose services including `openvas`, `openvasd`, and
`ospd-openvas`, checks the local HTTPS and GSAD endpoints,
checks that the generated admin password file exists, is non-empty, and is mode
`0600` when using the default password generation path, and writes per-host
evidence reports under `.secrets/rocky-standalone-evidence/`. The evidence
includes the validation timestamp, the target's OS family, kernel, package
manager, conditional DNF5 backend runtime status, controller `ansible-core`
version, CPU, Rocky 10 x86_64 x86-64-v3 CPU flag proof, memory, and free-disk facts,
install mode, official Docker repo setting, localhost web bind address, Docker RPM repo GPG checking, Docker's CentOS RPM
GPG key URL, Docker RPM GPG key fingerprint and import status, HTTPS port, GSAD
port, and proof that the compose file contains the expected
`127.0.0.1:443:443` and `127.0.0.1:9392:9392` mappings. The compose service
listing in the evidence is collected after the service readiness gate passes.
The default Rocky validation readiness window is 60 retries with a 15-second
delay, so release evidence proves a 900-second service startup window was used.
`scripts/dev/Test-RockyAcceptanceEvidence.py --summary-json` validates those
same reports before emitting the accepted Rocky 9/10 evidence summary.

The CI smoke check does not start the full Greenbone stack because GitHub-hosted
runners are not Rocky Linux hosts. A full acceptance run means installing with
`site.yml` on real Rocky 9 and Rocky 10 hosts, then running the post-install
validation playbook.
The same Docker-based package-resolution smoke check can be run locally with
`scripts/dev/Test-RockyDockerRepo.sh` or, on Windows PowerShell,
`scripts/dev/Test-RockyDockerRepo.ps1`.
If a local Docker Desktop or proxy setup breaks TLS inside the smoke container,
`ROCKY_DOCKER_REPO_SMOKE_TLS_VERIFY=false` disables TLS verification for that
smoke run only.
When SSH-reachable clean Rocky 9 and Rocky 10 hosts are available without GitHub
Actions, `scripts/dev/Run-RockyStandaloneAcceptance.sh` runs the same live preflight, install, validation, evidence freshness check,
and failure diagnostics from a local checkout. Windows controllers can launch the
same runner through WSL with `scripts/dev/Run-RockyStandaloneAcceptance.ps1`,
which uses `WSLENV` for environment transfer and WSL path translation.
Use `.github/workflows/rocky-standalone-acceptance.yml` when SSH-reachable Rocky
9 and 10 hosts are available. The workflow supports passwordless sudo or an
optional `ROCKY_BECOME_PASSWORD` secret, verifies SSH and sudo access with an
Ansible `raw` command before target Python is required, rejects hosts where
`/opt/greenbone-community` or known Greenbone containers already exist, writes
the same JSON evidence reports, validates that the artifact contains one complete Rocky 9 report and one
complete Rocky 10 report with parseable `validated_at` timestamps from the last
24 hours and matching GitHub workflow run ID and attempt values, including
proof that GSA is bound to `127.0.0.1:443`, GSAD is bound to
`127.0.0.1:9392`, and both endpoints respond locally, and uploads them as a GitHub Actions artifact. Use a
self-hosted runner when the Rocky hosts are on a private network. Self-hosted
runners must be version v2.327.1 or later for the Node.js 24 based actions used
by the workflow. On failure, the workflow also runs
`playbooks/collect-rocky-standalone-diagnostics.yml` and uploads Docker,
Compose, Docker info, SELinux, firewalld, repo trust, service, disk, and recent Compose log diagnostics
as the `rocky-standalone-diagnostics` artifact. The diagnostics report does not include
the generated admin password, but operators should review logs before sharing
the artifact outside trusted teams.
Before dispatching the live workflow, run
`python3 scripts/dev/Test-RockyAcceptanceReadiness.py` from a checkout with
authenticated `gh` to confirm that the workflow is active and required repository secret names are present.

## Upstream Evidence

- Docker documents CentOS Stream 9 and 10 as maintained Docker Engine targets:
  <https://docs.docker.com/engine/install/centos/>
- Docker documents RHEL 9 and 10 as maintained Docker Engine targets:
  <https://docs.docker.com/engine/install/rhel/>
- Rocky Linux 10 release notes define x86_64 support as the x86-64-v3
  baseline and list aarch64 as a supported processor architecture:
  <https://docs.rockylinux.org/release_notes/10_0/>
- Greenbone documents Community Containers on Docker Compose and lists CentOS 9 Stream
  among supported distributions:
  <https://greenbone.github.io/docs/latest/22.4/container/index.html>
- Greenbone states Community Containers are for testing and familiarity, not production setups.
