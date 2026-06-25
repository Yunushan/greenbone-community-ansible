# greenbone-community-ansible — 简体中文

本项目使用 Ansible 安装 Greenbone Community Edition。

## 默认拓扑

默认部署为一个主节点（single master）。`greenbone_workers` 组默认为空。

## 支持的发行版

Ubuntu、Debian、Kali Linux、RHEL、AlmaLinux、Rocky Linux 9/10、Oracle Linux 和 Alpine Linux。

## 安装模式

`greenbone_install_mode: auto` 会在 Kali 上使用原生 `gvm` 包，在其他支持的系统上使用 Docker。也可以强制指定：

```yaml
greenbone_install_mode: docker
```

或：

```yaml
greenbone_install_mode: native
```

## 安装

```bash
ansible-galaxy collection install -r requirements.yml
ansible-playbook -i inventories/single-master/hosts.yml site.yml
```

管理员密码会在 Ansible 控制端生成并保存在：

```text
.secrets/greenbone_admin_password
```

## Web 界面

Docker 模式默认只绑定本机：

```text
https://127.0.0.1
https://127.0.0.1:9392
```

如需对网络开放：

```yaml
greenbone_web_bind_address: "0.0.0.0"
```

请务必配合防火墙、VPN 或反向代理。

## 工作节点

将主机加入 `greenbone_workers` 组即可启用可选扫描工作节点。远程扫描器注册需要 OSP 证书，因此默认关闭。
