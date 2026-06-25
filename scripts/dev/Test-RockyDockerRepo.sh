#!/usr/bin/env bash
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required for Rocky Docker repository smoke validation." >&2
  exit 127
fi

packages=(
  docker-ce
  docker-ce-cli
  containerd.io
  docker-buildx-plugin
  docker-compose-plugin
)

for major in 9 10; do
  image="rockylinux:${major}"
  echo "Validating Docker RPM repository support on ${image}"

  docker run --rm "${image}" bash -lc "
    set -euo pipefail
    dnf -y install ca-certificates curl dnf-plugins-core python3
    curl -fsSL https://download.docker.com/linux/centos/docker-ce.repo \
      -o /etc/yum.repos.d/docker-ce.repo
    dnf -y makecache --disablerepo='*' --enablerepo='docker-ce-stable'
    if dnf -q repoquery --disablerepo='*' --enablerepo='docker-ce-stable' ${packages[*]}; then
      exit 0
    fi
    dnf -y install --downloadonly --setopt=install_weak_deps=False ${packages[*]}
  "
done

compose_dir="$(mktemp -d)"
trap 'rm -rf "${compose_dir}"' EXIT

echo "Validating Greenbone Community Containers compose file"
curl -fsSL https://greenbone.github.io/docs/latest/_static/compose.yaml \
  -o "${compose_dir}/compose.yaml"
docker compose -f "${compose_dir}/compose.yaml" config >/dev/null

echo "Rocky Docker standalone smoke validation passed."
