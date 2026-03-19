<#
.SYNOPSIS
    WSL Manager Script - Fixed filesystem wait hang issue and .wslconfig encoding
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true, Position=0)]
    [ValidateSet("install", "uninstall", "update")]
    [string]$Action,

    [Parameter()]
    [string]$Distro = "",

    [Parameter()]
    [ValidateSet("LTS", "Latest", "")]
    [string]$UbuntuVersion = "LTS",

    [Parameter()]
    [switch]$All,

    [Parameter()]
    [switch]$Force
)

# Auto elevate
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Requesting administrator privileges..." -ForegroundColor Yellow
    $scriptPath = $MyInvocation.MyCommand.Path
    $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -Action $Action"
    if ($Distro) { $arguments += " -Distro `"$Distro`"" }
    if ($UbuntuVersion -and -not $Distro) { $arguments += " -UbuntuVersion `"$UbuntuVersion`"" }
    if ($All) { $arguments += " -All" }
    if ($Force) { $arguments += " -Force" }
    Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -Verb RunAs
    exit
}

# Utility functions
function Write-Step($msg) { Write-Host "`n[Step] $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg) { Write-Host "  [ERR] $msg" -ForegroundColor Red }
function Write-Info($msg) { Write-Host "  [INFO] $msg" -ForegroundColor White }

function Get-UbuntuVersions {
    try {
        $onlineList = wsl --list --online 2>$null | Select-String "Ubuntu"
        $versions = foreach ($line in $onlineList) {
            if ($line -match "(Ubuntu-?[\d\.]*)") { $matches[1] }
        }
        return $versions | Where-Object { $_ } | Sort-Object -Unique
    } catch {
        return @("Ubuntu-24.04", "Ubuntu-22.04", "Ubuntu-20.04", "Ubuntu")
    }
}

function Get-VersionNumber($ver) {
    if ($ver -match "(\d+)\.(\d+)") { return [int]$matches[1] * 100 + [int]$matches[2] }
    return 0
}

function Select-UbuntuVersion($versions, $strategy) {
    $sorted = $versions | Where-Object { $_ -match "Ubuntu-?(\d+\.\d+)" } | ForEach-Object {
        [PSCustomObject]@{ Name = $_; Ver = Get-VersionNumber $_; IsLTS = ($_ -match "\d+\.04") }
    } | Sort-Object Ver -Descending

    switch ($strategy) {
        "LTS" { 
            $lts = $sorted | Where-Object { $_.IsLTS } | Select-Object -First 1
            if ($lts) { return $lts.Name }
            return "Ubuntu-24.04"
        }
        "Latest" { 
            if ($sorted) { return $sorted[0].Name }
            return "Ubuntu"
        }
        default { 
            $lts = $sorted | Where-Object { $_.IsLTS } | Select-Object -First 1
            if ($lts) { return $lts.Name }
            return "Ubuntu-24.04"
        }
    }
}

function Get-InstalledDistros {
    return wsl --list --quiet 2>$null | Where-Object { $_ -and $_ -notmatch "Windows Subsystem for Linux" } | ForEach-Object { $_.Trim() }
}

function Test-DistroInstalled($name) {
    if ([string]::IsNullOrWhiteSpace($name)) { return $false }
    return (Get-InstalledDistros) -contains $name
}

# ========== Test WSL Responsiveness ==========
function Test-WSLResponsive($distroName, $timeoutSeconds = 5) {
    $job = Start-Job -ScriptBlock {
        param($distro)
        try {
            $result = wsl -d $distro -- echo "ready" 2>&1
            return ($result -eq "ready")
        } catch {
            return $false
        }
    } -ArgumentList $distroName
    
    $jobResult = Wait-Job $job -Timeout $timeoutSeconds
    if ($jobResult) {
        $output = Receive-Job $job
        Remove-Job $job -ErrorAction SilentlyContinue
        return $output
    } else {
        Stop-Job $job -ErrorAction SilentlyContinue
        Remove-Job $job -Force -ErrorAction SilentlyContinue
        return $false
    }
}

# ========== Configure WSL Global Network ==========
function Configure-WSLGlobalNetwork {
    Write-Step "Configure WSL Global Network..."
    
    $wslConfigPath = "$env:USERPROFILE\.wslconfig"
    
    $existingConfig = ""
    if (Test-Path $wslConfigPath) {
        try {
            $existingConfig = Get-Content $wslConfigPath -Raw -ErrorAction Stop
        } catch {
            Write-Warn "Cannot read existing .wslconfig: $_"
        }
    }
    
    if ($existingConfig -match "networkingMode\s*=\s*mirrored") {
        Write-Ok "WSL already configured with mirrored networking mode"
        return
    }
    
    # 修复：使用简单的 ASCII 编码，避免 UTF-8 BOM 问题
    # 修复：使用保守的配置值，确保兼容性
    $configContent = @"
[wsl2]
networkingMode=mirrored
autoProxy=true
dnsTunneling=true
firewall=true
"@
    
    # 注意：移除了 autoMemoryReclaim=gradual，因为它需要 WSL 2.0.0+
    # 旧版本 WSL 不支持这个值会导致 "键未知" 错误
    
    try {
        if (Test-Path $wslConfigPath) {
            $backupPath = "$wslConfigPath.backup.$(Get-Date -Format 'yyyyMMddHHmmss')"
            Copy-Item $wslConfigPath $backupPath -Force -ErrorAction Stop
            Write-Ok "Backup created at $backupPath"
        }
        
        # 修复：使用 ASCII 编码并确保没有 BOM
        [System.IO.File]::WriteAllText($wslConfigPath, $configContent, [System.Text.Encoding]::ASCII)
        Write-Ok ".wslconfig created with ASCII encoding (no BOM)"
        Write-Warn "Please run 'wsl --shutdown' and restart WSL to apply network changes"
        
    } catch {
        Write-Err "Failed to write .wslconfig: $_"
    }
}

# ========== Install with better error handling ==========
function Install-WSL {
    Write-Host "=== WSL Installation ===" -ForegroundColor Cyan
    
    Configure-WSLGlobalNetwork
    
    if ([string]::IsNullOrWhiteSpace($Distro)) {
        Write-Step "Detecting available Ubuntu versions..."
        $available = Get-UbuntuVersions
        if ($available.Count -eq 0) {
            Write-Warn "No Ubuntu versions found, using defaults"
            $available = @("Ubuntu-24.04", "Ubuntu-22.04", "Ubuntu-20.04")
        }
        Write-Host "  Available: $($available -join ', ')" -ForegroundColor Gray
        $Distro = Select-UbuntuVersion $available $UbuntuVersion
        if ([string]::IsNullOrWhiteSpace($Distro)) {
            $Distro = "Ubuntu"
        }
        Write-Ok "Selected: $Distro (Strategy: $UbuntuVersion)"
    }

    # Check if exists
    $existing = Test-DistroInstalled $Distro
    if ($existing) {
        Write-Warn "$Distro is already installed"
        if (-not $Force) {
            $reinstall = Read-Host "Reinstall? This will delete all data! (yes/N)"
            if ($reinstall -ne "yes") { 
                Write-Host "Configuring existing system..." -ForegroundColor Yellow
                Configure-Distro $Distro
                return 
            }
        }
        Write-Step "Removing old installation..."
        wsl --terminate $Distro 2>$null
        wsl --unregister $Distro 2>$null
        Start-Sleep -Seconds 2
        $existing = $false
    }

    # 1. Enable features
    Write-Step "Enabling WSL features..."
    try {
        $dismOutput = dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart 2>&1
        if ($LASTEXITCODE -ne 0) { Write-Warn "WSL feature enable returned code: $LASTEXITCODE" }
        
        $dismOutput = dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart 2>&1
        if ($LASTEXITCODE -ne 0) { Write-Warn "VirtualMachinePlatform feature enable returned code: $LASTEXITCODE" }
    } catch {
        Write-Warn "Feature enable error: $_"
    }
    Write-Ok "WSL features enabled"

    # 2. Set WSL2 default
    Write-Step "Configuring WSL2..."
    try {
        wsl --set-default-version 2 2>$null
        wsl --update 2>$null
    } catch {
        Write-Warn "WSL2 config error: $_"
    }
    Write-Ok "WSL2 configured"

    # 3. Install distro
    if (-not $existing) {
        Write-Step "Installing $Distro..."
        Write-Info "This may take 5-10 minutes..."
        
        try {
            # Use --no-launch to avoid blocking
            $proc = Start-Process -FilePath "wsl.exe" -ArgumentList "--install", "-d", $Distro, "--no-launch" -Wait -PassThru -WindowStyle Normal -NoNewWindow
            
            if ($proc.ExitCode -ne 0) {
                Write-Warn "Install returned exit code $($proc.ExitCode)"
            }
            
            Write-Ok "Package installation initiated"
            
            # Wait for distro to appear
            Write-Info "Waiting for installation to complete..."
            $timeout = 600
            $timer = 0
            
            while (-not (Test-DistroInstalled $Distro) -and $timer -lt $timeout) {
                Start-Sleep -Seconds 5
                $timer += 5
                if ($timer % 30 -eq 0) {
                    Write-Host "    ... waited $timer seconds" -ForegroundColor Gray
                }
            }
            
            if (-not (Test-DistroInstalled $Distro)) {
                throw "Timeout waiting for installation after $timeout seconds"
            }
            
            Write-Ok "$Distro is installed"
            
        } catch {
            Write-Err "Error during install: $_"
            Write-Host "`nTroubleshooting:" -ForegroundColor Yellow
            Write-Host "  1. Check Windows Store is accessible" -ForegroundColor White
            Write-Host "  2. Try: wsl --install -d $Distro" -ForegroundColor White
            Write-Host "  3. Check Windows Update" -ForegroundColor White
            return
        }
    }

    # 4. Configure
    Configure-Distro $Distro
}

# ========== Configure distro with better wait logic ==========
function Configure-Distro($distroName) {
    Write-Step "Configuring $distroName..."

    if ([string]::IsNullOrWhiteSpace($distroName)) {
        $distroName = "Ubuntu"
    }

    # Better wait logic with timeout and progress display
    Write-Host "  Waiting for WSL to be responsive..." -ForegroundColor Gray
    Write-Info "This may take up to 30 seconds. Press Ctrl+C to cancel."
    
    $maxAttempts = 30
    $attempt = 0
    $ready = $false
    
    while ($attempt -lt $maxAttempts -and -not $ready) {
        $attempt++
        
        # Show progress every 5 attempts
        if ($attempt % 5 -eq 0) {
            Write-Host "    ... attempt $attempt of $maxAttempts" -ForegroundColor Gray
        }
        
        $ready = Test-WSLResponsive $distroName 3
        
        if (-not $ready) {
            Start-Sleep -Seconds 1
        }
    }
    
    if (-not $ready) {
        Write-Warn "WSL is not responding after $maxAttempts attempts"
        Write-Info "Trying to restart WSL..."
        wsl --terminate $distroName 2>$null
        Start-Sleep -Seconds 3
        
        # Try once more
        $ready = Test-WSLResponsive $distroName 5
        
        if (-not $ready) {
            Write-Err "WSL is still not responding"
            Write-Host "`nTroubleshooting steps:" -ForegroundColor Yellow
            Write-Host "  1. Run: wsl --shutdown" -ForegroundColor White
            Write-Host "  2. Run: wsl -d $distroName" -ForegroundColor White
            Write-Host "  3. If still stuck, restart computer" -ForegroundColor White
            return
        }
    }

    # Create wsl.conf
    Write-Host "  Creating wsl.conf..." -ForegroundColor Gray
    
    $configContent = @"
[boot]
systemd=true

[user]
default=root
"@
    
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($configContent)
    $base64 = [Convert]::ToBase64String($bytes)
    
    try {
        $result = wsl -d $distroName -u root -- bash -c "echo '$base64' | base64 -d > /etc/wsl.conf && chmod 644 /etc/wsl.conf" 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "wsl.conf created"
        } else {
            throw $result
        }
    } catch {
        Write-Warn "Failed to create wsl.conf: $_"
        Write-Info "Trying minimal config..."
        try {
            wsl -d $distroName -u root -- bash -c 'printf "[user]\ndefault=root\n" > /etc/wsl.conf'
            if ($LASTEXITCODE -eq 0) {
                Write-Ok "Minimal wsl.conf created"
            }
        } catch {
            Write-Err "Failed to create wsl.conf"
        }
    }

    # Restart
    Write-Host "  Restarting WSL..." -ForegroundColor Gray
    wsl --terminate $distroName 2>$null
    Start-Sleep -Seconds 3

    # Create user
    $defaultName = $env:USERNAME
    $username = Read-Host "`nEnter Linux username (empty for '$defaultName')"
    if ([string]::IsNullOrWhiteSpace($username)) { $username = $defaultName }
    
    # Sanitize username
    $username = $username -replace '[^\w\-]', ''
    if ([string]::IsNullOrWhiteSpace($username)) { $username = "user" }

    Write-Host "Creating user '$username'..." -ForegroundColor Yellow
    
    try {
        wsl -d $distroName -u root -- useradd -m -G sudo -s /bin/bash $username 2>$null
        wsl -d $distroName -u root -- bash -c "echo '$username ALL=(ALL:ALL) NOPASSWD: ALL' > /etc/sudoers.d/$username && chmod 440 /etc/sudoers.d/$username"
        
        Write-Host "Set password for ${username}:" -ForegroundColor Yellow
        wsl -d $distroName -u root -- passwd $username
        
        # Update wsl.conf with user
        $updateConfig = @"
[boot]
systemd=true

[user]
default=$username
"@
        $bytes2 = [System.Text.Encoding]::UTF8.GetBytes($updateConfig)
        $base642 = [Convert]::ToBase64String($bytes2)
        wsl -d $distroName -u root -- bash -c "echo '$base642' | base64 -d > /etc/wsl.conf"
        
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "Failed to update wsl.conf with user"
        }
        
        wsl --terminate $distroName 2>$null
        
        Write-Ok "Configuration complete, default user: $username"
        
        Write-Host "`n========================================" -ForegroundColor Green
        Write-Host "  Installation Complete!" -ForegroundColor Green
        Write-Host "========================================" -ForegroundColor Green
        Write-Host "`nNetwork:" -ForegroundColor Cyan
        Write-Host "  - Windows localhost: 127.0.0.1" -ForegroundColor White
        Write-Host "  - WSL localhost: 127.0.0.1 (shared)" -ForegroundColor White
        Write-Host "`nCommands:" -ForegroundColor Cyan
        Write-Host "  Start: wsl -d $distroName" -ForegroundColor White
        Write-Host "  Test:  wsl -d $distroName -e curl -I http://127.0.0.1" -ForegroundColor White
        
        $startNow = Read-Host "`nPress Enter to start $distroName (or type 'n' to skip)"
        if ($startNow -ne "n") {
            wsl -d $distroName
        }
    } catch {
        Write-Err "Error configuring user: $_"
    }
}

