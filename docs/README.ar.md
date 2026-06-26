# greenbone-community-ansible — العربية

هذا المشروع يثبّت Greenbone Community Edition باستخدام Ansible.

## البنية الافتراضية

الإعداد الافتراضي هو عقدة رئيسية واحدة. مجموعة `greenbone_workers` تكون فارغة افتراضياً.

## التوزيعات المدعومة

Ubuntu و Debian و Kali Linux و RHEL و AlmaLinux و Rocky Linux 9/10 و Oracle Linux و Alpine Linux.

## أوضاع التثبيت

القيمة `greenbone_install_mode: auto` تستخدم حزم `gvm` الأصلية على Kali، وتستخدم Docker على معظم الأنظمة المدعومة الأخرى.
في تثبيت Rocky Linux 9/10 standalone يجب ضبط `greenbone_install_mode: docker` صراحةً.
يمكن فرض وضع محدد:

```yaml
greenbone_install_mode: docker
```

أو:

```yaml
greenbone_install_mode: native
```

## التثبيت

```bash
ansible-galaxy collection install -r requirements.yml
ansible-playbook -i inventories/single-master/hosts.yml site.yml
```

يتم إنشاء كلمة مرور المدير محلياً على جهاز Ansible controller في:

```text
.secrets/greenbone_admin_password
```

## واجهة الويب

في وضع Docker يتم الربط على localhost افتراضياً:

```text
https://127.0.0.1
https://127.0.0.1:9392
```

لإتاحتها على الشبكة:

```yaml
greenbone_web_bind_address: "0.0.0.0"
```

استخدم جداراً نارياً أو VPN أو reverse proxy.

## عقد العمال

أضف الخوادم إلى مجموعة `greenbone_workers` لاستخدام عقد فحص إضافية. تسجيل الماسحات البعيدة معطّل افتراضياً إلى أن يتم إعداد شهادات OSP.
