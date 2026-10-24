param([switch]$NoPause)
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
try {
$installRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$allowedRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs\Arar'))
if ($installRoot -ne $allowedRoot) { throw 'Beklenmeyen kurulum konumu. Kaldırma durduruldu.' }
$manifestPath = Join-Path $installRoot 'installed_files.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.product -ne 'Arar') { throw 'Arar kurulum kaydı bulunamadı.' }
$runtimeDll = Join-Path $installRoot 'runtime\python312.dll'
if (Test-Path -LiteralPath $runtimeDll) {
    try {
        $probe = [IO.File]::Open($runtimeDll, 'Open', 'ReadWrite', 'None')
        $probe.Dispose()
    } catch {
        throw 'Arar şu anda çalışıyor. Uygulamayı kapatıp kaldırmayı yeniden deneyin.'
    }
}
# Delete only files shipped by this package; settings, input PDFs and archives stay.
foreach ($relative in $manifest.files) {
    $target = [IO.Path]::GetFullPath((Join-Path $installRoot $relative))
    if (-not $target.StartsWith($installRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Geçersiz kaldırma yolu.'
    }
    if (Test-Path -LiteralPath $target -PathType Leaf) { Remove-Item -LiteralPath $target }
}
foreach ($link in @((Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) 'Arar.lnk'),
                    (Join-Path ([Environment]::GetFolderPath('Programs')) 'Arar\Arar.lnk'))) {
    if (Test-Path -LiteralPath $link) {
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($link)
        if ($shortcut.TargetPath.StartsWith($installRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $link
        }
    }
}
$registryPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Arar'
$registryEntry = Get-ItemProperty -LiteralPath $registryPath -ErrorAction SilentlyContinue
if ($registryEntry -and $registryEntry.InstallLocation -eq $installRoot) {
    Remove-Item -LiteralPath $registryPath
}
Remove-Item -LiteralPath $manifestPath
Remove-Item -LiteralPath (Join-Path $installRoot 'install.lock') -ErrorAction SilentlyContinue
Write-Host 'Arar kaldırıldı. Ayarlar ve belgeler korundu:' $installRoot
} catch {
    Write-Host ('Kaldırma tamamlanamadı: ' + $_.Exception.Message) -ForegroundColor Red
    if (-not $NoPause) { Read-Host 'Kapatmak için Enter tuşuna basın' }
    exit 1
}
if (-not $NoPause) { Read-Host 'Kapatmak için Enter tuşuna basın' }
