#!/usr/bin/env python3
"""Validate Docker RPM publication needed by Rocky Linux standalone installs."""

from __future__ import annotations

import re
import sys
import urllib.request


REQUIRED_PACKAGES = (
    "docker-ce",
    "docker-ce-cli",
    "containerd.io",
    "docker-buildx-plugin",
    "docker-compose-plugin",
)

RPM_ARCHITECTURES = ("x86_64", "aarch64")


def read_url(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def published_package_names(packages_url: str, releasever: int, architecture: str) -> set[str]:
    text = read_url(packages_url).decode("utf-8", errors="replace")
    return {
        package
        for package in REQUIRED_PACKAGES
        if re.search(
            rf'href="{re.escape(package)}-[0-9][^"]+\.el{releasever}\.{re.escape(architecture)}\.rpm"',
            text,
        )
    }


def validate_release(releasever: int, architecture: str) -> None:
    packages_url = f"https://download.docker.com/linux/centos/{releasever}/{architecture}/stable/Packages/"
    available = published_package_names(packages_url, releasever, architecture)
    missing = sorted(set(REQUIRED_PACKAGES) - available)

    if missing:
        raise RuntimeError(
            f"Docker CentOS {releasever} {architecture} repo is missing packages: {', '.join(missing)}"
        )

    print(f"Docker CentOS {releasever} {architecture} repo publishes required packages.")


def main() -> int:
    try:
        for releasever in (9, 10):
            for architecture in RPM_ARCHITECTURES:
                validate_release(releasever, architecture)
    except Exception as exc:  # pragma: no cover - command-line guard
        print(f"Rocky Docker repo metadata validation failed: {exc}", file=sys.stderr)
        return 1

    print("Rocky Docker repo package publication validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
