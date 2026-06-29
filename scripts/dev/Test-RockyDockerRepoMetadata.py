#!/usr/bin/env python3
"""Validate RPM publication needed by Rocky Linux standalone installs."""

from __future__ import annotations

import gzip
import json
import re
import sys
import xml.etree.ElementTree as ET
import urllib.error
import urllib.parse
import urllib.request


DOCKER_REQUIRED_PACKAGES = (
    "docker-ce",
    "docker-ce-cli",
    "containerd.io",
    "docker-buildx-plugin",
    "docker-compose-plugin",
)
ROCKY_PREREQUISITE_PACKAGES = (
    "ca-certificates",
    "curl",
    "dnf-plugins-core",
    "gnupg2",
    "python3",
    "python3-dnf",
    "python3-libdnf",
)
ROCKY_REPOSITORIES = ("BaseOS", "AppStream")

RPM_ARCHITECTURES = ("x86_64", "aarch64")
REQUIRED_CONTAINER_PLATFORMS = {
    ("linux", "amd64"),
    ("linux", "arm64"),
}
ROCKY_SMOKE_IMAGES = (
    "quay.io/rockylinux/rockylinux:9",
    "quay.io/rockylinux/rockylinux:10",
)
GPG_KEY_URL = "https://download.docker.com/linux/centos/gpg"
ROCKY_REPO_URL_TEMPLATE = "https://dl.rockylinux.org/pub/rocky/{releasever}/{repo}/{architecture}/os/"
MANIFEST_ACCEPT = ", ".join(
    (
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
    )
)


def read_url(url: str, headers: dict[str, str] | None = None) -> bytes:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def primary_metadata_url(repo_base_url: str) -> str:
    repomd = ET.fromstring(read_url(f"{repo_base_url}repodata/repomd.xml"))
    namespace = {"repo": "http://linux.duke.edu/metadata/repo"}
    for data in repomd.findall("repo:data", namespace):
        if data.get("type") == "primary":
            location = data.find("repo:location", namespace)
            if location is None or not location.get("href"):
                break
            return f"{repo_base_url}{location.get('href')}"

    raise RuntimeError(f"Repository metadata at {repo_base_url} does not publish primary metadata.")


def rocky_repo_package_names(releasever: int, architecture: str, repo: str, required_packages: set[str]) -> set[str]:
    repo_base_url = ROCKY_REPO_URL_TEMPLATE.format(
        releasever=releasever,
        repo=repo,
        architecture=architecture,
    )
    primary_url = primary_metadata_url(repo_base_url)
    primary_content = read_url(primary_url)
    if primary_url.endswith(".gz"):
        primary_content = gzip.decompress(primary_content)

    primary = ET.fromstring(primary_content)
    namespace = {"common": "http://linux.duke.edu/metadata/common"}
    return {
        name.text
        for name in primary.findall(".//common:name", namespace)
        if name.text in required_packages
    }


def validate_rocky_prerequisites(releasever: int, architecture: str) -> None:
    required_packages = set(ROCKY_PREREQUISITE_PACKAGES)
    available: set[str] = set()
    for repo in ROCKY_REPOSITORIES:
        available.update(rocky_repo_package_names(releasever, architecture, repo, required_packages))

    missing = sorted(required_packages - available)
    if missing:
        raise RuntimeError(
            f"Rocky {releasever} {architecture} official repos are missing prerequisites: "
            f"{', '.join(missing)}"
        )

    print(f"Rocky {releasever} {architecture} official repos publish required prerequisites.")


def published_package_names(packages_url: str, releasever: int, architecture: str) -> set[str]:
    text = read_url(packages_url).decode("utf-8", errors="replace")
    return {
        package
        for package in DOCKER_REQUIRED_PACKAGES
        if re.search(
            rf'href="{re.escape(package)}-[0-9][^"]+\.el{releasever}\.{re.escape(architecture)}\.rpm"',
            text,
        )
    }


