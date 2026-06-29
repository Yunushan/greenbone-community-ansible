#!/usr/bin/env python3
"""Validate live Rocky standalone acceptance evidence files."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


DEFAULT_EXPECTED_HOSTS = {
    "rocky9-standalone": 9,
    "rocky10-standalone": 10,
}
SUPPORTED_ARCHITECTURES = {"x86_64", "aarch64"}
SUPPORTED_PACKAGE_MANAGERS = {"dnf", "dnf5"}
SUPPORTED_ROCKY_DISTRIBUTION_NAMES = {"rocky", "rockylinux"}
REQUIRED_RUNNING_SERVICES = {
    "gsa",
    "gsad",
    "gvmd",
    "nginx",
    "openvas",
    "openvasd",
    "ospd-openvas",
    "pg-gvm",
    "redis-server",
}
REQUIRED_DOCKER_RPM_PACKAGES = {
    "docker-ce",
    "docker-ce-cli",
    "containerd.io",
    "docker-buildx-plugin",
    "docker-compose-plugin",
}
EXPECTED_DOCKER_RPM_GPG_FINGERPRINT = "060A 61C5 1B55 8A7F 742B 77AA C52F EB6B 621E 9F35"
EXPECTED_DOCKER_RPM_GPG_KEY_ID = "621e9f35"
MINIMUM_ANSIBLE_CORE_VERSION_FOR_ROCKY10 = (2, 19, 0)
MINIMUM_ANSIBLE_CORE_VERSION_FOR_ROCKY10_TEXT = "2.19.0"
MINIMUM_CPU_CORES = 4
MINIMUM_MEMORY_MB = 8192
MINIMUM_DISK_MB = 61440
MINIMUM_SERVICE_WAIT_SECONDS = 900
DEFAULT_MAX_ACCEPTANCE_EVIDENCE_AGE_HOURS = 24
ACCEPTED_WEB_STATUSES = {200, 301, 302}
EXPECTED_DOCKER_RPM_REPO_FILE = "/etc/yum.repos.d/docker-ce.repo"
EXPECTED_WEB_BIND_ADDRESS = "127.0.0.1"
EXPECTED_WEB_HTTPS_PORT = 443
EXPECTED_WEB_GSAD_PORT = 9392
ROCKY10_X86_64_V3_REQUIRED_CPU_FLAG_GROUPS = (
    ("cx16",),
    ("lahf_lm",),
    ("popcnt",),
    ("pni", "sse3"),
    ("ssse3",),
    ("sse4_1",),
    ("sse4_2",),
    ("avx",),
    ("avx2",),
    ("bmi1",),
    ("bmi2",),
    ("f16c",),
    ("fma",),
    ("abm", "lzcnt"),
    ("movbe",),
    ("xsave",),
)


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


def _cpu_flag_group_label(group: tuple[str, ...]) -> str:
    return "/".join(group)


def _version_tuple(value: object, field: str) -> tuple[int, int, int]:
    value_text = str(value or "")
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", value_text)
    if not match:
        raise EvidenceError(f"{field} must look like a semantic version, got {value!r}.")
    return tuple(int(part) for part in match.groups())


def _parse_timestamp(value: object, field: str) -> datetime:
    value_text = str(value or "")
    if not value_text:
        raise EvidenceError(f"{field}: missing evidence field validated_at.")
    if value_text.endswith("Z"):
        value_text = f"{value_text[:-1]}+00:00"
    try:
        timestamp = datetime.fromisoformat(value_text)
    except ValueError as exc:
        raise EvidenceError(f"{field}: validated_at must be an ISO 8601 timestamp.") from exc
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def _utc_timestamp(hours_ago: int = 0) -> str:
    timestamp = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return timestamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _validate_report(
    report: dict[str, object],
    host: str,
    expected_major: int,
    max_age_hours: float | None = None,
    expected_run_id: str | None = None,
    expected_run_attempt: str | None = None,
) -> None:
    if report.get("host") != host:
        raise EvidenceError(f"{host}: report host field is {report.get('host')!r}.")

    validated_at = _parse_timestamp(report.get("validated_at"), host)
    if max_age_hours is not None:
        now = datetime.now(timezone.utc)
        future_tolerance = timedelta(minutes=5)
        if validated_at - now > future_tolerance:
            raise EvidenceError(f"{host}: validated_at is more than 5 minutes in the future.")
        max_age = timedelta(hours=max_age_hours)
        if now - validated_at > max_age:
            raise EvidenceError(
                f"{host}: acceptance evidence is older than {max_age_hours:g} hours."
            )
    if expected_run_id is not None and str(report.get("acceptance_run_id", "")) != expected_run_id:
        raise EvidenceError(f"{host}: acceptance_run_id does not match this workflow run.")
    if (
        expected_run_attempt is not None
        and str(report.get("acceptance_run_attempt", "")) != expected_run_attempt
    ):
        raise EvidenceError(f"{host}: acceptance_run_attempt does not match this workflow attempt.")

    distribution = re.sub(r"[^a-z0-9]", "", str(report.get("distribution", "")).lower())
    if distribution not in SUPPORTED_ROCKY_DISTRIBUTION_NAMES:
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
    if actual_major == 10 and architecture == "x86_64":
        if report.get("rocky10_x86_64_v3_cpu_flags_checked") is not True:
            raise EvidenceError(f"{host}: Rocky 10 x86_64 CPU flag check must be recorded.")
        cpu_flags = {
            flag.lower()
            for flag in _as_string_list(report.get("cpu_flags"), f"{host}: cpu_flags")
        }
        missing_cpu_flag_groups = [
            _cpu_flag_group_label(group)
            for group in ROCKY10_X86_64_V3_REQUIRED_CPU_FLAG_GROUPS
            if cpu_flags.isdisjoint(group)
        ]
        if missing_cpu_flag_groups:
            raise EvidenceError(
                f"{host}: missing Rocky 10 x86-64-v3 CPU feature groups: "
                f"{', '.join(missing_cpu_flag_groups)}."
            )
        reported_missing_cpu_flags = _as_string_list(
            report.get("rocky10_x86_64_v3_missing_cpu_flags"),
            f"{host}: rocky10_x86_64_v3_missing_cpu_flags",
        )
        if reported_missing_cpu_flags:
            raise EvidenceError(
                f"{host}: Rocky 10 x86-64-v3 CPU feature check reported missing groups: "
                f"{', '.join(reported_missing_cpu_flags)}."
            )
    if report.get("os_family") != "RedHat":
        raise EvidenceError(f"{host}: os_family must be RedHat, got {report.get('os_family')!r}.")
    if not report.get("kernel"):
        raise EvidenceError(f"{host}: missing evidence field kernel.")
    package_manager = report.get("package_manager")
    if package_manager not in SUPPORTED_PACKAGE_MANAGERS:
        raise EvidenceError(
            f"{host}: package_manager must be one of "
            f"{', '.join(sorted(SUPPORTED_PACKAGE_MANAGERS))}, got {package_manager!r}."
        )
    if package_manager == "dnf5":
        if report.get("dnf5_backend_checked") is not True:
            raise EvidenceError(f"{host}: DNF5 backend runtime check must be recorded.")
        if report.get("python3_libdnf5_installed") is not True:
            raise EvidenceError(f"{host}: python3-libdnf5 must be installed for DNF5 targets.")

    ansible_core_version = _version_tuple(report.get("ansible_core_version"), f"{host}: ansible_core_version")
    if actual_major == 10 and ansible_core_version < MINIMUM_ANSIBLE_CORE_VERSION_FOR_ROCKY10:
        minimum = ".".join(str(part) for part in MINIMUM_ANSIBLE_CORE_VERSION_FOR_ROCKY10)
        raise EvidenceError(
            f"{host}: ansible_core_version must be at least {minimum} for Rocky Linux 10."
        )
    if report.get("minimum_ansible_core_version_for_rocky10") != MINIMUM_ANSIBLE_CORE_VERSION_FOR_ROCKY10_TEXT:
        raise EvidenceError(
            f"{host}: minimum_ansible_core_version_for_rocky10 must be "
            f"{MINIMUM_ANSIBLE_CORE_VERSION_FOR_ROCKY10_TEXT}."
        )

    if report.get("install_mode") != "docker":
        raise EvidenceError(f"{host}: install_mode must be docker, got {report.get('install_mode')!r}.")
    if report.get("official_docker_repo_enabled") is not True:
        raise EvidenceError(f"{host}: official_docker_repo_enabled must be true.")

    minimum_cpu_cores = _as_int(report.get("minimum_cpu_cores"), f"{host}: minimum_cpu_cores")
    if minimum_cpu_cores < MINIMUM_CPU_CORES:
        raise EvidenceError(f"{host}: minimum_cpu_cores must be at least {MINIMUM_CPU_CORES}.")
    cpu_cores = _as_int(report.get("cpu_cores"), f"{host}: cpu_cores")
    if cpu_cores < minimum_cpu_cores:
        raise EvidenceError(f"{host}: CPU cores {cpu_cores} below required {minimum_cpu_cores}.")

    minimum_memory_mb = _as_int(report.get("minimum_memory_mb"), f"{host}: minimum_memory_mb")
    if minimum_memory_mb < MINIMUM_MEMORY_MB:
        raise EvidenceError(f"{host}: minimum_memory_mb must be at least {MINIMUM_MEMORY_MB}.")
    memory_mb = _as_int(report.get("memory_mb"), f"{host}: memory_mb")
    if memory_mb < minimum_memory_mb:
        raise EvidenceError(f"{host}: memory {memory_mb} MB below required {minimum_memory_mb} MB.")

    minimum_disk_mb = _as_int(report.get("minimum_disk_mb"), f"{host}: minimum_disk_mb")
    if minimum_disk_mb < MINIMUM_DISK_MB:
        raise EvidenceError(f"{host}: minimum_disk_mb must be at least {MINIMUM_DISK_MB}.")
    disk_mb_available = _as_int(report.get("disk_mb_available"), f"{host}: disk_mb_available")
    if disk_mb_available < minimum_disk_mb:
        raise EvidenceError(
            f"{host}: free disk {disk_mb_available} MB below required {minimum_disk_mb} MB."
        )
    if not report.get("disk_check_path"):
        raise EvidenceError(f"{host}: missing evidence field disk_check_path.")

    if report.get("docker_rpm_repo_file") != EXPECTED_DOCKER_RPM_REPO_FILE:
        raise EvidenceError(
            f"{host}: Docker RPM repository file must be {EXPECTED_DOCKER_RPM_REPO_FILE}, "
            f"got {report.get('docker_rpm_repo_file')!r}."
        )
    if report.get("docker_rpm_repo_file_exists") is not True:
        raise EvidenceError(f"{host}: Docker RPM repository file was not found.")
    if report.get("docker_rpm_repo_uses_docker_centos_repo") is not True:
        raise EvidenceError(f"{host}: Docker RPM repository must use Docker's CentOS repo.")
    if report.get("docker_rpm_repo_gpgcheck_enabled") is not True:
        raise EvidenceError(f"{host}: Docker RPM repository must have gpgcheck=1.")
    if report.get("docker_rpm_repo_gpgkey_url_present") is not True:
        raise EvidenceError(f"{host}: Docker RPM repository must use Docker's CentOS RPM GPG key.")
    if report.get("docker_rpm_gpg_key_fingerprint") != EXPECTED_DOCKER_RPM_GPG_FINGERPRINT:
        raise EvidenceError(
            f"{host}: Docker RPM GPG key fingerprint must be {EXPECTED_DOCKER_RPM_GPG_FINGERPRINT}."
        )
    if str(report.get("docker_rpm_gpg_key_id", "")).lower() != EXPECTED_DOCKER_RPM_GPG_KEY_ID:
        raise EvidenceError(f"{host}: Docker RPM GPG key ID must be {EXPECTED_DOCKER_RPM_GPG_KEY_ID}.")
    if report.get("docker_rpm_gpg_key_imported") is not True:
        raise EvidenceError(f"{host}: Docker RPM GPG key must be imported in the RPM database.")

    docker_rpm_packages = _as_string_list(report.get("docker_rpm_packages"), f"{host}: docker_rpm_packages")
    missing_rpm_packages = sorted(REQUIRED_DOCKER_RPM_PACKAGES - set(docker_rpm_packages))
    if missing_rpm_packages:
        raise EvidenceError(f"{host}: missing Docker RPM packages: {', '.join(missing_rpm_packages)}.")

    compose_ps = _as_string_list(report.get("compose_ps"), f"{host}: compose_ps")
    if not compose_ps:
        raise EvidenceError(f"{host}: compose_ps evidence must not be empty.")
    if report.get("compose_ps_collected_after_service_wait") is not True:
        raise EvidenceError(f"{host}: compose_ps must be collected after the service wait gate.")
    service_wait_retries = _as_int(report.get("service_wait_retries"), f"{host}: service_wait_retries")
    service_wait_delay_seconds = _as_int(
        report.get("service_wait_delay_seconds"),
        f"{host}: service_wait_delay_seconds",
    )
    service_wait_timeout_seconds = _as_int(
        report.get("service_wait_timeout_seconds"),
        f"{host}: service_wait_timeout_seconds",
    )
    if service_wait_timeout_seconds != service_wait_retries * service_wait_delay_seconds:
        raise EvidenceError(f"{host}: service_wait_timeout_seconds does not match retries times delay.")
    if service_wait_timeout_seconds < MINIMUM_SERVICE_WAIT_SECONDS:
        raise EvidenceError(
            f"{host}: service wait timeout must be at least {MINIMUM_SERVICE_WAIT_SECONDS} seconds."
        )

    running_services = set(_as_string_list(report.get("running_services"), f"{host}: running_services"))
    missing_services = sorted(REQUIRED_RUNNING_SERVICES - running_services)
    if missing_services:
        raise EvidenceError(f"{host}: missing running services: {', '.join(missing_services)}.")

    web_status = _as_int(report.get("web_probe_status"), f"{host}: web_probe_status")
    if web_status not in ACCEPTED_WEB_STATUSES:
        raise EvidenceError(f"{host}: unexpected web probe status {web_status}.")
    gsad_web_status = _as_int(
        report.get("web_gsad_probe_status"),
        f"{host}: web_gsad_probe_status",
    )
    if gsad_web_status not in ACCEPTED_WEB_STATUSES:
        raise EvidenceError(f"{host}: unexpected GSAD web probe status {gsad_web_status}.")
    if report.get("web_bind_address") != EXPECTED_WEB_BIND_ADDRESS:
        raise EvidenceError(
            f"{host}: web_bind_address must be {EXPECTED_WEB_BIND_ADDRESS}, "
            f"got {report.get('web_bind_address')!r}."
        )
    web_https_port = _as_int(report.get("web_https_port"), f"{host}: web_https_port")
    if web_https_port != EXPECTED_WEB_HTTPS_PORT:
        raise EvidenceError(
            f"{host}: web_https_port must be {EXPECTED_WEB_HTTPS_PORT}, got {web_https_port}."
        )
    web_gsad_port = _as_int(report.get("web_gsad_port"), f"{host}: web_gsad_port")
    if web_gsad_port != EXPECTED_WEB_GSAD_PORT:
        raise EvidenceError(
            f"{host}: web_gsad_port must be {EXPECTED_WEB_GSAD_PORT}, got {web_gsad_port}."
        )
    if report.get("web_https_mapping_present") is not True:
        raise EvidenceError(f"{host}: compose file must contain the expected HTTPS web mapping.")
    if report.get("web_gsad_mapping_present") is not True:
        raise EvidenceError(f"{host}: compose file must contain the expected GSAD web mapping.")

    for field in ("docker_version", "docker_compose_version", "compose_file"):
        if not report.get(field):
            raise EvidenceError(f"{host}: missing evidence field {field}.")
    docker_version = str(report.get("docker_version"))
    if not docker_version.startswith("Docker version "):
        raise EvidenceError(f"{host}: docker_version does not look like Docker Engine output.")
    docker_compose_version = str(report.get("docker_compose_version"))
    if "Docker Compose version" not in docker_compose_version:
        raise EvidenceError(f"{host}: docker_compose_version does not look like Docker Compose output.")
    compose_file = str(report.get("compose_file"))
    if not compose_file.endswith("/compose.yaml"):
        raise EvidenceError(f"{host}: compose_file must point to a compose.yaml file.")

    if report.get("admin_password_file_checked") is not True:
        raise EvidenceError(f"{host}: generated admin password file must be checked in acceptance evidence.")
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


def validate_evidence(
    evidence_dir: Path,
    expected_hosts: dict[str, int],
    max_age_hours: float | None = None,
    expected_run_id: str | None = None,
    expected_run_attempt: str | None = None,
) -> None:
    if not evidence_dir.is_dir():
        raise EvidenceError(f"Missing evidence directory: {evidence_dir}")

    expected_reports = {f"{host}.json" for host in expected_hosts}
    actual_reports = {path.name for path in evidence_dir.glob("*.json")}
    unexpected_reports = sorted(actual_reports - expected_reports)
    if unexpected_reports:
        raise EvidenceError(f"Unexpected evidence report files: {', '.join(unexpected_reports)}.")

    for host, expected_major in expected_hosts.items():
        report = _load_report(evidence_dir, host)
        _validate_report(
            report,
            host,
            expected_major,
            max_age_hours=max_age_hours,
            expected_run_id=expected_run_id,
            expected_run_attempt=expected_run_attempt,
        )


def evidence_summary(evidence_dir: Path, expected_hosts: dict[str, int]) -> dict[str, object]:
    reports: list[dict[str, object]] = []
    for host in expected_hosts:
        report = _load_report(evidence_dir, host)
        reports.append(
            {
                "host": host,
                "distribution": report.get("distribution"),
                "distribution_major_version": report.get("distribution_major_version"),
                "architecture": report.get("architecture"),
                "validated_at": report.get("validated_at"),
                "acceptance_run_id": report.get("acceptance_run_id"),
                "acceptance_run_attempt": report.get("acceptance_run_attempt"),
                "ansible_core_version": report.get("ansible_core_version"),
                "package_manager": report.get("package_manager"),
                "dnf5_backend_checked": report.get("dnf5_backend_checked"),
                "python3_libdnf5_installed": report.get("python3_libdnf5_installed"),
                "rocky10_x86_64_v3_cpu_flags_checked": report.get(
                    "rocky10_x86_64_v3_cpu_flags_checked"
                ),
                "rocky10_x86_64_v3_missing_cpu_flags": report.get(
                    "rocky10_x86_64_v3_missing_cpu_flags"
                ),
                "cpu_cores": report.get("cpu_cores"),
                "memory_mb": report.get("memory_mb"),
                "disk_mb_available": report.get("disk_mb_available"),
                "docker_version": report.get("docker_version"),
                "docker_compose_version": report.get("docker_compose_version"),
                "docker_rpm_repo_file": report.get("docker_rpm_repo_file"),
                "docker_rpm_gpg_key_imported": report.get("docker_rpm_gpg_key_imported"),
                "service_wait_timeout_seconds": report.get("service_wait_timeout_seconds"),
                "running_services": report.get("running_services"),
                "web_bind_address": report.get("web_bind_address"),
                "web_https_port": report.get("web_https_port"),
                "web_gsad_port": report.get("web_gsad_port"),
            }
        )
    return {"status": "valid", "reports": reports}


def _write_sample_report(path: Path, host: str, major: int) -> None:
    report = {
        "host": host,
        "validated_at": _utc_timestamp(),
        "acceptance_run_id": "123456789",
        "acceptance_run_attempt": "1",
        "distribution": "Rocky",
        "distribution_version": f"{major}.0",
        "distribution_major_version": str(major),
        "architecture": "x86_64",
        "os_family": "RedHat",
        "kernel": "6.12.0-55.el10.x86_64",
        "package_manager": "dnf",
        "dnf5_backend_checked": False,
        "python3_libdnf5_installed": False,
        "ansible_core_version": "2.21.1",
        "minimum_ansible_core_version_for_rocky10": "2.19.0",
        "cpu_flags": sorted({flag for group in ROCKY10_X86_64_V3_REQUIRED_CPU_FLAG_GROUPS for flag in group}),
        "rocky10_x86_64_v3_cpu_flags_checked": major == 10,
        "rocky10_x86_64_v3_required_cpu_flag_groups": [
            list(group) for group in ROCKY10_X86_64_V3_REQUIRED_CPU_FLAG_GROUPS
        ],
        "rocky10_x86_64_v3_missing_cpu_flags": [],
        "expected_distribution_major_version": major,
        "install_mode": "docker",
        "official_docker_repo_enabled": True,
        "cpu_cores": MINIMUM_CPU_CORES,
        "minimum_cpu_cores": MINIMUM_CPU_CORES,
        "memory_mb": MINIMUM_MEMORY_MB,
        "minimum_memory_mb": MINIMUM_MEMORY_MB,
        "disk_check_path": "/opt",
        "disk_mb_available": MINIMUM_DISK_MB,
        "minimum_disk_mb": MINIMUM_DISK_MB,
        "docker_rpm_repo_file": "/etc/yum.repos.d/docker-ce.repo",
        "docker_rpm_repo_file_exists": True,
        "docker_rpm_repo_uses_docker_centos_repo": True,
        "docker_rpm_repo_gpgcheck_enabled": True,
        "docker_rpm_repo_gpgkey_url_present": True,
        "docker_rpm_gpg_key_fingerprint": EXPECTED_DOCKER_RPM_GPG_FINGERPRINT,
        "docker_rpm_gpg_key_id": EXPECTED_DOCKER_RPM_GPG_KEY_ID,
        "docker_rpm_gpg_key_imported": True,
        "docker_rpm_packages": [
            "containerd.io",
            "docker-buildx-plugin",
            "docker-ce",
            "docker-ce-cli",
            "docker-compose-plugin",
        ],
        "docker_version": "Docker version 28.0.0",
        "docker_compose_version": "Docker Compose version v2.35.0",
        "admin_password_file_checked": True,
        "admin_password_file": ".secrets/greenbone_admin_password",
        "admin_password_file_exists": True,
        "admin_password_file_size": 32,
        "admin_password_file_mode": "0600",
        "compose_file": "/opt/greenbone-community/compose.yaml",
        "compose_ps_collected_after_service_wait": True,
        "service_wait_retries": 60,
        "service_wait_delay_seconds": 15,
        "service_wait_timeout_seconds": MINIMUM_SERVICE_WAIT_SECONDS,
        "compose_ps": sorted(REQUIRED_RUNNING_SERVICES),
        "running_services": sorted(REQUIRED_RUNNING_SERVICES),
        "web_bind_address": EXPECTED_WEB_BIND_ADDRESS,
        "web_https_port": EXPECTED_WEB_HTTPS_PORT,
        "web_gsad_port": EXPECTED_WEB_GSAD_PORT,
        "web_https_mapping_present": True,
        "web_gsad_mapping_present": True,
        "web_probe_status": 200,
        "web_gsad_probe_status": 200,
    }
    path.write_text(json.dumps(report), encoding="utf-8")


def _expect_evidence_error(
    evidence_dir: Path,
    expected_message: str,
    max_age_hours: float | None = None,
    expected_run_id: str | None = None,
    expected_run_attempt: str | None = None,
) -> None:
    try:
        validate_evidence(
            evidence_dir,
            DEFAULT_EXPECTED_HOSTS,
            max_age_hours=max_age_hours,
            expected_run_id=expected_run_id,
            expected_run_attempt=expected_run_attempt,
        )
    except EvidenceError as exc:
        if expected_message not in str(exc):
            raise
    else:
        raise EvidenceError(f"Self-test did not reject evidence with {expected_message}.")


def run_self_test() -> None:
    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)
        validate_evidence(evidence_dir, DEFAULT_EXPECTED_HOSTS)
        validate_evidence(
            evidence_dir,
            DEFAULT_EXPECTED_HOSTS,
            max_age_hours=DEFAULT_MAX_ACCEPTANCE_EVIDENCE_AGE_HOURS,
            expected_run_id="123456789",
            expected_run_attempt="1",
        )
        summary = evidence_summary(evidence_dir, DEFAULT_EXPECTED_HOSTS)
        if summary.get("status") != "valid":
            raise EvidenceError("Self-test evidence summary did not report valid status.")
        summary_reports = summary.get("reports")
        if not isinstance(summary_reports, list) or len(summary_reports) != len(DEFAULT_EXPECTED_HOSTS):
            raise EvidenceError("Self-test evidence summary did not include every expected host.")
        rocky10_summary = next(
            (
                item
                for item in summary_reports
                if isinstance(item, dict) and item.get("host") == "rocky10-standalone"
            ),
            None,
        )
        if rocky10_summary is None:
            raise EvidenceError("Self-test evidence summary did not include Rocky 10.")
        if rocky10_summary.get("rocky10_x86_64_v3_cpu_flags_checked") is not True:
            raise EvidenceError("Self-test evidence summary did not include Rocky 10 CPU flag proof.")

        extra_report = evidence_dir / "stale-rocky.json"
        _write_sample_report(extra_report, "stale-rocky", 9)
        _expect_evidence_error(evidence_dir, "Unexpected evidence report files")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        _expect_evidence_error(
            evidence_dir,
            "acceptance_run_id does not match this workflow run",
            expected_run_id="987654321",
        )

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        _expect_evidence_error(
            evidence_dir,
            "acceptance_run_attempt does not match this workflow attempt",
            expected_run_attempt="2",
        )

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["validated_at"] = "not-a-timestamp"
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "validated_at must be an ISO 8601 timestamp")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["validated_at"] = _utc_timestamp(
            hours_ago=DEFAULT_MAX_ACCEPTANCE_EVIDENCE_AGE_HOURS + 1
        )
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(
            evidence_dir,
            "acceptance evidence is older than",
            max_age_hours=DEFAULT_MAX_ACCEPTANCE_EVIDENCE_AGE_HOURS,
        )

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        future_timestamp = datetime.now(timezone.utc) + timedelta(minutes=10)
        broken_report["validated_at"] = future_timestamp.replace(microsecond=0).isoformat()
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(
            evidence_dir,
            "validated_at is more than 5 minutes in the future",
            max_age_hours=DEFAULT_MAX_ACCEPTANCE_EVIDENCE_AGE_HOURS,
        )

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        rocky10_report_path = evidence_dir / "rocky10-standalone.json"
        rocky10_report = json.loads(rocky10_report_path.read_text(encoding="utf-8"))
        rocky10_report["distribution"] = "Rocky Linux"
        rocky10_report_path.write_text(json.dumps(rocky10_report), encoding="utf-8")
        validate_evidence(evidence_dir, DEFAULT_EXPECTED_HOSTS)

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        rocky10_report_path = evidence_dir / "rocky10-standalone.json"
        rocky10_report = json.loads(rocky10_report_path.read_text(encoding="utf-8"))
        rocky10_report["package_manager"] = "dnf5"
        rocky10_report["dnf5_backend_checked"] = True
        rocky10_report["python3_libdnf5_installed"] = True
        rocky10_report_path.write_text(json.dumps(rocky10_report), encoding="utf-8")
        validate_evidence(evidence_dir, DEFAULT_EXPECTED_HOSTS)

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["package_manager"] = "yum"
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "package_manager must be one of")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky10-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["package_manager"] = "dnf5"
        broken_report["python3_libdnf5_installed"] = True
        broken_report["dnf5_backend_checked"] = False
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "DNF5 backend runtime check must be recorded")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky10-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["package_manager"] = "dnf5"
        broken_report["dnf5_backend_checked"] = True
        broken_report["python3_libdnf5_installed"] = False
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "python3-libdnf5 must be installed")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky10-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["ansible_core_version"] = "2.18.9"
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "ansible_core_version must be at least")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky10-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["minimum_ansible_core_version_for_rocky10"] = "2.18.0"
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "minimum_ansible_core_version_for_rocky10 must be")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["install_mode"] = "auto"
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "install_mode must be docker")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["official_docker_repo_enabled"] = False
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "official_docker_repo_enabled must be true")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["docker_rpm_repo_file"] = "/etc/yum.repos.d/rocky-docker.repo"
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "Docker RPM repository file must be")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["docker_rpm_repo_uses_docker_centos_repo"] = False
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "Docker RPM repository must use Docker's CentOS repo")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["docker_rpm_repo_gpgcheck_enabled"] = False
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "Docker RPM repository must have gpgcheck=1")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["docker_rpm_repo_gpgkey_url_present"] = False
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "Docker RPM repository must use Docker's CentOS RPM GPG key")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["docker_rpm_gpg_key_fingerprint"] = "bad"
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "Docker RPM GPG key fingerprint must be")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["docker_rpm_gpg_key_imported"] = False
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "Docker RPM GPG key must be imported")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["docker_rpm_packages"] = [
            package
            for package in broken_report["docker_rpm_packages"]
            if package != "docker-ce"
        ]
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "missing Docker RPM packages: docker-ce")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["compose_ps_collected_after_service_wait"] = False
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "compose_ps must be collected after")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["service_wait_timeout_seconds"] = MINIMUM_SERVICE_WAIT_SECONDS - 1
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "service_wait_timeout_seconds does not match")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["service_wait_retries"] = 30
        broken_report["service_wait_delay_seconds"] = 10
        broken_report["service_wait_timeout_seconds"] = 300
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "service wait timeout must be at least")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["running_services"] = [
            service
            for service in broken_report["running_services"]
            if service != "openvas"
        ]
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "missing running services: openvas")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["web_bind_address"] = "0.0.0.0"
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "web_bind_address must be 127.0.0.1")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["web_gsad_probe_status"] = 500
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "unexpected GSAD web probe status")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["web_https_port"] = 8443
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "web_https_port must be 443")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["web_gsad_port"] = 9443
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "web_gsad_port must be 9392")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["web_https_mapping_present"] = False
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "expected HTTPS web mapping")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["web_gsad_mapping_present"] = False
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "expected GSAD web mapping")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky10-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["cpu_flags"] = [
            flag for flag in broken_report["cpu_flags"] if flag != "avx2"
        ]
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "x86-64-v3 CPU feature groups")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["cpu_cores"] = MINIMUM_CPU_CORES - 1
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "CPU cores")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["docker_version"] = "podman version 5.0.0"
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "docker_version does not look like Docker Engine output")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["compose_file"] = "/opt/greenbone-community/docker-compose.yml"
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "compose_file must point to a compose.yaml file")

    with TemporaryDirectory() as tmp:
        evidence_dir = Path(tmp)
        for host, major in DEFAULT_EXPECTED_HOSTS.items():
            _write_sample_report(evidence_dir / f"{host}.json", host, major)

        broken_report_path = evidence_dir / "rocky9-standalone.json"
        broken_report = json.loads(broken_report_path.read_text(encoding="utf-8"))
        broken_report["admin_password_file_checked"] = False
        broken_report_path.write_text(json.dumps(broken_report), encoding="utf-8")
        _expect_evidence_error(evidence_dir, "generated admin password file must be checked")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence-dir",
        default=".secrets/rocky-standalone-evidence",
        type=Path,
        help="Directory containing per-host Rocky acceptance JSON reports.",
    )
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=None,
        help="Reject reports whose validated_at timestamp is older than this many hours.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Reject reports whose acceptance_run_id does not match this value.",
    )
    parser.add_argument(
        "--run-attempt",
        default=None,
        help="Reject reports whose acceptance_run_attempt does not match this value.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run the verifier against generated sample evidence.",
    )
    parser.add_argument(
        "--summary-json",
        action="store_true",
        help="Print a JSON summary of validated Rocky acceptance evidence.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.self_test:
            run_self_test()
        else:
            validate_evidence(
                args.evidence_dir,
                DEFAULT_EXPECTED_HOSTS,
                max_age_hours=args.max_age_hours,
                expected_run_id=args.run_id,
                expected_run_attempt=args.run_attempt,
            )
            if args.summary_json:
                print(json.dumps(evidence_summary(args.evidence_dir, DEFAULT_EXPECTED_HOSTS), indent=2))
                return 0
    except EvidenceError as exc:
        print(f"Rocky acceptance evidence validation failed: {exc}", file=sys.stderr)
        return 1

    print("Rocky acceptance evidence validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
