#!/usr/bin/env python3
"""Validate GitHub readiness for Rocky standalone acceptance dispatch."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory


WORKFLOW_PATH = Path(".github/workflows/rocky-standalone-acceptance.yml")
WORKFLOW_PATH_TEXT = WORKFLOW_PATH.as_posix()
REQUIRED_SECRETS = {
    "ROCKY9_HOST",
    "ROCKY10_HOST",
    "ROCKY_SSH_USER",
    "ROCKY_SSH_PRIVATE_KEY",
}
OPTIONAL_SECRETS = {
    "ROCKY_BECOME_PASSWORD",
    "ROCKY_SSH_KNOWN_HOSTS",
}
OPTIONAL_VARIABLES = {
    "ROCKY_SSH_PORT",
}


class ReadinessError(Exception):
    """Raised when GitHub acceptance prerequisites are missing."""


CommandRunner = Callable[[list[str]], str]


def run_command(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip()
        raise ReadinessError(f"{' '.join(command)} failed: {details}")
    return completed.stdout


def require_gh() -> None:
    if not shutil.which("gh"):
        raise ReadinessError(
            "GitHub CLI `gh` is required to check repository secrets and workflow state."
        )


def read_json(command: list[str], runner: CommandRunner) -> object:
    try:
        return json.loads(runner(command))
    except json.JSONDecodeError as exc:
        raise ReadinessError(f"{' '.join(command)} did not return valid JSON.") from exc


def validate_local_workflow(workflow_path: Path = WORKFLOW_PATH) -> None:
    if not workflow_path.is_file():
        raise ReadinessError(f"Missing acceptance workflow: {workflow_path}")
    workflow = workflow_path.read_text(encoding="utf-8")
    for required in ("workflow_dispatch:", "runner_label:", "ROCKY9_HOST", "ROCKY10_HOST"):
        if required not in workflow:
            raise ReadinessError(f"Acceptance workflow is missing required content: {required}")


def validate_auth(runner: CommandRunner) -> None:
    runner(["gh", "auth", "status"])


def validate_workflow_enabled(runner: CommandRunner) -> None:
    workflows = read_json(
        ["gh", "workflow", "list", "--all", "--json", "name,path,state"],
        runner,
    )
    if not isinstance(workflows, list):
        raise ReadinessError("gh workflow list did not return a JSON array.")

    workflow = next(
        (
            item
            for item in workflows
            if isinstance(item, dict) and item.get("path") == WORKFLOW_PATH_TEXT
        ),
        None,
    )
    if workflow is None:
        raise ReadinessError(f"Remote repository is missing workflow {WORKFLOW_PATH_TEXT}.")
    if workflow.get("state") != "active":
        raise ReadinessError(
            f"Remote workflow {WORKFLOW_PATH_TEXT} is not active; state={workflow.get('state')!r}."
        )


def validate_secrets(runner: CommandRunner) -> None:
    secrets = read_json(["gh", "secret", "list", "--json", "name"], runner)
    if not isinstance(secrets, list):
        raise ReadinessError("gh secret list did not return a JSON array.")
    secret_names = {
        item.get("name")
        for item in secrets
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    missing = sorted(REQUIRED_SECRETS - secret_names)
    if missing:
        raise ReadinessError(f"Missing required repository secrets: {', '.join(missing)}.")

    present_optional = sorted(OPTIONAL_SECRETS & secret_names)
    if present_optional:
        print(f"Optional Rocky acceptance secrets present: {', '.join(present_optional)}.")


def validate_variables(runner: CommandRunner) -> None:
    variables = read_json(["gh", "variable", "list", "--json", "name,value"], runner)
    if not isinstance(variables, list):
        raise ReadinessError("gh variable list did not return a JSON array.")
    variable_map = {
        item.get("name"): item.get("value", "")
        for item in variables
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    unknown_variables = sorted(set(variable_map) & OPTIONAL_VARIABLES)
    if "ROCKY_SSH_PORT" not in variable_map:
        print("ROCKY_SSH_PORT repository variable is absent; workflow will use default port 22.")
        return

    try:
        ssh_port = int(str(variable_map["ROCKY_SSH_PORT"]))
    except ValueError as exc:
        raise ReadinessError("ROCKY_SSH_PORT repository variable must be an integer.") from exc
    if ssh_port < 1 or ssh_port > 65535:
        raise ReadinessError("ROCKY_SSH_PORT repository variable must be between 1 and 65535.")
    if unknown_variables:
        print("Optional Rocky acceptance variables present: " + ", ".join(unknown_variables) + ".")


def validate_readiness(runner: CommandRunner = run_command) -> None:
    validate_local_workflow()
    require_gh()
    validate_auth(runner)
    validate_workflow_enabled(runner)
    validate_secrets(runner)
    validate_variables(runner)


def self_test_runner(command_map: dict[tuple[str, ...], str]) -> CommandRunner:
    def run(command: list[str]) -> str:
        key = tuple(command)
        if key not in command_map:
            raise ReadinessError(f"Unexpected self-test command: {' '.join(command)}")
        return command_map[key]

    return run


def run_self_test() -> None:
    workflow_text = """---
