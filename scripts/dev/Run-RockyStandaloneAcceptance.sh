#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${repo_root}"

python_bin="${PYTHON:-python3}"
acceptance_inventory="${ACCEPTANCE_INVENTORY:-inventories/rocky-standalone/hosts.acceptance.yml}"
max_age_hours="${ROCKY_ACCEPTANCE_MAX_AGE_HOURS:-24}"
diagnostics_enabled=0
cleanup_paths=()

fail() {
  echo "Rocky standalone local acceptance failed: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

require_env() {
  if [ -z "$(printenv "$1")" ]; then
    fail "Missing required environment variable $1."
  fi
}

cleanup() {
  status=$?
  if [ "${diagnostics_enabled}" -eq 1 ] && [ "${status}" -ne 0 ]; then
    echo "Acceptance failed; collecting Rocky diagnostics." >&2
    ansible-playbook -i "${acceptance_inventory}" playbooks/collect-rocky-standalone-diagnostics.yml || true
  fi
  for path in "${cleanup_paths[@]}"; do
    rm -rf "${path}"
  done
  exit "${status}"
}

trap cleanup EXIT

self_test() {
  export ROCKY_ACCEPTANCE_SELF_TEST_PRESENT=value
  require_env ROCKY_ACCEPTANCE_SELF_TEST_PRESENT
  if (unset ROCKY_ACCEPTANCE_SELF_TEST_MISSING; require_env ROCKY_ACCEPTANCE_SELF_TEST_MISSING) 2>/dev/null; then
    fail "Self-test did not reject a missing required environment variable."
  fi
  if (export ROCKY_ACCEPTANCE_SELF_TEST_EMPTY=; require_env ROCKY_ACCEPTANCE_SELF_TEST_EMPTY) 2>/dev/null; then
    fail "Self-test did not reject an empty required environment variable."
  fi
  echo "Rocky standalone local acceptance runner self-test passed."
}

if [ "${1:-}" = "--self-test" ]; then
  self_test
  exit 0
fi
if [ "$#" -gt 0 ]; then
  fail "Unsupported argument: $1"
fi

require_command "${python_bin}"
require_command ansible
require_command ansible-galaxy
require_command ansible-inventory
require_command ansible-playbook
require_command ssh-keygen

require_env ROCKY9_HOST
require_env ROCKY10_HOST
require_env ROCKY_SSH_USER

if [ "${ROCKY9_HOST}" = "${ROCKY10_HOST}" ]; then
  fail "ROCKY9_HOST and ROCKY10_HOST must be different hosts."
fi

ROCKY_SSH_PORT="${ROCKY_SSH_PORT:-22}"
if ! [[ "${ROCKY_SSH_PORT}" =~ ^[0-9]+$ ]] || [ "${ROCKY_SSH_PORT}" -lt 1 ] || [ "${ROCKY_SSH_PORT}" -gt 65535 ]; then
  fail "ROCKY_SSH_PORT must be an integer between 1 and 65535."
fi
export ROCKY_SSH_PORT

if [ -n "${ROCKY_ACCEPTANCE_SSH_DIR:-}" ]; then
  ssh_dir="${ROCKY_ACCEPTANCE_SSH_DIR}"
  install -d -m 700 "${ssh_dir}"
else
  ssh_dir="$(mktemp -d "${TMPDIR:-/tmp}/rocky-standalone-ssh.XXXXXX")"
  cleanup_paths+=("${ssh_dir}")
fi

if [ -n "${ROCKY_SSH_PRIVATE_KEY_FILE:-}" ]; then
  [ -r "${ROCKY_SSH_PRIVATE_KEY_FILE}" ] || fail "ROCKY_SSH_PRIVATE_KEY_FILE is not readable."
  ssh_key_file="${ROCKY_SSH_PRIVATE_KEY_FILE}"
else
  require_env ROCKY_SSH_PRIVATE_KEY
  ssh_key_file="${ssh_dir}/id_ed25519"
  printf '%s\n' "${ROCKY_SSH_PRIVATE_KEY}" > "${ssh_key_file}"
  chmod 600 "${ssh_key_file}"
fi

if [ -n "${ROCKY_SSH_KNOWN_HOSTS_FILE:-}" ]; then
  [ -s "${ROCKY_SSH_KNOWN_HOSTS_FILE}" ] || fail "ROCKY_SSH_KNOWN_HOSTS_FILE is empty or missing."
  known_hosts_file="${ROCKY_SSH_KNOWN_HOSTS_FILE}"
else
  known_hosts_file="${ssh_dir}/known_hosts"
  if [ -n "${ROCKY_SSH_KNOWN_HOSTS:-}" ]; then
    printf '%s\n' "${ROCKY_SSH_KNOWN_HOSTS}" > "${known_hosts_file}"
  else
    require_command ssh-keyscan
    : > "${known_hosts_file}"
    for host in "${ROCKY9_HOST}" "${ROCKY10_HOST}"; do
      if ! host_keys="$(ssh-keyscan -T 10 -p "${ROCKY_SSH_PORT}" -H "${host}")" || [ -z "${host_keys}" ]; then
        fail "Failed to collect SSH host key for ${host}."
      fi
      printf '%s\n' "${host_keys}" >> "${known_hosts_file}"
    done
  fi
  chmod 600 "${known_hosts_file}"
fi

if ! ssh-keygen -l -f "${known_hosts_file}" >/dev/null; then
  fail "SSH known_hosts does not contain valid host keys."
fi

rm -rf .secrets/rocky-standalone-evidence
rm -rf .secrets/rocky-standalone-diagnostics

export GITHUB_RUN_ID="${GITHUB_RUN_ID:-local-$(date -u +%Y%m%dT%H%M%SZ)}"
export GITHUB_RUN_ATTEMPT="${GITHUB_RUN_ATTEMPT:-1}"

if [ "${ROCKY_ACCEPTANCE_SKIP_GALAXY:-0}" != "1" ]; then
  ansible-galaxy collection install -r requirements.yml
fi

"${python_bin}" scripts/dev/Render-RockyAcceptanceInventory.py \
  --output "${acceptance_inventory}" \
  --ssh-key-file "${ssh_key_file}" \
  --known-hosts-file "${known_hosts_file}"

ansible-inventory -i "${acceptance_inventory}" --graph

ansible greenbone_masters \
  -i "${acceptance_inventory}" \
  -m ansible.builtin.raw \
  -a 'id -u && test -r /etc/os-release' \
  --become

clean_host_script="$(cat <<'EOF'
set -eu
if [ -e /opt/greenbone-community ]; then
  echo "Rocky acceptance hosts must be clean; /opt/greenbone-community already exists."
  exit 1
fi
if command -v docker >/dev/null 2>&1; then
  docker_name_format="$(printf "{%s}" "{.Names}")"
  compose_project_label="com.docker.compose.project=greenbone-community"
  greenbone_service_pattern="(gsa|gsad|gvmd|nginx|openvas|openvasd|ospd-openvas|pg-gvm|redis-server)"
  greenbone_container_pattern="^((greenbone-community[-_])?${greenbone_service_pattern}([-_][0-9]+)?)$"
  existing="$(docker ps -a --filter "label=${compose_project_label}" --format "${docker_name_format}")"
  if [ -z "${existing}" ]; then
    existing="$(
      docker ps -a --format "${docker_name_format}" |
      grep -E "${greenbone_container_pattern}" || true
    )"
  fi
  if [ -n "${existing}" ]; then
    echo "Rocky acceptance hosts must be clean; Greenbone containers already exist: ${existing}"
    exit 1
  fi
fi
EOF
)"

ansible greenbone_masters \
  -i "${acceptance_inventory}" \
  -m ansible.builtin.raw \
  -a "${clean_host_script}" \
  --become

diagnostics_enabled=1

ansible-playbook -i "${acceptance_inventory}" playbooks/preflight-rocky-standalone.yml
ansible-playbook -i "${acceptance_inventory}" site.yml
ansible-playbook -i "${acceptance_inventory}" playbooks/validate-rocky-standalone.yml

"${python_bin}" scripts/dev/Test-RockyAcceptanceEvidence.py \
  --max-age-hours "${max_age_hours}" \
  --run-id "${GITHUB_RUN_ID}" \
  --run-attempt "${GITHUB_RUN_ATTEMPT}"

diagnostics_enabled=0
echo "Rocky standalone local acceptance passed."
