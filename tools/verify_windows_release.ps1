# Read-only package verification. Does not start the app, elevate, or change settings.
# Compatible with Windows PowerShell 5.1 and PowerShell 7.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ZipPath,
    [Parameter(Mandatory = $true)][string]$PackageDirectory,
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$ExpectedZipSha256,
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-fA-F0-9]{40}$')][string]$ExpectedSourceCommit,
    [Parameter(Mandatory = $true)][string]$ExpectedVersion,
    [Parameter(Mandatory = $true)][string]$OutputPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:OS -ne 'Windows_NT') { throw 'This helper requires Windows.' }
$archive = (Get-Item -LiteralPath $ZipPath).FullName
$package = (Get-Item -LiteralPath $PackageDirectory).FullName.TrimEnd('\', '/')
$prefix = $package + [IO.Path]::DirectorySeparatorChar
$reportPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputPath)
if (Test-Path -LiteralPath $reportPath) { throw 'Output already exists; use a new report path.' }
if ($reportPath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Write the report outside the verified package directory.'
}
$zipHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($zipHash -ne $ExpectedZipSha256) { throw 'ZIP SHA-256 mismatch.' }
# Anchor the extracted manifest to the already-verified ZIP, not to itself.
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::OpenRead($archive)
try {
    $entry = $zip.GetEntry('NetMonitor/FILE-MANIFEST.json')
    if ($null -eq $entry) { throw 'ZIP has no NetMonitor file manifest.' }
    $entryStream = $entry.Open()
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $manifestHash = [BitConverter]::ToString($sha.ComputeHash($entryStream)).Replace('-', '') }
    finally { $sha.Dispose(); $entryStream.Dispose() }
} finally { $zip.Dispose() }
$manifestPath = Join-Path $package 'FILE-MANIFEST.json'
if ((Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash -ne $manifestHash) {
    throw 'Extracted manifest differs from the verified ZIP.'
}
$build = Get-Content -LiteralPath (Join-Path $package 'BUILD-INFO.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($build.version -ne $ExpectedVersion -or $build.source_commit -ne $ExpectedSourceCommit) {
    throw 'BUILD-INFO version or source commit mismatch.'
}
if ($build.source_inputs_dirty -ne $false) { throw 'Build source inputs were not clean.' }
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$entries = @($manifest.PSObject.Properties)
if ($entries.Count -eq 0) { throw 'Empty file manifest.' }
$expectedFiles = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
[void]$expectedFiles.Add('FILE-MANIFEST.json')
foreach ($entry in $entries) {
    $relative = $entry.Name.Replace('/', '\')
    $full = [IO.Path]::GetFullPath((Join-Path $package $relative))
    if ([IO.Path]::IsPathRooted($relative) -or -not $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Manifest path escapes the package.'
    }
    if (-not $expectedFiles.Add($relative)) { throw 'Duplicate manifest path.' }
    $file = Get-Item -LiteralPath $full
    if ($file.PSIsContainer -or $file.Length -ne $entry.Value.bytes) { throw "File size mismatch: $relative" }
    if ((Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash -ne $entry.Value.sha256) {
        throw "File SHA-256 mismatch: $relative"
    }
}
$actualFiles = @(Get-ChildItem -LiteralPath $package -File -Recurse -Force)
foreach ($file in $actualFiles) {
    if (-not $expectedFiles.Contains($file.FullName.Substring($prefix.Length))) {
        throw 'Unexpected file in the package; use a fresh extraction.'
    }
}
if ($actualFiles.Count -ne $expectedFiles.Count) { throw 'Package file count mismatch.' }
$exe = Join-Path $package 'NetMonitor.exe'
$signature = Get-AuthenticodeSignature -LiteralPath $exe
$system = Get-CimInstance -ClassName Win32_OperatingSystem
Add-Type -AssemblyName System.Windows.Forms
$displays = @([Windows.Forms.Screen]::AllScreens | ForEach-Object {
    [ordered]@{ primary = $_.Primary; x = $_.Bounds.X; y = $_.Bounds.Y;
        width = $_.Bounds.Width; height = $_.Bounds.Height }
})
$report = [ordered]@{
    schema_version = 1
    at_utc = [DateTime]::UtcNow.ToString('o')
    package_verified = $true
    version = $build.version
    source_commit = $build.source_commit
    channel = $build.status
    zip_sha256 = $zipHash
    zip_bytes = (Get-Item -LiteralPath $archive).Length
    manifest_entries_verified = $entries.Count
    package_file_count = $actualFiles.Count
    exe_sha256 = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
    authenticode_status = [string]$signature.Status
    windows = [ordered]@{ caption = $system.Caption; version = $system.Version; architecture = $system.OSArchitecture }
    powershell_version = $PSVersionTable.PSVersion.ToString()
    screens_reported_by_winforms = $displays
    screen_note = 'Session-visible WinForms coordinates; enter per-display scaling and physical/VM/RDP context manually.'
    clean_machine_verified = $false
    app_started_by_this_script = $false
    native_etw_verified = $false
    physical_multi_monitor_verified = $false
}
$json = $report | ConvertTo-Json -Depth 8
$stream = [IO.File]::Open($reportPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
try {
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($json + [Environment]::NewLine)
    $stream.Write($bytes, 0, $bytes.Length)
} finally { $stream.Dispose() }
Write-Output "Verified $($entries.Count) manifest entries; report written to the requested output path."
