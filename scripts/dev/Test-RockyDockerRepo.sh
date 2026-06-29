#!/usr/bin/env bash
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required for Rocky Docker repository smoke validation." >&2
  exit 127
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker must be running for Rocky Docker repository smoke validation." >&2
  exit 1
fi

tls_verify="${ROCKY_DOCKER_REPO_SMOKE_TLS_VERIFY:-${ROCKY_DOCKER_REPO_SMOKE_DNF_SSLVERIFY:-true}}"
case "${tls_verify}" in
  true | false) ;;
  *)
    echo "ROCKY_DOCKER_REPO_SMOKE_TLS_VERIFY must be true or false." >&2
    exit 2
    ;;
esac

packages=(
  docker-ce
  docker-ce-cli
  containerd.io
  docker-buildx-plugin
  docker-compose-plugin
)

images=(
  quay.io/rockylinux/rockylinux:9
  quay.io/rockylinux/rockylinux:10
)

for image in "${images[@]}"; do
  echo "Validating Docker RPM repository support on ${image}"

  docker run --rm \
    -e ROCKY_DOCKER_REPO_SMOKE_TLS_VERIFY="${tls_verify}" \
    "${image}" bash -lc "
    set -euo pipefail
    tls_verify=\"\${ROCKY_DOCKER_REPO_SMOKE_TLS_VERIFY:-true}\"
    case \"\${tls_verify}\" in
      true | false) ;;
      *)
        echo 'ROCKY_DOCKER_REPO_SMOKE_TLS_VERIFY must be true or false.' >&2
        exit 2
        ;;
    esac
    dnf_options=()
    curl_options=()
    if [ \"\${tls_verify}\" = false ]; then
      echo 'WARNING: TLS verification is disabled for this local Rocky smoke container.' >&2
      dnf_options+=(--setopt=sslverify=false)
      curl_options+=(-k)
    fi
    curl_package=curl
    if rpm -q curl-minimal >/dev/null 2>&1; then
      curl_package=curl-minimal
    fi
    dnf \"\${dnf_options[@]}\" -y install ca-certificates \"\${curl_package}\" dnf-plugins-core python3
    curl \"\${curl_options[@]}\" -fsSL https://download.docker.com/linux/centos/docker-ce.repo \
      -o /etc/yum.repos.d/docker-ce.repo
    dnf \"\${dnf_options[@]}\" -y makecache --disablerepo='*' --enablerepo='docker-ce-stable'
    if dnf \"\${dnf_options[@]}\" -q repoquery --disablerepo='*' --enablerepo='docker-ce-stable' ${packages[*]}; then
      exit 0
    fi
    dnf \"\${dnf_options[@]}\" -y install --downloadonly --setopt=install_weak_deps=False ${packages[*]}
  "
done

compose_dir="$(mktemp -d)"
trap 'rm -rf "${compose_dir}"' EXIT

echo "Validating Greenbone Community Containers compose file"
curl -fsSL https://greenbone.github.io/docs/latest/_static/compose.yaml \
  -o "${compose_dir}/compose.yaml"
docker compose -f "${compose_dir}/compose.yaml" config >/dev/null

echo "Rocky Docker standalone smoke validation passed."
