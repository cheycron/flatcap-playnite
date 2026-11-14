# QA driver for one theme and one view, run on the Windows machine against a SEPARATE portable Playnite copy.
# It never touches an installed Playnite: it only stops processes whose image lives under $Root, and the portable copy has its own
# named-pipe endpoint (Common.config) so the single-instance mechanism cannot reach another Playnite.
# usage: qa-run.ps1 -Root <qa dir> -Theme Slate|Daylight|Default -View Details|Grid -Name desktop-slate-grid [-Upload http://host:port]
param([string]$Root, [string]$Theme, [string]$View, [string]$Name, [string]$Upload = '')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$app = Join-Path $Root 'app'
$themeId = if ($Theme -eq 'Default') { 'Playnite_builtin_DefaultDesktop' } else { "Flatcap_${Theme}_Desktop" }

Get-Process Playnite.DesktopApp, Playnite.BrowserProcess -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$Root\*" } | ForEach-Object { Stop-Process -Id $_.Id -Force }
Start-Sleep 3

# install the package exactly as built: a .pthm is a ZIP whose root holds theme.yaml
$dst = Join-Path $app "Themes\Desktop\$themeId"
if ($Theme -ne 'Default') {
    Remove-Item $dst -Recurse -Force -ErrorAction SilentlyContinue
    [IO.Compression.ZipFile]::ExtractToDirectory((Join-Path $Root "${themeId}_2_0_0.pthm"), $dst)
}

# settings of the portable copy only
$cfgPath = Join-Path $app 'config.json'
$cfg = Get-Content $cfgPath -Raw
$cfg = [regex]::Replace($cfg, '"Theme":\s*"[^"]*"', "`"Theme`": `"$themeId`"")
$cfg = [regex]::Replace($cfg, '"ShowElevatedRightsWarning":\s*(true|false)', '"ShowElevatedRightsWarning": false')
$cfg = [regex]::Replace($cfg, '"GamesViewType":\s*\d+', "`"GamesViewType`": $(if ($View -eq 'Grid') { 1 } else { 0 })")
[IO.File]::WriteAllText($cfgPath, $cfg)

$p = Start-Process (Join-Path $app 'Playnite.DesktopApp.exe') -ArgumentList '--masterinstance', '--nolibupdate', '--hidesplashscreen' -WorkingDirectory $app -PassThru
Start-Sleep 14
$shots = Join-Path $Root 'shots'
New-Item -ItemType Directory -Force $shots | Out-Null
Remove-Item "$shots\$Name*.png" -Force -ErrorAction SilentlyContinue
& (Join-Path $Root 'winshot.ps1') -ProcessId $p.Id -OutDir $shots -Resize 1440x900 -Prefix $Name
$log = Get-Content (Join-Path $app 'playnite.log') -Tail 400
"errors/warnings mentioning theme or XAML since start:"
$log | Where-Object { $_ -match '\|(ERROR|FATAL)\|' -or $_ -match 'theme|xaml|Xaml' } | Select-Object -Last 6 | ForEach-Object { $_.Substring(0, [Math]::Min(220, $_.Length)) }
if ($Upload) {
    Get-ChildItem "$shots\$Name*.png" | ForEach-Object { Invoke-WebRequest -Method Put -InFile $_.FullName -Uri "$Upload/$($_.Name)" -UseBasicParsing | Out-Null; "uploaded $($_.Name)" }
}
