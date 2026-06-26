$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")

function Read-RepoFile {
    param([string] $RelativePath)
    Get-Content -Raw -Path (Join-Path $RepoRoot $RelativePath)
}

function Assert-True {
    param(
        [bool] $Condition,
        [string] $Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Assert-Contains {
    param(
        [string] $Text,
        [string] $Needle,
        [string] $Context
    )

    Assert-True -Condition $Text.Contains($Needle) -Message "Missing expected content in ${Context}: ${Needle}"
}

function Get-TopLevelListValues {
    param(
        [string] $YamlText,
        [string] $Key
    )

    $values = New-Object System.Collections.Generic.List[string]
    $inside = $false

    foreach ($line in ($YamlText -split "`r?`n")) {
        if ($line -match "^$([regex]::Escape($Key)):\s*$") {
            $inside = $true
            continue
        }

        if ($inside -and $line -match "^\S") {
            break
        }

        if ($inside -and $line -match "^\s*-\s*(.+?)\s*$") {
            $values.Add($Matches[1])
        }
    }

    return $values.ToArray()
}

function Get-EffectiveInstallMode {
    param(
        [string] $RequestedMode,
        [string] $DistributionNormalized,
        [string[]] $AutoNativeDistributions
    )

    if ($RequestedMode -eq "native") {
        return "native"
    }

    if ($RequestedMode -eq "auto" -and $AutoNativeDistributions -contains $DistributionNormalized) {
        return "native"
    }

    return "docker"
}

function Test-RockyCase {
    param(
        [int] $MajorVersion,
        [string] $RequestedMode,
        [bool] $ShouldPass,
        [int[]] $SupportedRockyMajorVersions,
        [string[]] $AutoNativeDistributions,
        [bool] $UseOfficialRepo = $true,
        [bool] $InstallDockerEngine = $true
    )

    $effectiveMode = Get-EffectiveInstallMode `
        -RequestedMode $RequestedMode `
        -DistributionNormalized "rocky" `
        -AutoNativeDistributions $AutoNativeDistributions
    $actualPass = (
        $RequestedMode -eq "docker" -and
        $effectiveMode -eq "docker" -and
        $SupportedRockyMajorVersions -contains $MajorVersion -and
        $UseOfficialRepo
    )

    Assert-True `
        -Condition ($actualPass -eq $ShouldPass) `
        -Message "Unexpected Rocky ${MajorVersion}/${RequestedMode} support result. Expected ${ShouldPass}, got ${actualPass}."
}

$commonDefaults = Read-RepoFile "roles/greenbone_common/defaults/main.yml"
$commonTasks = Read-RepoFile "roles/greenbone_common/tasks/main.yml"
$dockerDefaults = Read-RepoFile "roles/greenbone_docker/defaults/main.yml"
$redhatTasks = Read-RepoFile "roles/greenbone_docker/tasks/redhat.yml"
$groupVars = Read-RepoFile "group_vars/all.yml"
$masterPreflightTasks = Read-RepoFile "roles/greenbone_master/tasks/preflight.yml"
$masterDockerTasks = Read-RepoFile "roles/greenbone_master/tasks/docker.yml"
$rockyInventory = Read-RepoFile "inventories/rocky-standalone/hosts.yml"
$installPlaybook = Read-RepoFile "playbooks/install.yml"
$rockyBootstrapPlaybook = Read-RepoFile "playbooks/bootstrap-rocky-standalone.yml"
$rockyDockerRepoSmoke = Read-RepoFile "scripts/dev/Test-RockyDockerRepo.sh"
$rockyDockerRepoMetadata = Read-RepoFile "scripts/dev/Test-RockyDockerRepoMetadata.py"
$rockyAcceptanceEvidence = Read-RepoFile "scripts/dev/Test-RockyAcceptanceEvidence.py"
$greenboneContainerPlatforms = Read-RepoFile "scripts/dev/Test-GreenboneContainerPlatforms.py"
$rockyPreflightPlaybook = Read-RepoFile "playbooks/preflight-rocky-standalone.yml"
$rockyValidationPlaybook = Read-RepoFile "playbooks/validate-rocky-standalone.yml"
$rockyDiagnosticsPlaybook = Read-RepoFile "playbooks/collect-rocky-standalone-diagnostics.yml"
$makefile = Read-RepoFile "Makefile"
$workflow = Read-RepoFile ".github/workflows/ansible-lint.yml"
$acceptanceWorkflow = Read-RepoFile ".github/workflows/rocky-standalone-acceptance.yml"

$supportedDistributions = Get-TopLevelListValues $commonDefaults "greenbone_supported_distributions_normalized"
$autoNativeDistributions = Get-TopLevelListValues $commonDefaults "greenbone_auto_native_distributions_normalized"
$rockyMajorVersions = Get-TopLevelListValues $commonDefaults "greenbone_rocky_docker_supported_major_versions" | ForEach-Object { [int] $_ }
$rockyArchitectures = Get-TopLevelListValues $commonDefaults "greenbone_rocky_docker_supported_architectures"
$rpmConflicts = Get-TopLevelListValues $dockerDefaults "greenbone_docker_rpm_conflicting_packages"
$rpmPackages = Get-TopLevelListValues $dockerDefaults "greenbone_docker_rpm_packages"

Assert-True -Condition ($supportedDistributions -contains "rocky") -Message "Rocky is not in supported distributions."
Assert-True -Condition ($supportedDistributions -contains "rockylinux") -Message "Rocky Linux normalized name is not in supported distributions."
Assert-True -Condition ($rockyMajorVersions -contains 9) -Message "Rocky 9 is not in the supported Rocky Docker version allowlist."
Assert-True -Condition ($rockyMajorVersions -contains 10) -Message "Rocky 10 is not in the supported Rocky Docker version allowlist."
Assert-True -Condition ($rockyArchitectures -contains "x86_64") -Message "Rocky x86_64 is not in the supported Rocky Docker architecture allowlist."
Assert-True -Condition ($rockyArchitectures -contains "aarch64") -Message "Rocky aarch64 is not in the supported Rocky Docker architecture allowlist."
Assert-Contains $commonDefaults 'greenbone_rocky10_min_ansible_core_version: "2.19.0"' "common defaults"
Assert-Contains $commonDefaults "greenbone_rocky_validate_service_retries: 60" "common defaults"
Assert-Contains $commonDefaults "greenbone_rocky_validate_service_delay: 15" "common defaults"
Assert-True -Condition ($autoNativeDistributions -notcontains "rocky") -Message "Rocky must not auto-select native installation."
Assert-True -Condition ($autoNativeDistributions -notcontains "rockylinux") -Message "Rocky Linux must not auto-select native installation."
Assert-Contains $commonDefaults "default('.', true)" "common defaults"
Assert-Contains $groupVars "default('.', true)" "group vars"
Assert-Contains $groupVars 'greenbone_admin_password: ""' "group vars"

Test-RockyCase -MajorVersion 9 -RequestedMode "auto" -ShouldPass $false -SupportedRockyMajorVersions $rockyMajorVersions -AutoNativeDistributions $autoNativeDistributions
Test-RockyCase -MajorVersion 9 -RequestedMode "docker" -ShouldPass $true -SupportedRockyMajorVersions $rockyMajorVersions -AutoNativeDistributions $autoNativeDistributions
Test-RockyCase -MajorVersion 10 -RequestedMode "auto" -ShouldPass $false -SupportedRockyMajorVersions $rockyMajorVersions -AutoNativeDistributions $autoNativeDistributions
Test-RockyCase -MajorVersion 10 -RequestedMode "docker" -ShouldPass $true -SupportedRockyMajorVersions $rockyMajorVersions -AutoNativeDistributions $autoNativeDistributions
Test-RockyCase -MajorVersion 9 -RequestedMode "docker" -UseOfficialRepo $false -ShouldPass $false -SupportedRockyMajorVersions $rockyMajorVersions -AutoNativeDistributions $autoNativeDistributions
Test-RockyCase -MajorVersion 10 -RequestedMode "docker" -UseOfficialRepo $false -InstallDockerEngine $false -ShouldPass $false -SupportedRockyMajorVersions $rockyMajorVersions -AutoNativeDistributions $autoNativeDistributions
Test-RockyCase -MajorVersion 9 -RequestedMode "native" -ShouldPass $false -SupportedRockyMajorVersions $rockyMajorVersions -AutoNativeDistributions $autoNativeDistributions
Test-RockyCase -MajorVersion 8 -RequestedMode "docker" -ShouldPass $false -SupportedRockyMajorVersions $rockyMajorVersions -AutoNativeDistributions $autoNativeDistributions
Test-RockyCase -MajorVersion 11 -RequestedMode "docker" -ShouldPass $false -SupportedRockyMajorVersions $rockyMajorVersions -AutoNativeDistributions $autoNativeDistributions

Assert-Contains $commonTasks "greenbone_distribution_normalized in ['rocky', 'rockylinux']" "common tasks"
Assert-Contains $commonTasks "greenbone_install_mode == 'docker'" "common tasks"
Assert-Contains $commonTasks "ansible_architecture in greenbone_rocky_docker_supported_architectures" "common tasks"
Assert-Contains $commonTasks "greenbone_docker_use_official_repo | default(true) | bool" "common tasks"
Assert-Contains $commonTasks "greenbone_docker_use_official_repo=true" "common tasks"
Assert-Contains $commonTasks "Assert controller ansible-core supports Rocky Linux 10" "common tasks"
Assert-Contains $commonTasks "greenbone_rocky10_min_ansible_core_version" "common tasks"
Assert-Contains $commonTasks "Bootstrap DNF5 Python bindings when target reports DNF5" "common tasks"
Assert-Contains $commonTasks "ansible.builtin.raw" "common tasks"
Assert-Contains $commonTasks "set -eu" "common tasks"
Assert-Contains $commonTasks "dnf -q list --available python3-libdnf5" "common tasks"
Assert-Contains $commonTasks "greenbone_common_rocky10_dnf5_bootstrap" "common tasks"
Assert-Contains $commonTasks "greenbone_dnf5_bootstrap=changed" "common tasks"
Assert-Contains $redhatTasks "else 'centos'" "RedHat Docker tasks"
Assert-Contains $redhatTasks "https://download.docker.com/linux/{{ greenbone_docker_rpm_repo_family }}/docker-ce.repo" "RedHat Docker tasks"
Assert-Contains $redhatTasks "greenbone_docker_rpm_gpg_key_url" "RedHat Docker tasks"
Assert-Contains $redhatTasks "Import Docker RPM GPG key" "RedHat Docker tasks"
Assert-Contains $redhatTasks "ansible.builtin.rpm_key" "RedHat Docker tasks"
Assert-Contains $redhatTasks "fingerprint: `"{{ greenbone_docker_rpm_gpg_fingerprint }}`"" "RedHat Docker tasks"
Assert-Contains $dockerDefaults "060A 61C5 1B55 8A7F 742B 77AA C52F EB6B 621E 9F35" "Docker defaults"
Assert-Contains $masterPreflightTasks "Generate Greenbone admin password" "master preflight tasks"
Assert-Contains $masterPreflightTasks "Set generated Greenbone admin password file path" "master preflight tasks"
Assert-Contains $masterPreflightTasks "ansible.builtin.password" "master preflight tasks"
Assert-Contains $masterPreflightTasks "greenbone_admin_password" "master preflight tasks"
Assert-Contains $masterPreflightTasks "length=32" "master preflight tasks"
Assert-Contains $masterPreflightTasks "chars=['ascii_letters', 'digits']" "master preflight tasks"
Assert-Contains $masterPreflightTasks "throttle: 1" "master preflight tasks"
Assert-Contains $masterPreflightTasks "greenbone_master_effective_admin_password" "master preflight tasks"
Assert-Contains $masterPreflightTasks "Assert Greenbone admin password is available" "master preflight tasks"
Assert-Contains $masterPreflightTasks "Greenbone admin password is empty." "master preflight tasks"
Assert-Contains $masterPreflightTasks "the empty generated password file" "master preflight tasks"
Assert-Contains $masterPreflightTasks "Secure generated Greenbone admin password file" "master preflight tasks"
Assert-Contains $masterPreflightTasks 'mode: "0600"' "master preflight tasks"
Assert-Contains $masterPreflightTasks "default('.', true)" "master preflight tasks"
Assert-Contains $masterDockerTasks "Assert Greenbone Docker compose web port mappings are patched" "master Docker tasks"
Assert-Contains $masterDockerTasks "Validate Greenbone Docker compose configuration" "master Docker tasks"
Assert-Contains $masterDockerTasks "greenbone_master_effective_admin_password" "master Docker tasks"
Assert-Contains $masterDockerTasks "docker" "master Docker tasks"
Assert-Contains $masterDockerTasks "compose" "master Docker tasks"
Assert-Contains $masterDockerTasks "config" "master Docker tasks"

foreach ($package in @("docker-ce", "docker-ce-cli", "containerd.io", "docker-buildx-plugin", "docker-compose-plugin")) {
    Assert-True -Condition ($rpmPackages -contains $package) -Message "Missing Docker RPM package: ${package}"
}

foreach ($package in @("podman", "podman-docker", "containerd", "runc")) {
    Assert-True -Condition ($rpmConflicts -contains $package) -Message "Missing Docker RPM conflict package: ${package}"
}

Assert-Contains $rockyInventory "greenbone_install_mode: docker" "Rocky standalone inventory"
Assert-Contains $rockyInventory "greenbone_docker_use_official_repo: true" "Rocky standalone inventory"
Assert-Contains $rockyInventory "greenbone_web_bind_address: `"127.0.0.1`"" "Rocky standalone inventory"
Assert-Contains $rockyInventory "greenbone-rocky-standalone:" "Rocky standalone inventory"
Assert-Contains $rockyInventory "greenbone_workers:" "Rocky standalone inventory"
Assert-Contains $rockyInventory "hosts: {}" "Rocky standalone inventory"
Assert-Contains $installPlaybook "import_playbook: bootstrap-rocky-standalone.yml" "install playbook"
Assert-Contains $rockyPreflightPlaybook "import_playbook: bootstrap-rocky-standalone.yml" "Rocky preflight playbook"
Assert-Contains $rockyBootstrapPlaybook "Bootstrap Rocky Linux standalone Python support" "Rocky bootstrap playbook"
Assert-Contains $rockyBootstrapPlaybook "gather_facts: false" "Rocky bootstrap playbook"
Assert-Contains $rockyBootstrapPlaybook "ansible.builtin.raw" "Rocky bootstrap playbook"
Assert-Contains $rockyBootstrapPlaybook 'if [ "${ID:-}" != "rocky" ]; then' "Rocky bootstrap playbook"
Assert-Contains $rockyBootstrapPlaybook 'rocky_major="${VERSION_ID:-}"' "Rocky bootstrap playbook"
Assert-Contains $rockyBootstrapPlaybook 'packages="python3 python3-dnf python3-libdnf"' "Rocky bootstrap playbook"
Assert-Contains $rockyBootstrapPlaybook "dnf -q list --available python3-libdnf5" "Rocky bootstrap playbook"
Assert-Contains $rockyBootstrapPlaybook "python3-libdnf5" "Rocky bootstrap playbook"
Assert-Contains $rockyBootstrapPlaybook "dnf -y install" "Rocky bootstrap playbook"
Assert-Contains $rockyBootstrapPlaybook "greenbone_bootstrap_rocky_python_result" "Rocky bootstrap playbook"
Assert-Contains $rockyBootstrapPlaybook "greenbone_rocky_python_bootstrap=changed" "Rocky bootstrap playbook"
Assert-Contains $rockyDockerRepoSmoke "rockylinux:`${major}" "Rocky Docker repository smoke script"
Assert-Contains $rockyDockerRepoSmoke "https://download.docker.com/linux/centos/docker-ce.repo" "Rocky Docker repository smoke script"
Assert-Contains $rockyDockerRepoSmoke "https://greenbone.github.io/docs/latest/_static/compose.yaml" "Rocky Docker repository smoke script"
Assert-Contains $rockyDockerRepoSmoke "docker compose -f" "Rocky Docker repository smoke script"
Assert-Contains $rockyDockerRepoSmoke "docker-compose-plugin" "Rocky Docker repository smoke script"
Assert-Contains $rockyDockerRepoMetadata "ROCKY_PREREQUISITE_PACKAGES" "Rocky Docker repo metadata script"
Assert-Contains $rockyDockerRepoMetadata '"python3-dnf"' "Rocky Docker repo metadata script"
Assert-Contains $rockyDockerRepoMetadata '"python3-libdnf"' "Rocky Docker repo metadata script"
Assert-Contains $rockyDockerRepoMetadata "ROCKY_REPOSITORIES = (`"BaseOS`", `"AppStream`")" "Rocky Docker repo metadata script"
Assert-Contains $rockyDockerRepoMetadata "validate_rocky_prerequisites" "Rocky Docker repo metadata script"
Assert-Contains $rockyDockerRepoMetadata "official repos publish required prerequisites" "Rocky Docker repo metadata script"
Assert-Contains $rockyDockerRepoMetadata "RPM_ARCHITECTURES = (`"x86_64`", `"aarch64`")" "Rocky Docker repo metadata script"
Assert-Contains $rockyDockerRepoMetadata 'GPG_KEY_URL = "https://download.docker.com/linux/centos/gpg"' "Rocky Docker repo metadata script"
Assert-Contains $rockyDockerRepoMetadata "validate_gpg_key()" "Rocky Docker repo metadata script"
Assert-Contains $rockyDockerRepoMetadata "https://download.docker.com/linux/centos/{releasever}/{architecture}/stable/Packages/" "Rocky Docker repo metadata script"
Assert-Contains $rockyDockerRepoMetadata "-[0-9][^`"]+\.el{releasever}\.{re.escape(architecture)}\.rpm" "Rocky Docker repo metadata script"
Assert-Contains $rockyDockerRepoMetadata "for releasever in (9, 10)" "Rocky Docker repo metadata script"
Assert-Contains $rockyDockerRepoMetadata "docker-compose-plugin" "Rocky Docker repo metadata script"
Assert-Contains $rockyAcceptanceEvidence "DEFAULT_EXPECTED_HOSTS" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "SUPPORTED_ROCKY_DISTRIBUTION_NAMES" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "Rocky Linux" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "rocky9-standalone" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "rocky10-standalone" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "validated_at" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "install_mode" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "official_docker_repo_enabled" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "REQUIRED_RUNNING_SERVICES" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence '"openvas"' "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence '"openvasd"' "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence '"ospd-openvas"' "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "Unexpected evidence report files" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "stale-rocky.json" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "_as_string_list" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "compose_ps evidence must not be empty" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "compose_ps_collected_after_service_wait" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "compose_ps must be collected after" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "MINIMUM_SERVICE_WAIT_SECONDS = 900" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "service_wait_timeout_seconds does not match" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "service wait timeout must be at least" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "missing running services: openvas" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "MINIMUM_CPU_CORES = 4" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "MINIMUM_MEMORY_MB = 8192" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "MINIMUM_DISK_MB = 61440" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "EXPECTED_DOCKER_RPM_REPO_FILE" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "SUPPORTED_PACKAGE_MANAGERS" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "package_manager must be one of" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "DNF5 backend runtime check must be recorded" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "python3-libdnf5 must be installed" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence '"package_manager": "dnf"' "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence '"package_manager"] = "dnf5"' "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence '"dnf5_backend_checked": False' "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence '"python3_libdnf5_installed": False' "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence '"os_family": "RedHat"' "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence '"kernel":' "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence '"package_manager":' "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "MINIMUM_ANSIBLE_CORE_VERSION_FOR_ROCKY10" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "MINIMUM_ANSIBLE_CORE_VERSION_FOR_ROCKY10_TEXT" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "ansible_core_version must be at least" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "minimum_ansible_core_version_for_rocky10 must be" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "EXPECTED_WEB_BIND_ADDRESS" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "EXPECTED_WEB_HTTPS_PORT" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "EXPECTED_WEB_GSAD_PORT" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "minimum_cpu_cores" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "disk_mb_available" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "admin_password_file_size" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "admin_password_file_mode" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "generated admin password file must be checked" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "REQUIRED_DOCKER_RPM_PACKAGES" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "docker_rpm_repo_uses_docker_centos_repo" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "docker_rpm_repo_gpgcheck_enabled" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "docker_rpm_repo_gpgkey_url_present" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "EXPECTED_DOCKER_RPM_GPG_FINGERPRINT" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "EXPECTED_DOCKER_RPM_GPG_KEY_ID" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "Docker RPM GPG key must be imported" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "Docker RPM repository file must be" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "Docker RPM repository must have gpgcheck=1" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "Docker RPM repository must use Docker's CentOS RPM GPG key" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "docker_version does not look like Docker Engine output" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "compose_file must point to a compose.yaml file" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "web_bind_address must be 127.0.0.1" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "web_https_port must be 443" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "web_gsad_port must be 9392" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "expected HTTPS web mapping" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "expected GSAD web mapping" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "web_gsad_probe_status" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "unexpected GSAD web probe status" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "--self-test" "Rocky acceptance evidence script"
Assert-Contains $greenboneContainerPlatforms "COMPOSE_URL = `"https://greenbone.github.io/docs/latest/_static/compose.yaml`"" "Greenbone container platform script"
Assert-Contains $greenboneContainerPlatforms "(`"linux`", `"amd64`")" "Greenbone container platform script"
Assert-Contains $greenboneContainerPlatforms "(`"linux`", `"arm64`")" "Greenbone container platform script"
Assert-Contains $greenboneContainerPlatforms "REQUIRED_COMPOSE_SERVICES" "Greenbone container platform script"
Assert-Contains $greenboneContainerPlatforms "REQUIRED_NGINX_PORTS" "Greenbone container platform script"
Assert-Contains $greenboneContainerPlatforms "assert_compose_topology(compose)" "Greenbone container platform script"
Assert-Contains $greenboneContainerPlatforms "Official Greenbone compose topology matches Rocky validation expectations." "Greenbone container platform script"
Assert-Contains $greenboneContainerPlatforms "registry_token" "Greenbone container platform script"
Assert-Contains $rockyDiagnosticsPlaybook "Collect Rocky Linux standalone Docker diagnostics" "Rocky diagnostics playbook"
Assert-Contains $rockyDiagnosticsPlaybook "greenbone_diag_dir" "Rocky diagnostics playbook"
Assert-Contains $rockyDiagnosticsPlaybook "rocky-standalone-diagnostics" "Rocky diagnostics playbook"
Assert-Contains $rockyDiagnosticsPlaybook "compose_logs_stdout" "Rocky diagnostics playbook"
Assert-Contains $rockyDiagnosticsPlaybook "docker_service_stdout" "Rocky diagnostics playbook"
Assert-Contains $rockyDiagnosticsPlaybook "docker_info_stdout" "Rocky diagnostics playbook"
Assert-Contains $rockyDiagnosticsPlaybook "selinux_stdout" "Rocky diagnostics playbook"
Assert-Contains $rockyDiagnosticsPlaybook "firewalld_stdout" "Rocky diagnostics playbook"
Assert-Contains $rockyDiagnosticsPlaybook "docker_rpm_repo_gpgcheck_enabled" "Rocky diagnostics playbook"
Assert-Contains $rockyDiagnosticsPlaybook "docker_rpm_gpg_key_imported" "Rocky diagnostics playbook"
Assert-Contains $rockyDiagnosticsPlaybook "'package_manager': ansible_pkg_mgr | default('unknown')" "Rocky diagnostics playbook"
Assert-Contains $rockyDiagnosticsPlaybook "greenbone_diag_python3_libdnf5" "Rocky diagnostics playbook"
Assert-Contains $rockyDiagnosticsPlaybook "'python3_libdnf5_installed': greenbone_diag_python3_libdnf5.rc == 0" "Rocky diagnostics playbook"
Assert-Contains $rockyDiagnosticsPlaybook "'ansible_core_version': ansible_version.full" "Rocky diagnostics playbook"
Assert-Contains $rockyValidationPlaybook "Validate Rocky Linux standalone Docker installation" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "ansible_distribution_major_version | int in [9, 10]" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "ansible_architecture in greenbone_validate_supported_architectures" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_install_mode == 'docker'" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_docker_use_official_repo | default(true) | bool" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_install_mode=docker" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "official CentOS RPM repository" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_min_cpu_cores" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_min_memory_mb" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_min_disk_mb" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_disk_check_path" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "Record Rocky validation resource facts" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "Assert target has minimum Greenbone container resources" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "'architecture': ansible_architecture" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "'os_family': ansible_os_family" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "'kernel': ansible_kernel | default('unknown')" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "'package_manager': ansible_pkg_mgr | default('unknown')" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "Assert Rocky Linux reports a supported package manager" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "ansible_pkg_mgr | default('unknown') in ['dnf', 'dnf5']" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "Check python3-libdnf5 package for DNF5 package-manager backend" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "Assert DNF5 package-manager backend runtime is installed" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "'dnf5_backend_checked': ansible_pkg_mgr | default('unknown') == 'dnf5'" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "'python3_libdnf5_installed':" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_rocky10_min_ansible_core_version" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "Assert controller ansible-core supports Rocky Linux 10" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "'ansible_core_version': ansible_version.full" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_expected_rocky_major_version is not defined or" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "expected_distribution_major_version" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "'validated_at': ansible_date_time.iso8601" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "'install_mode': greenbone_install_mode" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "'official_docker_repo_enabled': greenbone_docker_use_official_repo | default(true) | bool" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "docker.service" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "docker" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "compose" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "https://127.0.0.1:" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_web_bind_address" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_web_gsad_port" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "Probe local Greenbone GSAD endpoint" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_gsad_web_probe" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "Assert Greenbone compose web mappings are localhost-bound" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_compose_web_https_mapping" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_compose_web_gsad_mapping" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "'web_bind_address': greenbone_validate_web_bind_address" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "'web_https_port': greenbone_validate_web_https_port | int" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "'web_gsad_port': greenbone_validate_web_gsad_port | int" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "'web_https_mapping_present':" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "'web_gsad_mapping_present':" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "'web_gsad_probe_status':" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_secret_dir" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "rocky-standalone-evidence" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_required_running_services:" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "      - openvas" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "      - openvasd" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "      - ospd-openvas" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_rocky_validate_service_retries | default(60)" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_rocky_validate_service_delay | default(15)" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "List Greenbone compose services after readiness gate" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "List running Greenbone compose services" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "--services" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "--status" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "retries: `"{{ greenbone_validate_service_retries }}`"" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "until: >-" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "running_services" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_docker_version.stdout" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_compose_version.stdout" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_admin_password_file" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_default_secret_dir" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_secret_dir" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_docker_rpm_repo_file" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_docker_rpm_repo_gpgcheck_marker" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_docker_rpm_repo_gpgkey_marker" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_docker_rpm_gpg_fingerprint" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "Assert Docker RPM GPG key is imported" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "'docker_rpm_gpg_key_imported':" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_default_docker_rpm_packages" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_docker_rpm_packages" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_docker_rpm_repo_file_stat.stat.isreg" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "content | default('') | b64decode" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "--queryformat" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "%{NAME}\n" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "failed_when: false" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "Assert required Docker RPM packages are installed" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "Missing required Docker RPM packages" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "Assert Docker RPM repository is the supported CentOS repository" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "Docker's CentOS RPM GPG key configured" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "'docker_rpm_repo_gpgcheck_enabled':" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "'docker_rpm_repo_gpgkey_url_present':" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "Check required Docker RPM packages" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "Assert generated admin password file exists, is not empty, and is private" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_admin_password_file_stat.stat.size | int > 0" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_admin_password_file_stat.stat.mode == '0600'" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "admin_password_file_checked" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "admin_password_file_exists" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "admin_password_file_size" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "admin_password_file_mode" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "'cpu_cores': greenbone_validate_cpu_cores | int" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "'disk_mb_available': greenbone_validate_disk_mb_available | int" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "compose_ps_collected_after_service_wait" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "'service_wait_retries': greenbone_validate_service_retries | int" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "'service_wait_delay_seconds': greenbone_validate_service_delay | int" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "'service_wait_timeout_seconds':" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "to_nice_json" "Rocky validation playbook"
Assert-Contains $makefile "ROCKY_INVENTORY ?= inventories/rocky-standalone/hosts.yml" "Makefile"
Assert-Contains $makefile "rocky-standalone:" "Makefile"
Assert-Contains $makefile "rocky-preflight:" "Makefile"
Assert-Contains $makefile "rocky-syntax:" "Makefile"
Assert-Contains $makefile "playbooks/bootstrap-rocky-standalone.yml --syntax-check" "Makefile"
Assert-Contains $makefile "playbooks/collect-rocky-standalone-diagnostics.yml --syntax-check" "Makefile"
Assert-Contains $makefile "rocky-validate:" "Makefile"
Assert-Contains $workflow "Test-RockyStandaloneSupport.ps1" "GitHub Actions workflow"
Assert-Contains $workflow "Run Rocky RPM repository metadata validation" "GitHub Actions workflow"
Assert-Contains $workflow "Test-RockyDockerRepoMetadata.py" "GitHub Actions workflow"
Assert-Contains $workflow "Test-GreenboneContainerPlatforms.py" "GitHub Actions workflow"
Assert-Contains $workflow "Test-RockyAcceptanceEvidence.py --self-test" "GitHub Actions workflow"
Assert-Contains $workflow "Test-RockyDockerRepo.sh" "GitHub Actions workflow"
Assert-Contains $workflow "actions/checkout@v7" "GitHub Actions workflow"
Assert-Contains $workflow "actions/setup-python@v6" "GitHub Actions workflow"
Assert-Contains $workflow "permissions:" "GitHub Actions workflow"
Assert-Contains $workflow "contents: read" "GitHub Actions workflow"
Assert-Contains $workflow "playbooks/bootstrap-rocky-standalone.yml --syntax-check" "GitHub Actions workflow"
Assert-Contains $workflow "playbooks/preflight-rocky-standalone.yml --syntax-check" "GitHub Actions workflow"
Assert-Contains $workflow "playbooks/collect-rocky-standalone-diagnostics.yml --syntax-check" "GitHub Actions workflow"
Assert-Contains $workflow "ansible-playbook -i inventories/rocky-standalone/hosts.yml site.yml --syntax-check" "GitHub Actions workflow"
Assert-Contains $workflow "ansible-playbook -i inventories/rocky-standalone/hosts.yml playbooks/validate-rocky-standalone.yml --syntax-check" "GitHub Actions workflow"
Assert-Contains $workflow "ansible-playbook -i inventories/rocky-standalone/hosts.yml site.yml --list-hosts" "GitHub Actions workflow"
Assert-Contains $acceptanceWorkflow "workflow_dispatch:" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "runner_label:" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "runs-on: `${{ inputs.runner_label }}" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "actions/checkout@v7" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "Clear previous Rocky local artifacts" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "rm -rf .secrets/rocky-standalone-evidence" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "rm -rf .secrets/rocky-standalone-diagnostics" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "actions/setup-python@v6" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "permissions:" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "contents: read" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "concurrency:" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "group: rocky-standalone-acceptance" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "ROCKY9_HOST: `${{ secrets.ROCKY9_HOST }}" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "ROCKY10_HOST: `${{ secrets.ROCKY10_HOST }}" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "ROCKY_BECOME_PASSWORD: `${{ secrets.ROCKY_BECOME_PASSWORD }}" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow '::add-mask::${ROCKY_BECOME_PASSWORD}' "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "ROCKY_SSH_PORT must be an integer between 1 and 65535" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "ROCKY9_HOST and ROCKY10_HOST must be different hosts" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "ansible_ssh_private_key_file" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "ansible_become_password" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "ssh-keyscan -T 10" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "Failed to collect SSH host key" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "SSH known_hosts is empty" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "SSH known_hosts does not contain valid host keys" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "ssh-keygen -l -f ~/.ssh/known_hosts" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "ansible_ssh_common_args" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "--graph" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "greenbone_expected_rocky_major_version: 9" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "greenbone_expected_rocky_major_version: 10" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "greenbone_docker_use_official_repo" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "Verify Rocky SSH and sudo access" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "ansible.builtin.raw" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "id -u && test -r /etc/os-release" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "Run Rocky standalone preflight" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "playbooks/preflight-rocky-standalone.yml" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "Test-RockyAcceptanceEvidence.py" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "Collect Rocky diagnostics on failure" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "continue-on-error: true" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "playbooks/collect-rocky-standalone-diagnostics.yml" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "rocky-standalone-diagnostics" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "ansible-playbook -i `"`${ACCEPTANCE_INVENTORY}`" site.yml" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "playbooks/validate-rocky-standalone.yml" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "actions/upload-artifact@v7" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "if: always()" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "if-no-files-found: warn" "Rocky acceptance workflow"
Assert-Contains $rockyPreflightPlaybook "Preflight Rocky Linux standalone Docker targets" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "greenbone_rocky_preflight_min_cpu_cores" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "greenbone_rocky_preflight_min_memory_mb" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "greenbone_rocky_preflight_min_disk_mb" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "greenbone_preflight_rocky10_min_ansible_core_version" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "greenbone_rocky_preflight_disk_check_path" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "greenbone_preflight_default_docker_rpm_packages" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "greenbone_preflight_docker_rpm_packages" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "greenbone_preflight_default_disk_check_path" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "| dirname" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "greenbone_preflight_min_cpu_cores | int" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "greenbone_preflight_min_memory_mb | int" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "greenbone_preflight_min_disk_mb | int" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "Check available disk space for Greenbone work directory" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "Assert target has minimum Greenbone container resources" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "ansible_distribution_major_version | int in [9, 10]" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "ansible_architecture in greenbone_preflight_supported_architectures" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "greenbone_install_mode == 'docker'" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "greenbone_docker_use_official_repo | default(true) | bool" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "greenbone_expected_rocky_major_version is not defined or" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "Assert controller ansible-core supports Rocky Linux 10" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "Assert Rocky Linux reports a supported package manager" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "ansible_pkg_mgr | default('unknown') in ['dnf', 'dnf5']" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "https://download.docker.com/linux/centos/docker-ce.repo" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "https://download.docker.com/linux/centos/gpg" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "Record target Docker RPM metadata URL" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "stable/Packages/" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "Check Docker RPM metadata for target release and architecture" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "return_content: true" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "Assert Docker RPM metadata publishes required packages" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "regex_escape" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "https://greenbone.github.io/docs/latest/_static/compose.yaml" "Rocky preflight playbook"
Assert-Contains $rockyPreflightPlaybook "https://registry.community.greenbone.net/v2/" "Rocky preflight playbook"

Write-Host "Rocky standalone support validation passed."
