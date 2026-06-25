# greenbone-community-ansible — हिन्दी

यह प्रोजेक्ट Ansible की मदद से Greenbone Community Edition इंस्टॉल करता है।

## डिफ़ॉल्ट टोपोलॉजी

डिफ़ॉल्ट रूप से एक ही मास्टर नोड इंस्टॉल होता है। `greenbone_workers` समूह खाली रहता है।

## समर्थित वितरण

Ubuntu, Debian, Kali Linux, RHEL, AlmaLinux, Rocky Linux 9/10, Oracle Linux और Alpine Linux।

## इंस्टॉलेशन मोड

`greenbone_install_mode: auto` Kali पर native `gvm` पैकेज का उपयोग करता है और अन्य समर्थित सिस्टम पर Docker मोड का उपयोग करता है। आप मोड को जबरन सेट कर सकते हैं:

```yaml
greenbone_install_mode: docker
```

या:

```yaml
greenbone_install_mode: native
```

## इंस्टॉल करें

```bash
ansible-galaxy collection install -r requirements.yml
ansible-playbook -i inventories/single-master/hosts.yml site.yml
```

एडमिन पासवर्ड Ansible controller पर यहां बनेगा:

```text
.secrets/greenbone_admin_password
```

## Web UI

Docker मोड में UI डिफ़ॉल्ट रूप से localhost पर bind होता है:

```text
https://127.0.0.1
https://127.0.0.1:9392
```

नेटवर्क पर खोलने के लिए:

```yaml
greenbone_web_bind_address: "0.0.0.0"
```

Firewall, VPN या reverse proxy सुरक्षा का उपयोग करें।

## Worker nodes

अतिरिक्त scanner worker nodes के लिए hosts को `greenbone_workers` group में जोड़ें। Remote scanner registration तब तक बंद रहता है जब तक OSP certificates configure न हों।
