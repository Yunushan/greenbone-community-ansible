# Variables

## Core variables

| Variable | Default | Description |
|---|---:|---|
| `greenbone_install_mode` | `auto` | `auto`, `docker`, or `native`; Rocky Linux 9/10 standalone installs must set `docker` explicitly. |
| `greenbone_rocky_docker_supported_major_versions` | `[9, 10]` | Rocky Linux major versions validated for Docker-only standalone installs. |
| `greenbone_rocky_docker_supported_architectures` | `[x86_64, aarch64]` | Rocky Linux architectures validated for Docker-only standalone installs. Rocky Linux 10 x86_64 follows Rocky's x86-64-v3 baseline. |
| `greenbone_rocky10_min_ansible_core_version` | `2.19.0` | Minimum controller `ansible-core` version for Rocky Linux 10 package tasks. |
| `greenbone_rocky10_x86_64_v3_required_cpu_flag_groups` | x86-64-v3 feature groups | CPU feature groups required when validating Rocky Linux 10 on x86_64. Some groups include Linux flag aliases such as `pni`/`sse3` and `abm`/`lzcnt`. |
| `greenbone_rocky_preflight_min_cpu_cores` | `4` | Minimum CPU cores for the Rocky standalone preflight. |
| `greenbone_rocky_preflight_min_memory_mb` | `8192` | Minimum RAM in MB for the Rocky standalone preflight. |
| `greenbone_rocky_preflight_min_disk_mb` | `61440` | Minimum free disk in MB for the Rocky standalone preflight. |
| `greenbone_rocky_preflight_disk_check_path` | Parent of `greenbone_work_dir` | Filesystem path checked for free disk during Rocky standalone preflight. |
| `greenbone_rocky_validate_service_retries` | `60` | Required-service readiness retries for Rocky standalone validation. |
| `greenbone_rocky_validate_service_delay` | `15` | Delay in seconds between Rocky standalone validation readiness retries. |
| `greenbone_work_dir` | `/opt/greenbone-community` | Directory used on target hosts. |
| `greenbone_admin_user` | `admin` | Greenbone administrator account. |
| `greenbone_controller_secret_dir` | `.secrets` under the controller working directory | Local directory for generated controller-side secrets. |
| `greenbone_admin_password` | `""` | Admin password. Empty generates `.secrets/greenbone_admin_password` on the Ansible controller. |
| `greenbone_web_bind_address` | `127.0.0.1` | GSA bind address in Docker mode and optional native patching. |
| `greenbone_web_https_port` | `443` | Host HTTPS port for Docker nginx. |
| `greenbone_web_gsad_port` | `9392` | Host GSAD port for Docker nginx. |

## Docker variables

| Variable | Default | Description |
|---|---:|---|
| `greenbone_docker_compose_url` | Greenbone official compose URL | Compose file to download. |
| `greenbone_docker_compose_refresh` | `true` | Re-download compose file on each run. |
| `greenbone_docker_pull` | `true` | Pull images before `up -d`. |
| `greenbone_docker_patch_web_ports` | `true` | Patch official localhost ports to configured values. |
| `greenbone_docker_use_official_repo` | `true` | Use Docker official package repos where supported. |

## Native variables

| Variable | Default | Description |
|---|---:|---|
| `greenbone_native_package_name` | `gvm` | Native package name for Debian-family installs. |
| `greenbone_gvmd_user` | `_gvm` | OS user used to run `gvmd` commands. |
| `greenbone_native_setup_force` | `false` | Force `gvm-setup` even when marker exists. |
| `greenbone_native_setup_marker_path` | `/var/lib/gvm/private/CA/clientkey.pem` | Marker used to skip repeated setup. |

## Worker variables

| Variable | Default | Description |
|---|---:|---|
| `greenbone_worker_ospd_port` | `9390` | OSP daemon port on worker nodes. |
| `greenbone_worker_bind_address` | `0.0.0.0` | Worker OSPD bind address. |
| `greenbone_worker_scanner_name` | inventory hostname | Scanner display name. |
| `greenbone_worker_tls_enabled` | `false` | Enables OSP certificate paths in worker config. |
| `greenbone_worker_tls_dir` | `{{ greenbone_work_dir }}/tls` | Worker TLS certificate directory. |

## Recommended overrides

For a private LAN or VPN-accessible master:

```yaml
greenbone_web_bind_address: "0.0.0.0"
greenbone_web_https_port: 443
```

For fully Docker-based installation on all nodes:

```yaml
greenbone_install_mode: docker
```

For Rocky Linux 9/10 standalone installs on x86_64 or aarch64, keep Docker mode.
Rocky Linux 10 x86_64 targets must meet Rocky's x86-64-v3 CPU baseline:

```yaml
greenbone_install_mode: docker
greenbone_docker_use_official_repo: true
```

For Kali native installation:

```yaml
greenbone_install_mode: native
```
