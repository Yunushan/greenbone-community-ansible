#!/usr/bin/env python3
"""Render the temporary Rocky standalone acceptance inventory."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


class InventoryError(Exception):
    """Raised when acceptance inventory inputs are invalid."""


def scalar(value: object) -> str:
    return json.dumps(value)


def required_env(env: dict[str, str], name: str) -> str:
    value = env.get(name, "")
    if not value:
        raise InventoryError(f"Missing required environment variable {name}.")
    return value


def ssh_port(env: dict[str, str]) -> int:
    value = env.get("ROCKY_SSH_PORT", "22")
    try:
        port = int(value)
    except ValueError as exc:
        raise InventoryError("ROCKY_SSH_PORT must be an integer between 1 and 65535.") from exc

    if port < 1 or port > 65535:
        raise InventoryError("ROCKY_SSH_PORT must be an integer between 1 and 65535.")
    return port


def inventory_lines(
    env: dict[str, str],
    ssh_key_file: str,
    known_hosts_file: str,
) -> list[str]:
    rocky9_host = required_env(env, "ROCKY9_HOST")
    rocky10_host = required_env(env, "ROCKY10_HOST")
    ssh_user = required_env(env, "ROCKY_SSH_USER")

    if rocky9_host == rocky10_host:
        raise InventoryError("ROCKY9_HOST and ROCKY10_HOST must be different hosts.")

    inventory_vars = [
        ("greenbone_install_mode", scalar("docker")),
        ("greenbone_docker_use_official_repo", "true"),
        ("greenbone_web_bind_address", scalar("127.0.0.1")),
        ("ansible_user", scalar(ssh_user)),
        ("ansible_port", str(ssh_port(env))),
        ("ansible_ssh_private_key_file", scalar(ssh_key_file)),
        (
            "ansible_ssh_common_args",
            scalar(
                "-o StrictHostKeyChecking=yes "
                f"-o UserKnownHostsFile={known_hosts_file}"
            ),
        ),
    ]
    if env.get("ROCKY_BECOME_PASSWORD"):
        inventory_vars.append(("ansible_become_password", scalar(env["ROCKY_BECOME_PASSWORD"])))
    if env.get("GITHUB_RUN_ID"):
        inventory_vars.append(("greenbone_acceptance_run_id", scalar(env["GITHUB_RUN_ID"])))
    if env.get("GITHUB_RUN_ATTEMPT"):
        inventory_vars.append(("greenbone_acceptance_run_attempt", scalar(env["GITHUB_RUN_ATTEMPT"])))

    lines = ["---", "all:", "  vars:"]
    lines.extend(f"    {name}: {value}" for name, value in inventory_vars)
    lines.extend(
        [
            "  children:",
            "    greenbone_masters:",
            "      hosts:",
            "        rocky9-standalone:",
            f"          ansible_host: {scalar(rocky9_host)}",
            "          greenbone_expected_rocky_major_version: 9",
            "        rocky10-standalone:",
            f"          ansible_host: {scalar(rocky10_host)}",
            "          greenbone_expected_rocky_major_version: 10",
            "    greenbone_workers:",
            "      hosts: {}",
        ]
    )
    return lines


def render_inventory(
    output: Path,
    env: dict[str, str],
    ssh_key_file: str,
    known_hosts_file: str,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "\n".join(inventory_lines(env, ssh_key_file, known_hosts_file)) + "\n",
        encoding="utf-8",
    )


def expect_error(env: dict[str, str], expected: str) -> None:
    try:
        inventory_lines(env, "/tmp/key", "/tmp/known_hosts")
    except InventoryError as exc:
        if expected not in str(exc):
            raise
    else:
        raise InventoryError(f"Self-test did not reject inventory input with {expected}.")


def run_self_test() -> None:
    env = {
        "ROCKY9_HOST": "192.0.2.9",
        "ROCKY10_HOST": "192.0.2.10",
        "ROCKY_SSH_USER": "rocky",
        "ROCKY_SSH_PORT": "2222",
    }
    lines = inventory_lines(env, "/home/runner/.ssh/id_ed25519", "/home/runner/.ssh/known_hosts")
    text = "\n".join(lines)
    for expected in (
        'greenbone_install_mode: "docker"',
        "greenbone_docker_use_official_repo: true",
        'ansible_user: "rocky"',
        "ansible_port: 2222",
        'ansible_ssh_private_key_file: "/home/runner/.ssh/id_ed25519"',
        "-o StrictHostKeyChecking=yes -o UserKnownHostsFile=/home/runner/.ssh/known_hosts",
        "rocky9-standalone:",
        "greenbone_expected_rocky_major_version: 9",
        "rocky10-standalone:",
        "greenbone_expected_rocky_major_version: 10",
        "greenbone_workers:",
        "hosts: {}",
    ):
        if expected not in text:
            raise InventoryError(f"Self-test missing rendered content: {expected}")
    if "ansible_become_password" in text:
        raise InventoryError("Self-test rendered unexpected become password.")

    env_with_become = dict(env)
    env_with_become["ROCKY_BECOME_PASSWORD"] = "secret"
    become_text = "\n".join(inventory_lines(env_with_become, "/tmp/key", "/tmp/known_hosts"))
    if 'ansible_become_password: "secret"' not in become_text:
        raise InventoryError("Self-test did not render configured become password.")

    env_with_run = dict(env)
    env_with_run["GITHUB_RUN_ID"] = "123456789"
    env_with_run["GITHUB_RUN_ATTEMPT"] = "2"
    run_text = "\n".join(inventory_lines(env_with_run, "/tmp/key", "/tmp/known_hosts"))
    for expected in (
        'greenbone_acceptance_run_id: "123456789"',
        'greenbone_acceptance_run_attempt: "2"',
    ):
        if expected not in run_text:
            raise InventoryError(f"Self-test missing rendered GitHub run content: {expected}")

    with TemporaryDirectory() as tmp:
        output = Path(tmp) / "hosts.acceptance.yml"
        render_inventory(output, env, "/tmp/key", "/tmp/known_hosts")
        if not output.read_text(encoding="utf-8").startswith("---\nall:"):
            raise InventoryError("Self-test did not write inventory YAML.")

    missing_host = dict(env)
    missing_host.pop("ROCKY9_HOST")
    expect_error(missing_host, "ROCKY9_HOST")
    same_hosts = dict(env)
    same_hosts["ROCKY10_HOST"] = same_hosts["ROCKY9_HOST"]
    expect_error(same_hosts, "must be different hosts")
    bad_port = dict(env)
    bad_port["ROCKY_SSH_PORT"] = "0"
    expect_error(bad_port, "between 1 and 65535")
    text_port = dict(env)
    text_port["ROCKY_SSH_PORT"] = "ssh"
    expect_error(text_port, "between 1 and 65535")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default=os.environ.get("ACCEPTANCE_INVENTORY", "inventories/rocky-standalone/hosts.acceptance.yml"),
        type=Path,
        help="Path for the rendered temporary acceptance inventory.",
    )
    parser.add_argument(
        "--ssh-key-file",
        default=f"{os.environ.get('HOME', '~')}/.ssh/id_ed25519",
        help="Private key path to reference from the rendered inventory.",
    )
    parser.add_argument(
        "--known-hosts-file",
        default=f"{os.environ.get('HOME', '~')}/.ssh/known_hosts",
        help="Known-hosts path to reference from the rendered inventory.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run renderer self-tests instead of writing an inventory.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.self_test:
            run_self_test()
        else:
            render_inventory(args.output, os.environ, args.ssh_key_file, args.known_hosts_file)
    except InventoryError as exc:
        print(f"Rocky acceptance inventory rendering failed: {exc}", file=sys.stderr)
        return 1

    print("Rocky acceptance inventory rendering passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
