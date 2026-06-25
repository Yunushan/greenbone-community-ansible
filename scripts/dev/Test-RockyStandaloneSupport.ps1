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
        $effectiveMode -eq "docker" -and
        $SupportedRockyMajorVersions -contains $MajorVersion -and
        ((-not $InstallDockerEngine) -or $UseOfficialRepo)
    )

    Assert-True `
        -Condition ($actualPass -eq $ShouldPass) `
        -Message "Unexpected Rocky ${MajorVersion}/${RequestedMode} support result. Expected ${ShouldPass}, got ${actualPass}."
}

$commonDefaults = Read-RepoFile "roles/greenbone_common/defaults/main.yml"
$commonTasks = Read-RepoFile "roles/greenbone_common/tasks/main.yml"
$dockerDefaults = Read-RepoFile "roles/greenbone_docker/defaults/main.yml"
$redhatTasks = Read-RepoFile "roles/greenbone_docker/tasks/redhat.yml"
$masterPreflightTasks = Read-RepoFile "roles/greenbone_master/tasks/preflight.yml"
$masterDockerTasks = Read-RepoFile "roles/greenbone_master/tasks/docker.yml"
$rockyInventory = Read-RepoFile "inventories/rocky-standalone/hosts.yml"
$rockyDockerRepoSmoke = Read-RepoFile "scripts/dev/Test-RockyDockerRepo.sh"
$rockyDockerRepoMetadata = Read-RepoFile "scripts/dev/Test-RockyDockerRepoMetadata.py"
$rockyAcceptanceEvidence = Read-RepoFile "scripts/dev/Test-RockyAcceptanceEvidence.py"
$greenboneContainerPlatforms = Read-RepoFile "scripts/dev/Test-GreenboneContainerPlatforms.py"
$rockyValidationPlaybook = Read-RepoFile "playbooks/validate-rocky-standalone.yml"
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
Assert-True -Condition ($rockyMajorVersions -contains 9) -Message "Rocky 9 is not in the supported Rocky Docker version allowlist."
Assert-True -Condition ($rockyMajorVersions -contains 10) -Message "Rocky 10 is not in the supported Rocky Docker version allowlist."
Assert-True -Condition ($rockyArchitectures -contains "x86_64") -Message "Rocky x86_64 is not in the supported Rocky Docker architecture allowlist."
Assert-True -Condition ($rockyArchitectures -contains "aarch64") -Message "Rocky aarch64 is not in the supported Rocky Docker architecture allowlist."
Assert-True -Condition ($autoNativeDistributions -notcontains "rocky") -Message "Rocky must not auto-select native installation."

Test-RockyCase -MajorVersion 9 -RequestedMode "auto" -ShouldPass $true -SupportedRockyMajorVersions $rockyMajorVersions -AutoNativeDistributions $autoNativeDistributions
Test-RockyCase -MajorVersion 9 -RequestedMode "docker" -ShouldPass $true -SupportedRockyMajorVersions $rockyMajorVersions -AutoNativeDistributions $autoNativeDistributions
Test-RockyCase -MajorVersion 10 -RequestedMode "auto" -ShouldPass $true -SupportedRockyMajorVersions $rockyMajorVersions -AutoNativeDistributions $autoNativeDistributions
Test-RockyCase -MajorVersion 10 -RequestedMode "docker" -ShouldPass $true -SupportedRockyMajorVersions $rockyMajorVersions -AutoNativeDistributions $autoNativeDistributions
Test-RockyCase -MajorVersion 9 -RequestedMode "docker" -UseOfficialRepo $false -ShouldPass $false -SupportedRockyMajorVersions $rockyMajorVersions -AutoNativeDistributions $autoNativeDistributions
Test-RockyCase -MajorVersion 10 -RequestedMode "docker" -UseOfficialRepo $false -InstallDockerEngine $false -ShouldPass $true -SupportedRockyMajorVersions $rockyMajorVersions -AutoNativeDistributions $autoNativeDistributions
Test-RockyCase -MajorVersion 9 -RequestedMode "native" -ShouldPass $false -SupportedRockyMajorVersions $rockyMajorVersions -AutoNativeDistributions $autoNativeDistributions
Test-RockyCase -MajorVersion 8 -RequestedMode "docker" -ShouldPass $false -SupportedRockyMajorVersions $rockyMajorVersions -AutoNativeDistributions $autoNativeDistributions
Test-RockyCase -MajorVersion 11 -RequestedMode "docker" -ShouldPass $false -SupportedRockyMajorVersions $rockyMajorVersions -AutoNativeDistributions $autoNativeDistributions

