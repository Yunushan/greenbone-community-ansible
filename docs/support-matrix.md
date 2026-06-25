# Support Matrix

This project treats Greenbone Community Containers as the portable installation path.
Native package installation is intentionally conservative and is aimed at Kali or Debian-family lab hosts.

## Docker Standalone Targets

| Distribution | Versions | Architectures | Mode | Docker repository | Status |
|---|---:|---|---|---|---|
| Rocky Linux | 9.x | x86_64, aarch64 | Docker standalone master | Docker CentOS RPM repo | Supported by this project |
| Rocky Linux | 10.x | x86_64, aarch64 | Docker standalone master | Docker CentOS RPM repo | Supported by this project |

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
downloads the official Greenbone Community Containers compose file, starts it with Docker Compose,
and keeps the default web bind on localhost.

It does not mean native `gvm` packages are supported on Rocky Linux.

The CI smoke check pulls `rockylinux:9` and `rockylinux:10`, adds Docker's CentOS RPM repo,
verifies that Docker Engine and Docker Compose plugin packages resolve for both major versions,
then downloads Greenbone's official compose file and checks that Docker Compose can parse it.
CI also validates Docker's CentOS 9 and 10 RPM package publication for x86_64
and aarch64 directly so package publication failures are caught even before the
container smoke install. It also checks that Greenbone's current Community
Container compose images publish both linux/amd64 and linux/arm64 manifests.
CI also runs `ansible-playbook --syntax-check` and `--list-hosts` against the
Rocky standalone inventory.
A post-install validation playbook is provided at
`playbooks/validate-rocky-standalone.yml` for live Rocky 9/10 targets.
It waits for required core compose services, checks the local HTTPS endpoint,
checks that the generated admin password file exists, is non-empty, and is mode
`0600` when using the default password generation path, and writes per-host
evidence reports under `.secrets/rocky-standalone-evidence/`.

The CI smoke check does not start the full Greenbone stack because GitHub-hosted
runners are not Rocky Linux hosts. A full acceptance run means installing with
`site.yml` on real Rocky 9 and Rocky 10 hosts, then running the post-install
validation playbook.
Use `.github/workflows/rocky-standalone-acceptance.yml` when SSH-reachable Rocky
9 and 10 hosts are available. The workflow writes the same JSON evidence reports
validates that the artifact contains one complete Rocky 9 report and one
complete Rocky 10 report, and uploads them as a GitHub Actions artifact. Use a
self-hosted runner when the Rocky hosts are on a private network.

## Upstream Evidence

- Docker documents CentOS Stream 9 and 10 as maintained Docker Engine targets.
- Docker documents RHEL 9 and 10 as maintained Docker Engine targets.
- Greenbone documents Community Containers on Docker Compose and lists CentOS 9 Stream among supported distributions.
- Greenbone states Community Containers are for testing and familiarity, not production setups.
