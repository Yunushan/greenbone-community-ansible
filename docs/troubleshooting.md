# Troubleshooting

## First login works but feeds are not ready

Initial feed loading can take minutes to hours. In GSA, check **Administration → Feed Status**.

For Docker mode, you can follow logs:

```bash
sudo docker compose -f /opt/greenbone-community/compose.yaml logs -f
```

## Docker compose cannot bind port 443

Another service may already be using port 443. Override the port:

```yaml
greenbone_web_https_port: 8443
```

Run again:

```bash
ansible-playbook -i inventories/single-master/hosts.yml site.yml
```

## Native mode fails on non-Kali distributions

Native packaging differs by distribution. Use Docker mode for the widest support:

```yaml
greenbone_install_mode: docker
```

## Rocky Linux 9/10 Docker setup fails

Rocky Linux support is Docker-only in this project. Check:

1. `greenbone_install_mode` is `docker`.
2. The target is Rocky Linux 9 or 10.
3. The target architecture is x86_64 or aarch64.
4. `greenbone_docker_use_official_repo` is `true` when the role installs Docker.
5. The host can reach `download.docker.com` and `registry.community.greenbone.net`.
6. Conflicting Docker or Podman compatibility packages were removed by the Docker role.
7. The Docker service is running: `sudo systemctl status docker`.

## I cannot access the web UI from another machine

The default bind address is localhost for safety. Expose it only if you have access controls:

```yaml
greenbone_web_bind_address: "0.0.0.0"
```

## Worker registration fails

Check:

1. The worker host can be reached from the master on `greenbone_worker_ospd_port`.
2. OSP certificates exist on the master and worker.
3. The paths in `greenbone_scanner_ca_pub`, `greenbone_scanner_key_pub`, and `greenbone_scanner_key_priv` are valid in the execution context.
4. Firewalls allow traffic only from the master to the worker OSPD port.
