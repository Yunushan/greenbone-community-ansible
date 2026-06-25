#!/usr/bin/env python3
"""Validate Greenbone Community container platform publication."""

from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request


COMPOSE_URL = "https://greenbone.github.io/docs/latest/_static/compose.yaml"
REQUIRED_PLATFORMS = {
    ("linux", "amd64"),
    ("linux", "arm64"),
}
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


def compose_images() -> list[str]:
    compose = read_url(COMPOSE_URL).decode("utf-8", errors="replace")
    return sorted(set(re.findall(r"^\s*image:\s*(\S+)\s*$", compose, re.MULTILINE)))


def split_image(image: str) -> tuple[str, str, str]:
    repository, tag = (
        image.rsplit(":", 1)
        if ":" in image.rsplit("/", 1)[-1]
        else (image, "latest")
    )
    registry, path = repository.split("/", 1)
    return registry, path, tag


def registry_token(registry: str, path: str) -> str:
    query = urllib.parse.urlencode(
        {
            "service": "harbor-registry",
            "scope": f"repository:{path}:pull",
        }
    )
    payload = json.loads(read_url(f"https://{registry}/service/token?{query}"))
    return payload["token"]


def manifest_platforms(image: str) -> set[tuple[str, str]]:
    registry, path, tag = split_image(image)
    token = registry_token(registry, path)
    manifest = json.loads(
        read_url(
            f"https://{registry}/v2/{path}/manifests/{tag}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": MANIFEST_ACCEPT,
            },
        )
    )

    return {
        (
            entry.get("platform", {}).get("os", ""),
            entry.get("platform", {}).get("architecture", ""),
        )
        for entry in manifest.get("manifests", [])
    }


def main() -> int:
    try:
        for image in compose_images():
            platforms = manifest_platforms(image)
            missing = sorted(REQUIRED_PLATFORMS - platforms)
            if missing:
                rendered = ", ".join(f"{os_name}/{arch}" for os_name, arch in missing)
                raise RuntimeError(f"{image} is missing required platforms: {rendered}")

            print(f"{image} publishes linux/amd64 and linux/arm64 manifests.")
    except Exception as exc:  # pragma: no cover - command-line guard
        print(f"Greenbone container platform validation failed: {exc}", file=sys.stderr)
        return 1

    print("Greenbone container platform validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
