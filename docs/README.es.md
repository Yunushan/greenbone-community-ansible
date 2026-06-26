# greenbone-community-ansible — Español

Este proyecto instala Greenbone Community Edition con Ansible.

## Topología predeterminada

La instalación predeterminada usa un único nodo maestro. El grupo `greenbone_workers` está vacío.

## Distribuciones compatibles

Ubuntu, Debian, Kali Linux, RHEL, AlmaLinux, Rocky Linux 9/10, Oracle Linux y Alpine Linux.

## Modos de instalación

`greenbone_install_mode: auto` usa paquetes nativos `gvm` en Kali y Docker en la mayoría de los demás sistemas compatibles.
En Rocky Linux 9/10 standalone debes definir `greenbone_install_mode: docker` explícitamente.
También puedes forzar un modo:

```yaml
greenbone_install_mode: docker
```

O:

```yaml
greenbone_install_mode: native
```

## Instalación

```bash
ansible-galaxy collection install -r requirements.yml
ansible-playbook -i inventories/single-master/hosts.yml site.yml
```

La contraseña de administrador se genera localmente en el controlador de Ansible:

```text
.secrets/greenbone_admin_password
```

## Interfaz web

En modo Docker, la interfaz se publica solo en localhost por defecto:

```text
https://127.0.0.1
https://127.0.0.1:9392
```

Para exponerla en la red:

```yaml
greenbone_web_bind_address: "0.0.0.0"
```

Usa firewall, VPN o proxy inverso.

## Nodos worker

Agrega hosts al grupo `greenbone_workers` para usar nodos de escaneo opcionales. El registro remoto de scanners está desactivado hasta configurar certificados OSP.
