#!/usr/bin/env python3
"""Validate shell fragments embedded in the Rocky acceptance workflow."""

from __future__ import annotations

import shutil
import subprocess
import sys
import os
from pathlib import Path


WORKFLOW = Path(".github/workflows/rocky-standalone-acceptance.yml")
CLEAN_HOST_STEP = "Verify Rocky acceptance hosts are clean"
REQUIRED_CLEAN_HOST_FRAGMENTS = (
    "Rocky acceptance hosts must be clean",
    "/opt/greenbone-community",
    "docker_name_format",
    "com.docker.compose.project=greenbone-community",
    "greenbone-community[-_]",
    "grep -E",
)
FORBIDDEN_CLEAN_HOST_FRAGMENTS = (
    "{{.Names}}",
)


class WorkflowShellError(Exception):
    """Raised when a workflow shell fragment is missing or invalid."""


def indent_width(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def extract_literal_run_block(workflow_text: str, step_name: str) -> str:
    lines = workflow_text.splitlines()
    step_index = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip() == f"- name: {step_name}"
        ),
        None,
    )
    if step_index is None:
        raise WorkflowShellError(f"Missing workflow step: {step_name}")

    run_index = next(
        (
            index
            for index in range(step_index + 1, len(lines))
            if lines[index].strip() == "run: |"
        ),
        None,
    )
    if run_index is None:
        raise WorkflowShellError(f"Missing literal run block for workflow step: {step_name}")

    run_indent = indent_width(lines[run_index])
    content_indent = run_indent + 2
    block: list[str] = []
    for line in lines[run_index + 1 :]:
        if line.strip() and indent_width(line) <= run_indent:
            break
        block.append(line[content_indent:] if line.startswith(" " * content_indent) else "")

    if not block:
        raise WorkflowShellError(f"Empty literal run block for workflow step: {step_name}")
    return "\n".join(block) + "\n"


def assert_clean_host_run_block(run_block: str) -> None:
    for fragment in REQUIRED_CLEAN_HOST_FRAGMENTS:
        if fragment not in run_block:
            raise WorkflowShellError(f"Clean-host workflow shell is missing: {fragment}")
    for fragment in FORBIDDEN_CLEAN_HOST_FRAGMENTS:
        if fragment in run_block:
            raise WorkflowShellError(
                f"Clean-host workflow shell must not contain literal {fragment}."
            )


def extract_single_quoted_raw_argument(run_block: str) -> str:
    raw_lines: list[str] = []
    inside_raw = False
    closed_raw = False
    for line in run_block.splitlines():
        if not inside_raw:
            marker = "-a '"
            start = line.find(marker)
            if start >= 0:
                raw_lines.append(line[start + len(marker) :])
                inside_raw = True
            continue

        stripped = line.rstrip()
        if stripped.endswith("' \\"):
            raw_lines.append(stripped[:-3])
            closed_raw = True
            break
        raw_lines.append(line)

    if not inside_raw:
        raise WorkflowShellError("Clean-host workflow shell is missing the Ansible raw argument.")
    if not closed_raw:
        raise WorkflowShellError("Clean-host workflow shell raw argument is not single-quoted.")

    raw_script = "\n".join(raw_lines) + "\n"
    if not raw_script.strip():
        raise WorkflowShellError("Clean-host workflow raw argument is empty.")
    return raw_script


def assert_clean_host_raw_script(raw_script: str) -> None:
    if "'" in raw_script:
        raise WorkflowShellError("Clean-host raw script must not contain single quotes.")
    for fragment in REQUIRED_CLEAN_HOST_FRAGMENTS:
        if fragment not in raw_script:
            raise WorkflowShellError(f"Clean-host raw script is missing: {fragment}")
    for fragment in FORBIDDEN_CLEAN_HOST_FRAGMENTS:
        if fragment in raw_script:
            raise WorkflowShellError(
                f"Clean-host raw script must not contain literal {fragment}."
            )


def syntax_check(shell_name: str, run_block: str) -> None:
    shell = shutil.which(shell_name)
    if not shell:
        print(f"{shell_name} not found; skipping workflow shell syntax check.")
        return
    if os.name == "nt" and Path(shell).name.lower() == "bash.exe" and "system32" in shell.lower():
        print("Windows system32 bash shim found; skipping workflow shell syntax check.")
        return

    subprocess.run([shell, "-n", "-s"], check=True, input=run_block, text=True)


def shell_syntax_checks(run_block: str) -> None:
    syntax_check("sh", run_block)
    syntax_check("bash", run_block)


def main() -> int:
    try:
        workflow_text = WORKFLOW.read_text(encoding="utf-8")
        clean_host_run_block = extract_literal_run_block(workflow_text, CLEAN_HOST_STEP)
        assert_clean_host_run_block(clean_host_run_block)
        shell_syntax_checks(clean_host_run_block)
        clean_host_raw_script = extract_single_quoted_raw_argument(clean_host_run_block)
        assert_clean_host_raw_script(clean_host_raw_script)
        shell_syntax_checks(clean_host_raw_script)
    except (OSError, subprocess.CalledProcessError, WorkflowShellError) as exc:
        print(f"Rocky acceptance workflow shell validation failed: {exc}", file=sys.stderr)
        return 1

    print("Rocky acceptance workflow shell validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
