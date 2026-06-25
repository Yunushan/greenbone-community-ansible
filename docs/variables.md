# Variables

## Core variables

| Variable | Default | Description |
|---|---:|---|
| `greenbone_install_mode` | `auto` | `auto`, `docker`, or `native`. |
| `greenbone_rocky_docker_supported_major_versions` | `[9, 10]` | Rocky Linux major versions validated for Docker-only standalone installs. |
| `greenbone_rocky_docker_supported_architectures` | `[x86_64, aarch64]` | Rocky Linux architectures validated for Docker-only standalone installs. |
| `greenbone_work_dir` | `/opt/greenbone-community` | Directory used on target hosts. |
| `greenbone_admin_user` | `admin` | Greenbone administrator account. |
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

For Rocky Linux 9/10 standalone installs on x86_64 or aarch64, keep Docker mode:

```yaml
greenbone_install_mode: docker
greenbone_docker_use_official_repo: true
```

For Kali native installation:

```yaml
greenbone_install_mode: native
```
