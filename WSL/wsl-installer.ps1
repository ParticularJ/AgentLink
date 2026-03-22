<#
.SYNOPSIS
    WSL Manager Script - Fixed filesystem wait hang issue and .wslconfig encoding
    新增：支持离线安装，使用 Ubuntu 官方云镜像（国内可访问）
    修复：添加 WSL/Hyper-V 服务预检查和自动修复
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

# ========== 新增：WSL 服务预检查和修复 ==========
function Test-AndRepair-WSLService {
    Write-Step "Checking WSL services..."

    $services = @("LxssManager", "vmcompute")
    $needsRestart = $false

    foreach ($svcName in $services) {
        try {
            $svc = Get-Service $svcName -ErrorAction SilentlyContinue
            if (-not $svc) {
                Write-Warn "$svcName service not found"
                continue
            }

            Write-Info "$svcName status: $($svc.Status)"

            if ($svc.Status -ne "Running") {
                Write-Warn "$svcName is not running, attempting to start..."
                try {
                    Start-Service $svcName -ErrorAction Stop
                    Start-Sleep -Seconds 2
                    $svc = Get-Service $svcName
                    if ($svc.Status -eq "Running") {
                        Write-Ok "$svcName started successfully"
                    } else {
                        Write-Err "Failed to start $svcName"
                        $needsRestart = $true
                    }
                } catch {
                    Write-Err "Cannot start ${svcName}: $_"
                    $needsRestart = $true
                }
            } else {
                Write-Ok "$svcName is running"
            }
        } catch {
            Write-Err "Error checking $svcName`: $_"
        }
    }

    # 检查 WSL 是否响应
    Write-Info "Testing WSL responsiveness..."
    $wslTest = wsl --version 2>&1
    if ($LASTEXITCODE -ne 0 -or $wslTest -match "HCS_E_SERVICE_NOT_AVAILABLE|service is not available") {
        Write-Warn "WSL is not responding properly"
        $needsRestart = $true
    } else {
        Write-Ok "WSL is responsive"
    }

    if ($needsRestart) {
        Write-Warn "WSL services need to be reset"
        Write-Info "Attempting WSL shutdown and service restart..."

        # 尝试修复
        wsl --shutdown 2>$null
        Start-Sleep -Seconds 2

        # 重启 LxssManager
        try {
            Restart-Service LxssManager -Force -ErrorAction Stop
            Start-Sleep -Seconds 3
            Write-Ok "LxssManager restarted"
        } catch {
            Write-Err "Failed to restart LxssManager: $_"
            Write-Warn "You may need to restart your computer"
            return $false
        }

        # 再次测试
        $wslTest2 = wsl --version 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Err "WSL still not responding after service restart"
            return $false
        }
    }

    return $true
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

    $configContent = @"
[wsl2]
networkingMode=mirrored
autoProxy=true
dnsTunneling=true
firewall=true
"@

    try {
        if (Test-Path $wslConfigPath) {
            $backupPath = "$wslConfigPath.backup.$(Get-Date -Format 'yyyyMMddHHmmss')"
            Copy-Item $wslConfigPath $backupPath -Force -ErrorAction Stop
            Write-Ok "Backup created at $backupPath"
        }

        [System.IO.File]::WriteAllText($wslConfigPath, $configContent, [System.Text.Encoding]::ASCII)
        Write-Ok ".wslconfig created with ASCII encoding (no BOM)"
        Write-Warn "Please run 'wsl --shutdown' and restart WSL to apply network changes"

    } catch {
        Write-Err "Failed to write .wslconfig: $_"
    }
}