name: rocky-standalone-acceptance
'on':
  workflow_dispatch:
    inputs:
      runner_label:
        description: GitHub Actions runner label that can SSH to both Rocky hosts.
env:
  ROCKY9_HOST: ${{ secrets.ROCKY9_HOST }}
  ROCKY10_HOST: ${{ secrets.ROCKY10_HOST }}
"""
    with TemporaryDirectory() as tmp:
        original_cwd = Path.cwd()
        tmp_path = Path(tmp)
        try:
            workflow_path = tmp_path / WORKFLOW_PATH
            workflow_path.parent.mkdir(parents=True)
            workflow_path.write_text(workflow_text, encoding="utf-8")
            os.chdir(tmp_path)
            validate_local_workflow()
        finally:
            os.chdir(original_cwd)

    command_map = {
        ("gh", "auth", "status"): "",
        ("gh", "workflow", "list", "--all", "--json", "name,path,state"): json.dumps(
            [{"name": "rocky-standalone-acceptance", "path": WORKFLOW_PATH_TEXT, "state": "active"}]
        ),
        ("gh", "secret", "list", "--json", "name"): json.dumps(
            [{"name": name} for name in sorted(REQUIRED_SECRETS | {"ROCKY_SSH_KNOWN_HOSTS"})]
        ),
        ("gh", "variable", "list", "--json", "name,value"): json.dumps(
            [{"name": "ROCKY_SSH_PORT", "value": "2222"}]
        ),
    }
    runner = self_test_runner(command_map)
    validate_auth(runner)
    validate_workflow_enabled(runner)
    validate_secrets(runner)
    validate_variables(runner)

    missing_secret_map = dict(command_map)
    missing_secret_map[("gh", "secret", "list", "--json", "name")] = json.dumps(
        [{"name": name} for name in sorted(REQUIRED_SECRETS - {"ROCKY10_HOST"})]
    )
    try:
        validate_secrets(self_test_runner(missing_secret_map))
    except ReadinessError as exc:
        if "ROCKY10_HOST" not in str(exc):
            raise
    else:
        raise ReadinessError("Self-test did not reject missing ROCKY10_HOST secret.")

    disabled_workflow_map = dict(command_map)
    disabled_workflow_map[
        ("gh", "workflow", "list", "--all", "--json", "name,path,state")
    ] = json.dumps(
        [{"name": "rocky-standalone-acceptance", "path": WORKFLOW_PATH_TEXT, "state": "disabled_manually"}]
    )
    try:
        validate_workflow_enabled(self_test_runner(disabled_workflow_map))
    except ReadinessError as exc:
        if "not active" not in str(exc):
            raise
    else:
        raise ReadinessError("Self-test did not reject disabled workflow.")

    invalid_variable_map = dict(command_map)
    invalid_variable_map[("gh", "variable", "list", "--json", "name,value")] = json.dumps(
        [{"name": "ROCKY_SSH_PORT", "value": "70000"}]
    )
    try:
        validate_variables(self_test_runner(invalid_variable_map))
    except ReadinessError as exc:
        if "between 1 and 65535" not in str(exc):
            raise
    else:
        raise ReadinessError("Self-test did not reject invalid ROCKY_SSH_PORT.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run the readiness checker against mocked GitHub CLI responses.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.self_test:
            run_self_test()
        else:
            validate_readiness()
    except ReadinessError as exc:
        print(f"Rocky acceptance readiness validation failed: {exc}", file=sys.stderr)
        return 1

    print("Rocky acceptance readiness validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
