#!/usr/bin/env python3
"""Validate live Rocky standalone acceptance evidence files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


DEFAULT_EXPECTED_HOSTS = {
    "rocky9-standalone": 9,
    "rocky10-standalone": 10,
}
SUPPORTED_ARCHITECTURES = {"x86_64", "aarch64"}
REQUIRED_RUNNING_SERVICES = {
    "gsa",
    "gsad",
    "gvmd",
    "nginx",
    "ospd-openvas",
    "pg-gvm",
    "redis-server",
}
ACCEPTED_WEB_STATUSES = {200, 301, 302}


class EvidenceError(Exception):
    """Raised when an evidence report is missing or incomplete."""


def _as_int(value: object, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"{field} must be an integer-compatible value, got {value!r}.") from exc


def _as_string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise EvidenceError(f"{field} must be a JSON array of strings.")
    return value


def _load_report(evidence_dir: Path, host: str) -> dict[str, object]:
    report_path = evidence_dir / f"{host}.json"
    if not report_path.is_file():
        raise EvidenceError(f"Missing evidence report: {report_path}")

    try:
        with report_path.open("r", encoding="utf-8") as handle:
            report = json.load(handle)
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"Invalid JSON in evidence report {report_path}: {exc}") from exc

    if not isinstance(report, dict):
        raise EvidenceError(f"Evidence report {report_path} must contain a JSON object.")
    return report


def _validate_report(report: dict[str, object], host: str, expected_major: int) -> None:
    if report.get("host") != host:
        raise EvidenceError(f"{host}: report host field is {report.get('host')!r}.")

    distribution = str(report.get("distribution", "")).lower()
    if distribution != "rocky":
        raise EvidenceError(f"{host}: distribution must be Rocky, got {report.get('distribution')!r}.")

    actual_major = _as_int(report.get("distribution_major_version"), f"{host}: distribution_major_version")
    if actual_major != expected_major:
        raise EvidenceError(f"{host}: expected Rocky {expected_major}, got Rocky {actual_major}.")

    reported_expected_major = _as_int(
        report.get("expected_distribution_major_version"),
        f"{host}: expected_distribution_major_version",
    )
    if reported_expected_major != expected_major:
        raise EvidenceError(
            f"{host}: expected_distribution_major_version is {reported_expected_major}, "
            f"expected {expected_major}."
        )

    architecture = report.get("architecture")
    if architecture not in SUPPORTED_ARCHITECTURES:
        raise EvidenceError(f"{host}: unsupported architecture in evidence: {architecture!r}.")

    compose_ps = _as_string_list(report.get("compose_ps"), f"{host}: compose_ps")
    if not compose_ps:
        raise EvidenceError(f"{host}: compose_ps evidence must not be empty.")

    running_services = set(_as_string_list(report.get("running_services"), f"{host}: running_services"))
    missing_services = sorted(REQUIRED_RUNNING_SERVICES - running_services)
    if missing_services:
        raise EvidenceError(f"{host}: missing running services: {', '.join(missing_services)}.")

    web_status = _as_int(report.get("web_probe_status"), f"{host}: web_probe_status")
    if web_status not in ACCEPTED_WEB_STATUSES:
        raise EvidenceError(f"{host}: unexpected web probe status {web_status}.")

    for field in ("docker_version", "docker_compose_version", "compose_file"):
        if not report.get(field):
            raise EvidenceError(f"{host}: missing evidence field {field}.")

    if report.get("admin_password_file_checked") is True:
        if report.get("admin_password_file_exists") is not True:
            raise EvidenceError(f"{host}: generated admin password file was not found.")
        admin_password_file_size = _as_int(
            report.get("admin_password_file_size"),
            f"{host}: admin_password_file_size",
        )
        if admin_password_file_size <= 0:
            raise EvidenceError(f"{host}: generated admin password file is empty.")
        if report.get("admin_password_file_mode") != "0600":
            raise EvidenceError(
                f"{host}: generated admin password file mode must be 0600, "
                f"got {report.get('admin_password_file_mode')!r}."
            )


def validate_evidence(evidence_dir: Path, expected_hosts: dict[str, int]) -> None:
    if not evidence_dir.is_dir():
        raise EvidenceError(f"Missing evidence directory: {evidence_dir}")

    expected_reports = {f"{host}.json" for host in expected_hosts}
    actual_reports = {path.name for path in evidence_dir.glob("*.json")}
    unexpected_reports = sorted(actual_reports - expected_reports)
    if unexpected_reports:
        raise EvidenceError(f"Unexpected evidence report files: {', '.join(unexpected_reports)}.")

    for host, expected_major in expected_hosts.items():
        report = _load_report(evidence_dir, host)
        _validate_report(report, host, expected_major)


def _write_sample_report(path: Path, host: str, major: int) -> None:
    report = {
        "host": host,
        "distribution": "Rocky",
        "distribution_version": f"{major}.0",
        "distribution_major_version": str(major),
        "architecture": "x86_64",
        "expected_distribution_major_version": major,
        "docker_version": "Docker version 28.0.0",
        "docker_compose_version": "Docker Compose version v2.35.0",
        "admin_password_file_checked": True,
        "admin_password_file": ".secrets/greenbone_admin_password",
        "admin_password_file_exists": True,
        "admin_password_file_size": 32,
        "admin_password_file_mode": "0600",
        "compose_file": "/opt/greenbone-community/compose.yaml",
        "compose_ps": sorted(REQUIRED_RUNNING_SERVICES),
        "running_services": sorted(REQUIRED_RUNNING_SERVICES),
        "web_probe_status": 200,
    }
    path.write_text(json.dumps(report), encoding="utf-8")


def run_self_test() -> None:
    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)
        validate_evidence(evidence_dir, DEFAULT_EXPECTED_HOSTS)

        extra_report = evidence_dir / "stale-rocky.json"
        _write_sample_report(extra_report, "stale-rocky", 9)
        try:
            validate_evidence(evidence_dir, DEFAULT_EXPECTED_HOSTS)
        except EvidenceError as exc:
            if "Unexpected evidence report files" not in str(exc):
                raise
        else:
            raise EvidenceError("Self-test did not reject unexpected evidence report files.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence-dir",
        default=".secrets/rocky-standalone-evidence",
        type=Path,
        help="Directory containing per-host Rocky acceptance JSON reports.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run the verifier against generated sample evidence.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.self_test:
            run_self_test()
        else:
            validate_evidence(args.evidence_dir, DEFAULT_EXPECTED_HOSTS)
    except EvidenceError as exc:
        print(f"Rocky acceptance evidence validation failed: {exc}", file=sys.stderr)
        return 1

    print("Rocky acceptance evidence validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