Assert-Contains $commonTasks "when: greenbone_distribution_normalized == 'rocky'" "common tasks"
Assert-Contains $commonTasks "ansible_architecture in greenbone_rocky_docker_supported_architectures" "common tasks"
Assert-Contains $commonTasks "greenbone_docker_use_official_repo | default(true) | bool" "common tasks"
Assert-Contains $commonTasks "greenbone_install_docker_engine | default(true) | bool" "common tasks"
Assert-Contains $redhatTasks "else 'centos'" "RedHat Docker tasks"
Assert-Contains $redhatTasks "https://download.docker.com/linux/{{ greenbone_docker_rpm_repo_family }}/docker-ce.repo" "RedHat Docker tasks"
Assert-Contains $masterPreflightTasks "Generate Greenbone admin password" "master preflight tasks"
Assert-Contains $masterPreflightTasks "Set generated Greenbone admin password file path" "master preflight tasks"
Assert-Contains $masterPreflightTasks "ansible.builtin.password" "master preflight tasks"
Assert-Contains $masterPreflightTasks "greenbone_admin_password" "master preflight tasks"
Assert-Contains $masterPreflightTasks "length=32" "master preflight tasks"
Assert-Contains $masterPreflightTasks "chars=['ascii_letters', 'digits']" "master preflight tasks"
Assert-Contains $masterPreflightTasks "greenbone_master_effective_admin_password" "master preflight tasks"
Assert-Contains $masterPreflightTasks "Assert Greenbone admin password is available" "master preflight tasks"
Assert-Contains $masterPreflightTasks "Greenbone admin password is empty." "master preflight tasks"
Assert-Contains $masterPreflightTasks "the empty generated password file" "master preflight tasks"
Assert-Contains $masterPreflightTasks "Secure generated Greenbone admin password file" "master preflight tasks"
Assert-Contains $masterPreflightTasks 'mode: "0600"' "master preflight tasks"
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
Assert-Contains $rockyDockerRepoSmoke "rockylinux:`${major}" "Rocky Docker repository smoke script"
Assert-Contains $rockyDockerRepoSmoke "https://download.docker.com/linux/centos/docker-ce.repo" "Rocky Docker repository smoke script"
Assert-Contains $rockyDockerRepoSmoke "https://greenbone.github.io/docs/latest/_static/compose.yaml" "Rocky Docker repository smoke script"
Assert-Contains $rockyDockerRepoSmoke "docker compose -f" "Rocky Docker repository smoke script"
Assert-Contains $rockyDockerRepoSmoke "docker-compose-plugin" "Rocky Docker repository smoke script"
Assert-Contains $rockyDockerRepoMetadata "RPM_ARCHITECTURES = (`"x86_64`", `"aarch64`")" "Rocky Docker repo metadata script"
Assert-Contains $rockyDockerRepoMetadata "https://download.docker.com/linux/centos/{releasever}/{architecture}/stable/Packages/" "Rocky Docker repo metadata script"
Assert-Contains $rockyDockerRepoMetadata "-[0-9][^`"]+\.el{releasever}\.{re.escape(architecture)}\.rpm" "Rocky Docker repo metadata script"
Assert-Contains $rockyDockerRepoMetadata "for releasever in (9, 10)" "Rocky Docker repo metadata script"
Assert-Contains $rockyDockerRepoMetadata "docker-compose-plugin" "Rocky Docker repo metadata script"
Assert-Contains $rockyAcceptanceEvidence "DEFAULT_EXPECTED_HOSTS" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "rocky9-standalone" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "rocky10-standalone" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "REQUIRED_RUNNING_SERVICES" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "Unexpected evidence report files" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "stale-rocky.json" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "_as_string_list" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "compose_ps evidence must not be empty" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "admin_password_file_size" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "admin_password_file_mode" "Rocky acceptance evidence script"
Assert-Contains $rockyAcceptanceEvidence "--self-test" "Rocky acceptance evidence script"
Assert-Contains $greenboneContainerPlatforms "COMPOSE_URL = `"https://greenbone.github.io/docs/latest/_static/compose.yaml`"" "Greenbone container platform script"
Assert-Contains $greenboneContainerPlatforms "(`"linux`", `"amd64`")" "Greenbone container platform script"
Assert-Contains $greenboneContainerPlatforms "(`"linux`", `"arm64`")" "Greenbone container platform script"
Assert-Contains $greenboneContainerPlatforms "registry_token" "Greenbone container platform script"
Assert-Contains $rockyValidationPlaybook "Validate Rocky Linux standalone Docker installation" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "ansible_distribution_major_version | int in [9, 10]" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "ansible_architecture in greenbone_validate_supported_architectures" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "'architecture': ansible_architecture" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_expected_rocky_major_version is not defined or" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "expected_distribution_major_version" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "docker.service" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "docker" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "compose" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "https://127.0.0.1:" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook ".secrets/rocky-standalone-evidence" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_required_running_services:" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_service_retries: 30" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_service_delay: 10" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "List running Greenbone compose services" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "--services" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "--status" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "retries: `"{{ greenbone_validate_service_retries }}`"" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "until: >-" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "running_services" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_docker_version.stdout" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_compose_version.stdout" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_admin_password_file" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "Assert generated admin password file exists, is not empty, and is private" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_admin_password_file_stat.stat.size | int > 0" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "greenbone_validate_admin_password_file_stat.stat.mode == '0600'" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "admin_password_file_checked" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "admin_password_file_exists" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "admin_password_file_size" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "admin_password_file_mode" "Rocky validation playbook"
Assert-Contains $rockyValidationPlaybook "to_nice_json" "Rocky validation playbook"
Assert-Contains $makefile "ROCKY_INVENTORY ?= inventories/rocky-standalone/hosts.yml" "Makefile"
Assert-Contains $makefile "rocky-standalone:" "Makefile"
Assert-Contains $makefile "rocky-syntax:" "Makefile"
Assert-Contains $makefile "rocky-validate:" "Makefile"
Assert-Contains $workflow "Test-RockyStandaloneSupport.ps1" "GitHub Actions workflow"
Assert-Contains $workflow "Test-RockyDockerRepoMetadata.py" "GitHub Actions workflow"
Assert-Contains $workflow "Test-GreenboneContainerPlatforms.py" "GitHub Actions workflow"
Assert-Contains $workflow "Test-RockyAcceptanceEvidence.py --self-test" "GitHub Actions workflow"
Assert-Contains $workflow "Test-RockyDockerRepo.sh" "GitHub Actions workflow"
Assert-Contains $workflow "actions/checkout@v7" "GitHub Actions workflow"
Assert-Contains $workflow "actions/setup-python@v6" "GitHub Actions workflow"
Assert-Contains $workflow "ansible-playbook -i inventories/rocky-standalone/hosts.yml site.yml --syntax-check" "GitHub Actions workflow"
Assert-Contains $workflow "ansible-playbook -i inventories/rocky-standalone/hosts.yml playbooks/validate-rocky-standalone.yml --syntax-check" "GitHub Actions workflow"
Assert-Contains $workflow "ansible-playbook -i inventories/rocky-standalone/hosts.yml site.yml --list-hosts" "GitHub Actions workflow"
Assert-Contains $acceptanceWorkflow "workflow_dispatch:" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "runner_label:" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "runs-on: `${{ inputs.runner_label }}" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "actions/checkout@v7" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "actions/setup-python@v6" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "ROCKY9_HOST: `${{ secrets.ROCKY9_HOST }}" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "ROCKY10_HOST: `${{ secrets.ROCKY10_HOST }}" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "ROCKY_SSH_PORT must be an integer between 1 and 65535" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow 'ansible_ssh_private_key_file: "${HOME}/.ssh/id_ed25519"' "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "greenbone_expected_rocky_major_version: 9" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "greenbone_expected_rocky_major_version: 10" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "greenbone_docker_use_official_repo: true" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "Verify Rocky SSH and sudo access" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "ansible.builtin.ping --become" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "Clear previous Rocky acceptance evidence" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "rm -rf .secrets/rocky-standalone-evidence" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "Test-RockyAcceptanceEvidence.py" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "ansible-playbook -i `"`${ACCEPTANCE_INVENTORY}`" site.yml" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "playbooks/validate-rocky-standalone.yml" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "actions/upload-artifact@v7" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "if: always()" "Rocky acceptance workflow"
Assert-Contains $acceptanceWorkflow "if-no-files-found: warn" "Rocky acceptance workflow"

Write-Host "Rocky standalone support validation passed."