# ========== 新增：离线安装函数（使用 Ubuntu 官方云镜像，国内可访问） ==========
function Install-WSL-Offline {
    param([string]$Distro)

    Write-Step "Preparing offline installation for $Distro..."

    $distroUrls = @{
        "Ubuntu-24.04" = "https://cloud-images.ubuntu.com/wsl/releases/24.04/current/ubuntu-noble-wsl-amd64-24.04lts.rootfs.tar.gz"
        "Ubuntu-22.04" = "https://cloud-images.ubuntu.com/wsl/jammy/current/ubuntu-jammy-wsl-amd64-ubuntu22.04lts.rootfs.tar.gz"
        "Ubuntu-20.04" = "https://cloud-images.ubuntu.com/wsl/releases/20.04/current/ubuntu-focal-wsl-amd64-ubuntu20.04lts.rootfs.tar.gz"
        "Ubuntu"       = "https://cloud-images.ubuntu.com/wsl/releases/24.04/current/ubuntu-noble-wsl-amd64-24.04lts.rootfs.tar.gz"
    }

    $mirrorUrls = @{
        "Ubuntu-24.04" = "https://mirrors.ustc.edu.cn/ubuntu-cloud-images/wsl/releases/24.04/current/ubuntu-noble-wsl-amd64-24.04lts.rootfs.tar.gz"
        "Ubuntu-22.04" = "https://mirrors.ustc.edu.cn/ubuntu-cloud-images/wsl/jammy/current/ubuntu-jammy-wsl-amd64-ubuntu22.04lts.rootfs.tar.gz"
        "Ubuntu-20.04" = "https://mirrors.ustc.edu.cn/ubuntu-cloud-images/wsl/releases/20.04/current/ubuntu-focal-wsl-amd64-ubuntu20.04lts.rootfs.tar.gz"
        "Ubuntu"       = "https://mirrors.ustc.edu.cn/ubuntu-cloud-images/wsl/releases/24.04/current/ubuntu-noble-wsl-amd64-24.04lts.rootfs.tar.gz"
    }

    $url = $distroUrls[$Distro]
    if (-not $url) {
        Write-Warn "Unknown distro: $Distro, defaulting to Ubuntu-24.04"
        $url = $distroUrls["Ubuntu-24.04"]
    }

    $tempFile = "$env:TEMP\wsl-$Distro-rootfs.tar.gz"

    # 尝试下载（主源 + 镜像源）
    $downloadSuccess = $false
    foreach ($source in @($url, $mirrorUrls[$Distro])) {
        if (-not $source) { continue }

        try {
            Write-Info "Trying download from: $source"

            $job = Start-Job {
                param($uri, $out)
                try {
                    Invoke-WebRequest -Uri $uri -OutFile $out -UseBasicParsing -MaximumRedirection 5
                    return $true
                } catch {
                    return $false
                }
            } -ArgumentList $source, $tempFile

            Write-Info "Downloading... (timeout: 120s)"
            $jobResult = Wait-Job $job -Timeout 120

            if ($jobResult) {
                $downloadResult = Receive-Job $job
                Remove-Job $job

                if ($downloadResult -and (Test-Path $tempFile)) {
                    $fileSize = (Get-Item $tempFile).Length
                    if ($fileSize -gt 100MB) {
                        $downloadSuccess = $true
                        Write-Ok "Downloaded: $([math]::Round($fileSize / 1MB, 2)) MB"
                        break
                    } else {
                        Write-Warn "Downloaded file too small ($fileSize bytes), trying next source..."
                        Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
                    }
                }
            } else {
                Stop-Job $job
                Remove-Job $job -Force
                Write-Warn "Download timeout, trying next source..."
            }
        } catch {
            Write-Warn "Download failed: $_"
        }
    }

    if (-not $downloadSuccess) {
        Write-Err "All download sources failed"
        Write-Info "Please manually download the rootfs file from:"
        Write-Info "  https://cloud-images.ubuntu.com/wsl/"
        Write-Info "Then run: wsl --import $Distro <install-path> <downloaded-file> --version 2"
        return $false
    }

    # 导入到 WSL - 修复：添加重试机制和错误处理
    $maxImportAttempts = 3
    $importSuccess = $false

    for ($attempt = 1; $attempt -le $maxImportAttempts; $attempt++) {
        try {
            Write-Step "Importing to WSL (attempt $attempt/$maxImportAttempts)..."

            # 修复：先确保 WSL 服务可用
            if (-not (Test-AndRepair-WSLService)) {
                Write-Warn "WSL service not available, waiting..."
                Start-Sleep -Seconds 5
                continue
            }

            $installPath = "$env:LOCALAPPDATA\Packages\WSL\$Distro"
            if (-not (Test-Path $installPath)) {
                New-Item -ItemType Directory -Path $installPath -Force | Out-Null
            }

            Write-Info "Importing to: $installPath"

            # 修复：使用 Start-Process 捕获详细输出
            $psi = New-Object System.Diagnostics.ProcessStartInfo
            $psi.FileName = "wsl.exe"
            $psi.Arguments = "--import `"$Distro`" `"$installPath`" `"$tempFile`" --version 2"
            $psi.RedirectStandardError = $true
            $psi.RedirectStandardOutput = $true
            $psi.UseShellExecute = $false
            $psi.CreateNoWindow = $true

            $process = [System.Diagnostics.Process]::Start($psi)
            $stdout = $process.StandardOutput.ReadToEnd()
            $stderr = $process.StandardError.ReadToEnd()
            $process.WaitForExit()

            $importOutput = $stdout + $stderr

            if ($process.ExitCode -ne 0) {
                # 修复：检测特定错误并提供解决方案
                if ($importOutput -match "HCS_E_SERVICE_NOT_AVAILABLE|service not available") {
                    Write-Warn "Hyper-V Container Service unavailable"
                    Write-Info "Attempting to repair WSL service..."
                    Test-AndRepair-WSLService
                    Start-Sleep -Seconds 3
                    continue  # 重试
                }
                throw "WSL import failed with exit code $($process.ExitCode): $importOutput"
            }

            # 验证导入是否成功
            Start-Sleep -Seconds 2
            $checkDistro = wsl --list --quiet 2>$null | Where-Object { $_ -eq $Distro }
            if ($checkDistro) {
                $importSuccess = $true
                break
            } else {
                throw "Import appeared to succeed but distro not found in list"
            }

        } catch {
            Write-Err "Import attempt $attempt failed: $_"
            if ($attempt -lt $maxImportAttempts) {
                Write-Info "Waiting 5 seconds before retry..."
                Start-Sleep -Seconds 5
            }
        }
    }

    if ($importSuccess) {
        Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
        Write-Ok "Offline installation completed successfully"
        return $true
    } else {
        Write-Err "All import attempts failed"
        Write-Info "Rootfs file preserved at: $tempFile"
        Write-Info "You can manually import with:"
        Write-Info "  wsl --import $Distro <path> `"$tempFile`" --version 2"
        return $false
    }
}

# ========== Install with better error handling ==========
function Install-WSL {
    Write-Host "=== WSL Installation ===" -ForegroundColor Cyan

    # 修复：先检查并修复 WSL 服务
    if (-not (Test-AndRepair-WSLService)) {
        Write-Err "WSL services are not available"
        Write-Host "`nTroubleshooting:" -ForegroundColor Yellow
        Write-Host "  1. Ensure virtualization is enabled in BIOS (Intel VT-x / AMD-V)" -ForegroundColor White
        Write-Host "  2. Run: wsl --update" -ForegroundColor White
        Write-Host "  3. Restart your computer" -ForegroundColor White
        Write-Host "  4. If problem persists, try: dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all" -ForegroundColor White
        return
    }

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
        Write-Ok "WSL2 set as default"
    } catch {
        Write-Warn "WSL2 default setting error: $_"
    }

    # 修改：添加错误处理的 wsl --update
    try {
        $updateOutput = wsl --update 2>&1
        if ($LASTEXITCODE -ne 0 -or $updateOutput -match "无法与服务器建立连接|WININET_E_CANNOT_CONNECT|cannot connect|failed") {
            Write-Warn "WSL update failed (network issue, continuing...)"
            Write-Info "This is normal in restricted network environments"
        } else {
            Write-Ok "WSL kernel updated"
        }
    } catch {
        Write-Warn "WSL update error: $_"
        Write-Info "Continuing installation..."
    }
    Write-Ok "WSL2 configured"

    # 3. Install distro（修改为支持离线安装）
    if (-not $existing) {
        Write-Step "Installing $Distro..."
        Write-Info "This may take 5-10 minutes..."

        # 尝试在线安装（短时间检测），失败则转离线安装
        $installSuccess = $false
        $useOffline = $false

        try {
            Write-Info "Attempting online installation (Microsoft Store)..."
            Write-Info "Waiting 60 seconds to detect if store is accessible..."

            $proc = Start-Process -FilePath "wsl.exe" -ArgumentList "--install", "-d", $Distro, "--no-launch" -PassThru -WindowStyle Normal

            # 等待最多 60 秒检测安装进度
            $timer = 0
            $installDetected = $false
            while (-not $proc.HasExited -and $timer -lt 60) {
                Start-Sleep -Seconds 5
                $timer += 5

                # 检查是否已安装
                if (Test-DistroInstalled $Distro) {
                    $installDetected = $true
                    Write-Ok "Online installation detected"
                    break
                }

                # 每 30 秒显示进度
                if ($timer % 30 -eq 0) {
                    Write-Host "    ... waited $timer seconds" -ForegroundColor Gray
                }
            }

            # 根据检测结果决定后续操作
            if ($installDetected) {
                # 等待安装完成（最多再等待 5 分钟）
                Write-Info "Waiting for installation to complete..."
                $completionTimer = 0
                while (-not (Test-WSLResponsive $Distro 3) -and $completionTimer -lt 300) {
                    Start-Sleep -Seconds 10
                    $completionTimer += 10
                    if ($completionTimer % 60 -eq 0) {
                        Write-Host "    ... configuring for $completionTimer seconds" -ForegroundColor Gray
                    }
                }

                if (Test-DistroInstalled $Distro) {
                    $installSuccess = $true
                    Write-Ok "$Distro installed via Microsoft Store"
                }

                # 确保进程结束
                if (-not $proc.HasExited) {
                    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
                }
            } else {
                # 60秒内没有检测到安装，判定为网络问题
                if (-not $proc.HasExited) {
                    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
                }
                Write-Warn "Microsoft Store installation appears blocked (network issue)"
                $useOffline = $true
            }

        } catch {
            Write-Warn "Online installation error: $_"
            $useOffline = $true
        }

        # 如果在线安装失败，使用离线安装
        if (-not $installSuccess -and $useOffline) {
            Write-Info "Switching to offline installation method..."
            $installSuccess = Install-WSL-Offline -Distro $Distro
        }

        # 最终检查
        if (-not $installSuccess) {
            Write-Err "Failed to install $Distro"
            Write-Host "`nTroubleshooting:" -ForegroundColor Yellow
            Write-Host "  1. Check internet connection" -ForegroundColor White
            Write-Host "  2. Manual download: https://cloud-images.ubuntu.com/wsl/" -ForegroundColor White
            Write-Host "  3. Manual import: wsl --import $Distro <path> <rootfs.tar.gz> --version 2" -ForegroundColor White
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
            wsl -d $distroName -u root -- bash -c 'printf "[user]
default=root
" > /etc/wsl.conf'
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
        $updateOutput = wsl --update 2>&1
        if ($LASTEXITCODE -ne 0 -or $updateOutput -match "无法与服务器建立连接|WININET_E_CANNOT_CONNECT|cannot connect") {
            Write-Warn "WSL update failed due to network issues"
            Write-Info "You can manually download the update from:"
            Write-Info "  https://github.com/microsoft/WSL/releases"
        } else {
            Write-Ok "WSL kernel updated"
        }
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
