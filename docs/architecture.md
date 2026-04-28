# Architecture

## Default: single master

The default inventory contains one `greenbone_masters` host and an empty `greenbone_workers` group.

In Docker mode the master uses Greenbone Community Containers. The role downloads the official Greenbone `compose.yaml`, optionally patches localhost web ports, pulls images, and starts the stack.

In native mode the master installs the `gvm` package and runs `gvm-setup` on Debian-family systems, especially Kali Linux.

## Optional workers

Workers are optional scanner hosts. Add them to the `greenbone_workers` group when you want scanner capacity outside the master host.

```yaml
greenbone_workers:
  hosts:
    greenbone-worker-01:
      ansible_host: 192.0.2.21
    greenbone-worker-02:
      ansible_host: 192.0.2.22
```

The worker role deploys `ospd-openvas` and scanner support components. Remote scanner registration into `gvmd` is disabled by default because production-safe OSP registration requires certificate handling.

## Remote scanner registration

After you generate and distribute OSP certificates, review and run:

```bash
ansible-playbook -i inventories/multi-node/hosts.yml playbooks/register-workers.yml \
  -e greenbone_worker_registration_enabled=true
```

Before using it, verify these paths on the master:

```yaml
greenbone_scanner_ca_pub: /var/lib/gvm/CA/cacert.pem
greenbone_scanner_key_pub: /var/lib/gvm/CA/clientcert.pem
greenbone_scanner_key_priv: /var/lib/gvm/private/CA/clientkey.pem
```

For Docker master mode, those paths must exist inside the `gvmd` container. That usually means mounting or copying certificates into the compose stack. Because certificate strategies differ by environment, this repository does not force a universal certificate layout.

## Ports

| Component | Default bind | Default port |
|---|---:|---:|
| Docker GSA HTTPS | `127.0.0.1` | `443` |
| Docker GSAD alternate | `127.0.0.1` | `9392` |
| Worker OSPD | `0.0.0.0` | `9390` |

## Security model

Greenbone scanner containers need network privileges to perform vulnerability scanning. Do not deploy workers on untrusted hosts. Limit OSPD access to the master using a host firewall or security group.