# ========== UNINSTALL ==========
function Uninstall-WSL {
    Write-Host "=== WSL Uninstall ===" -ForegroundColor Cyan

    if ($All) {
        Write-Step "Complete WSL uninstall..."
        if (-not $Force) {
            $confirm = Read-Host "Delete all WSL distros and configs? (yes/N)"
            if ($confirm -ne "yes") { return }
        }
        
        $installedDistros = Get-InstalledDistros
        if ($installedDistros.Count -gt 0) {
            $installedDistros | ForEach-Object {
                Write-Host "  Uninstalling $_..." -ForegroundColor Yellow
                wsl --unregister $_ 2>$null
            }
        }
        
        $wslConfigPath = "$env:USERPROFILE\.wslconfig"
        if (Test-Path $wslConfigPath) {
            $removeConfig = Read-Host "Remove .wslconfig? (y/N)"
            if ($removeConfig -eq "y") {
                Remove-Item $wslConfigPath -Force -ErrorAction SilentlyContinue
                Write-Ok ".wslconfig removed"
            }
        }
        
        Write-Step "Disabling WSL features..."
        dism.exe /online /disable-feature /featurename:Microsoft-Windows-Subsystem-Linux /norestart 2>$null
        dism.exe /online /disable-feature /featurename:VirtualMachinePlatform /norestart 2>$null
        Write-Ok "WSL completely uninstalled"
        
    } else {
        if ([string]::IsNullOrWhiteSpace($Distro)) {
            $installed = Get-InstalledDistros
            if ($installed.Count -eq 0) { 
                Write-Err "No distros installed"
                return 
            }
            
            Write-Host "`nInstalled distros:" -ForegroundColor Cyan
            for ($i = 0; $i -lt $installed.Count; $i++) { Write-Host "  [$i] $($installed[$i])" }
            
            $sel = Read-Host "Select number to uninstall (or type name)"
            if ($sel -match "^\d+$" -and [int]$sel -lt $installed.Count) {
                $Distro = $installed[[int]$sel]
            } elseif (-not [string]::IsNullOrWhiteSpace($sel)) {
                $Distro = $sel
            } else {
                Write-Err "Invalid selection"
                return
            }
        }

        if (Test-DistroInstalled $Distro) {
            Write-Step "Uninstalling $Distro..."
            wsl --terminate $Distro 2>$null
            wsl --unregister $Distro 2>$null
            Write-Ok "$Distro uninstalled"
        } else {
            Write-Err "$Distro is not installed"
        }
    }
}

