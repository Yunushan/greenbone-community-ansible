ROCKY_INVENTORY ?= inventories/rocky-standalone/hosts.yml

.PHONY: install lint syntax rocky-standalone rocky-syntax rocky-validate

install:
	ansible-galaxy collection install -r requirements.yml
	ansible-playbook -i inventories/single-master/hosts.yml site.yml

lint:
	ansible-lint
	yamllint .

syntax:
	ansible-playbook -i inventories/single-master/hosts.yml site.yml --syntax-check

rocky-standalone:
	ansible-galaxy collection install -r requirements.yml
	ansible-playbook -i $(ROCKY_INVENTORY) site.yml

rocky-syntax:
	ansible-playbook -i $(ROCKY_INVENTORY) site.yml --syntax-check
	ansible-playbook -i $(ROCKY_INVENTORY) playbooks/validate-rocky-standalone.yml --syntax-check

rocky-validate:
	ansible-playbook -i $(ROCKY_INVENTORY) playbooks/validate-rocky-standalone.yml
