param(
    [string] $Distro = $env:ROCKY_ACCEPTANCE_WSL_DISTRO,
    [switch] $SelfTest
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Distro)) {
    $Distro = "Ubuntu"
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")

function Invoke-NativeChecked {
    param(
        [string[]] $Arguments,
        [string] $Description
    )

    & wsl.exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "${Description} failed with exit code ${LASTEXITCODE}."
    }
}

function Convert-ToWslPath {
    param(
        [string] $WindowsPath,
        [string] $Description
    )

    $escapedWindowsPath = $WindowsPath.Replace('\', '\\')
    $output = & wsl.exe -d $Distro -- wslpath -a $escapedWindowsPath
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to convert ${Description} to a WSL path."
    }
    $path = ($output | Select-Object -First 1)
    if ([string]::IsNullOrWhiteSpace($path)) {
        throw "Failed to convert ${Description} to a WSL path."
    }
    $path
}

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw "WSL is required for Windows Rocky standalone acceptance. Install WSL or run scripts/dev/Run-RockyStandaloneAcceptance.sh on Linux."
}

$wslRepoRoot = Convert-ToWslPath -WindowsPath $RepoRoot.ProviderPath -Description "repository root"

$plainEnvironmentNames = @(
    "ROCKY9_HOST",
    "ROCKY10_HOST",
    "ROCKY_SSH_USER",
    "ROCKY_SSH_PRIVATE_KEY",
    "ROCKY_BECOME_PASSWORD",
    "ROCKY_SSH_KNOWN_HOSTS",
    "ROCKY_SSH_PORT",
    "ROCKY_ACCEPTANCE_MAX_AGE_HOURS",
    "ROCKY_ACCEPTANCE_SKIP_GALAXY",
    "PYTHON",
    "ACCEPTANCE_INVENTORY",
    "GITHUB_RUN_ID",
    "GITHUB_RUN_ATTEMPT"
)
$pathEnvironmentNames = @(
    "ROCKY_SSH_PRIVATE_KEY_FILE",
    "ROCKY_SSH_KNOWN_HOSTS_FILE",
    "ROCKY_ACCEPTANCE_SSH_DIR"
)

$previousWslEnv = $env:WSLENV
try {
    $wslEnvEntries = @()
    if (-not [string]::IsNullOrWhiteSpace($previousWslEnv)) {
        $wslEnvEntries += $previousWslEnv -split ":" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    }
    $wslEnvEntries += $plainEnvironmentNames
    $wslEnvEntries += $pathEnvironmentNames | ForEach-Object { "${_}/p" }
    $env:WSLENV = ($wslEnvEntries | Select-Object -Unique) -join ":"

    $arguments = @(
        "-d", $Distro,
        "--cd", $wslRepoRoot,
        "--",
        "bash",
        "scripts/dev/Run-RockyStandaloneAcceptance.sh"
    )
    if ($SelfTest) {
        $arguments += "--self-test"
    }

    Invoke-NativeChecked -Arguments $arguments -Description "Rocky standalone acceptance in WSL"
}
finally {
    $env:WSLENV = $previousWslEnv
}
