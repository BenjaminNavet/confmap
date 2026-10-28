# Crée un raccourci « confmap » dans le menu Démarrer (touche Windows → « confmap »).
$Launcher = Join-Path $PSScriptRoot "confmap.ps1"
$Programs = [Environment]::GetFolderPath("Programs")
$Shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $Programs "confmap.lnk"))
$Shortcut.TargetPath = "powershell.exe"
$Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Launcher`""
$Shortcut.WorkingDirectory = Split-Path -Parent $PSScriptRoot
$Shortcut.Save()
Write-Host "Installé : $Programs\confmap.lnk (menu Démarrer → « confmap »)"