def validate_release(releasever: int, architecture: str) -> None:
    packages_url = f"https://download.docker.com/linux/centos/{releasever}/{architecture}/stable/Packages/"
    available = published_package_names(packages_url, releasever, architecture)
    missing = sorted(set(DOCKER_REQUIRED_PACKAGES) - available)

    if missing:
        raise RuntimeError(
            f"Docker CentOS {releasever} {architecture} repo is missing packages: {', '.join(missing)}"
        )

    print(f"Docker CentOS {releasever} {architecture} repo publishes required packages.")


def split_image(image: str) -> tuple[str, str, str]:
    repository, tag = (
        image.rsplit(":", 1)
        if ":" in image.rsplit("/", 1)[-1]
        else (image, "latest")
    )

    if "/" not in repository:
        return "registry-1.docker.io", f"library/{repository}", tag

    registry_candidate, path = repository.split("/", 1)
    if "." in registry_candidate or ":" in registry_candidate or registry_candidate == "localhost":
        return registry_candidate, path, tag

    return "registry-1.docker.io", repository, tag


def parse_bearer_challenge(header: str) -> dict[str, str]:
    if not header.startswith("Bearer "):
        raise RuntimeError(f"Unsupported registry authentication challenge: {header}")

    return {
        match.group(1): match.group(2)
        for match in re.finditer(r'([A-Za-z_][A-Za-z0-9_]*)="([^"]*)"', header)
    }


def registry_bearer_token(challenge: str) -> str:
    params = parse_bearer_challenge(challenge)
    realm = params.get("realm")
    if not realm:
        raise RuntimeError(f"Registry authentication challenge does not include a realm: {challenge}")

    query = urllib.parse.urlencode(
        {
            key: value
            for key, value in params.items()
            if key in {"service", "scope"}
        }
    )
    token_url = f"{realm}?{query}" if query else realm
    payload = json.loads(read_url(token_url).decode("utf-8"))
    token = payload.get("token") or payload.get("access_token")
    if not token:
        raise RuntimeError(f"Registry token response from {realm} did not include a token.")

    return token


def manifest_json(registry: str, path: str, tag: str) -> dict:
    url = f"https://{registry}/v2/{path}/manifests/{tag}"
    headers = {"Accept": MANIFEST_ACCEPT}
    try:
        return json.loads(read_url(url, headers=headers).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            raise
        challenge = exc.headers.get("WWW-Authenticate", "")
        token = registry_bearer_token(challenge)
        headers["Authorization"] = f"Bearer {token}"
        return json.loads(read_url(url, headers=headers).decode("utf-8"))


def manifest_platforms(image: str) -> set[tuple[str, str]]:
    registry, path, tag = split_image(image)
    manifest = manifest_json(registry, path, tag)
    return {
        (
            entry.get("platform", {}).get("os", ""),
            entry.get("platform", {}).get("architecture", ""),
        )
        for entry in manifest.get("manifests", [])
    }


def validate_smoke_image(image: str) -> None:
    platforms = manifest_platforms(image)
    missing = sorted(REQUIRED_CONTAINER_PLATFORMS - platforms)
    if missing:
        rendered = ", ".join(f"{os_name}/{arch}" for os_name, arch in missing)
        raise RuntimeError(f"{image} is missing required platforms: {rendered}")

    print(f"{image} publishes linux/amd64 and linux/arm64 manifests.")


def validate_gpg_key() -> None:
    content = read_url(GPG_KEY_URL).decode("ascii", errors="replace")
    if "BEGIN PGP PUBLIC KEY BLOCK" not in content:
        raise RuntimeError(f"Docker CentOS RPM GPG key URL did not return a PGP public key: {GPG_KEY_URL}")

    print("Docker CentOS RPM GPG key URL publishes a PGP public key.")


def main() -> int:
    try:
        validate_gpg_key()
        for releasever in (9, 10):
            for architecture in RPM_ARCHITECTURES:
                validate_rocky_prerequisites(releasever, architecture)
                validate_release(releasever, architecture)
        for image in ROCKY_SMOKE_IMAGES:
            validate_smoke_image(image)
    except Exception as exc:  # pragma: no cover - command-line guard
        print(f"Rocky metadata validation failed: {exc}", file=sys.stderr)
        return 1

    print("Rocky RPM package and smoke image publication validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