# ========== UPDATE ==========
function Update-WSL {
    Write-Host "=== WSL Update ===" -ForegroundColor Cyan

    Write-Step "Updating WSL kernel..."
    try {
        wsl --update
        Write-Ok "WSL kernel updated"
    } catch {
        Write-Warn "WSL update failed: $_"
    }

    $wslConfigPath = "$env:USERPROFILE\.wslconfig"
    if (Test-Path $wslConfigPath) {
        $config = Get-Content $wslConfigPath -Raw -ErrorAction SilentlyContinue
        if (-not ($config -match "networkingMode\s*=\s*mirrored")) {
            Write-Warn "Mirrored networking not configured"
            $setupNetwork = Read-Host "Configure now? (y/N)"
            if ($setupNetwork -eq "y") {
                Configure-WSLGlobalNetwork
                Write-Warn "Run 'wsl --shutdown' to apply"
            }
        }
    } else {
        Write-Warn "No .wslconfig found"
        $setupNetwork = Read-Host "Configure mirrored networking? (y/N)"
        if ($setupNetwork -eq "y") {
            Configure-WSLGlobalNetwork
        }
    }

    $installed = Get-InstalledDistros | Where-Object { $_ -match "Ubuntu" }
    if ($installed.Count -eq 0) {
        Write-Warn "No Ubuntu distros detected"
        return
    }

    foreach ($distro in $installed) {
        Write-Step "Updating $distro..."
        try {
            if (Test-WSLResponsive $distro 3) {
                wsl -d $distro -u root -- bash -c "apt update && apt upgrade -y && apt autoremove -y" 2>$null
                Write-Ok "$distro updated"
            } else {
                Write-Warn "$distro is not responsive, skipping update"
            }
        } catch {
            Write-Warn "Failed to update ${distro}: $_"
        }
    }

    wsl --shutdown
    Write-Host "`n========================================" -ForegroundColor Green
    Write-Host "  Update Complete!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
}

# ========== MAIN ==========
try {
    switch ($Action) {
        "install" { Install-WSL }
        "uninstall" { Uninstall-WSL }
        "update" { Update-WSL }
    }
} catch {
    Write-Err "Unhandled error: $_"
    Write-Host "Stack trace: $($_.ScriptStackTrace)" -ForegroundColor Red
}

if ($Host.UI.RawUI) {
    Write-Host "`nPress any key to exit..." -ForegroundColor Gray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}