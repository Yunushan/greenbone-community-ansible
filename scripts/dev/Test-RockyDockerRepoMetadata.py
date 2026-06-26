#!/usr/bin/env python3
"""Validate RPM publication needed by Rocky Linux standalone installs."""

from __future__ import annotations

import gzip
import re
import sys
import xml.etree.ElementTree as ET
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
GPG_KEY_URL = "https://download.docker.com/linux/centos/gpg"
ROCKY_REPO_URL_TEMPLATE = "https://dl.rockylinux.org/pub/rocky/{releasever}/{repo}/{architecture}/os/"


def read_url(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
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
    except Exception as exc:  # pragma: no cover - command-line guard
        print(f"Rocky RPM metadata validation failed: {exc}", file=sys.stderr)
        return 1

    print("Rocky RPM package publication validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
