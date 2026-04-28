.PHONY: install lint syntax

install:
	ansible-galaxy collection install -r requirements.yml
	ansible-playbook -i inventories/single-master/hosts.yml site.yml

lint:
	ansible-lint
	yamllint .

syntax:
	ansible-playbook -i inventories/single-master/hosts.yml site.yml --syntax-check
