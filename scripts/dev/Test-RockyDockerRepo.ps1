$ErrorActionPreference = "Stop"

function Invoke-NativeChecked {
    param(
        [scriptblock] $Command,
        [string] $Description
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "${Description} failed with exit code ${LASTEXITCODE}."
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is required for Rocky Docker repository smoke validation."
}

$tlsVerify = $env:ROCKY_DOCKER_REPO_SMOKE_TLS_VERIFY
if ([string]::IsNullOrWhiteSpace($tlsVerify)) {
    $tlsVerify = $env:ROCKY_DOCKER_REPO_SMOKE_DNF_SSLVERIFY
}
if ([string]::IsNullOrWhiteSpace($tlsVerify)) {
    $tlsVerify = "true"
}
if ($tlsVerify -notin @("true", "false")) {
    throw "ROCKY_DOCKER_REPO_SMOKE_TLS_VERIFY must be true or false."
}

Invoke-NativeChecked -Description "Docker readiness check" -Command {
    docker info
}

$packages = @(
    "docker-ce",
    "docker-ce-cli",
    "containerd.io",
    "docker-buildx-plugin",
    "docker-compose-plugin"
)
$packageText = $packages -join " "

$images = @(
    "quay.io/rockylinux/rockylinux:9",
    "quay.io/rockylinux/rockylinux:10"
)

foreach ($image in $images) {
    Write-Host "Validating Docker RPM repository support on ${image}"
    $script = @"
set -euo pipefail
tls_verify="`${ROCKY_DOCKER_REPO_SMOKE_TLS_VERIFY:-true}"
case "`${tls_verify}" in
  true | false) ;;
  *)
    echo 'ROCKY_DOCKER_REPO_SMOKE_TLS_VERIFY must be true or false.' >&2
    exit 2
    ;;
esac
dnf_options=()
curl_options=()
if [ "`${tls_verify}" = false ]; then
  echo 'WARNING: TLS verification is disabled for this local Rocky smoke container.' >&2
  dnf_options+=(--setopt=sslverify=false)
  curl_options+=(-k)
fi
curl_package=curl
if rpm -q curl-minimal >/dev/null 2>&1; then
  curl_package=curl-minimal
fi
dnf "`${dnf_options[@]}" -y install ca-certificates "`${curl_package}" dnf-plugins-core python3
curl "`${curl_options[@]}" -fsSL https://download.docker.com/linux/centos/docker-ce.repo \
  -o /etc/yum.repos.d/docker-ce.repo
dnf "`${dnf_options[@]}" -y makecache --disablerepo='*' --enablerepo='docker-ce-stable'
if dnf "`${dnf_options[@]}" -q repoquery --disablerepo='*' --enablerepo='docker-ce-stable' ${packageText}; then
  exit 0
fi
dnf "`${dnf_options[@]}" -y install --downloadonly --setopt=install_weak_deps=False ${packageText}
"@

    Invoke-NativeChecked -Description "Docker RPM repository validation on ${image}" -Command {
        docker run --rm -e "ROCKY_DOCKER_REPO_SMOKE_TLS_VERIFY=${tlsVerify}" $image bash -lc $script
    }
}

$composeDir = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $composeDir | Out-Null

try {
    $composeFile = Join-Path $composeDir "compose.yaml"
    Invoke-WebRequest -Uri "https://greenbone.github.io/docs/latest/_static/compose.yaml" -OutFile $composeFile
    Invoke-NativeChecked -Description "Greenbone compose config validation" -Command {
        docker compose -f $composeFile config
    }
}
finally {
    Remove-Item -LiteralPath $composeDir -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Rocky Docker standalone smoke validation passed."
