<#
.SYNOPSIS
    WSL 管理脚本 - 支持安装、卸载、更新
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

# 自动提权
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "正在请求管理员权限..." -ForegroundColor Yellow
    $scriptPath = $MyInvocation.MyCommand.Path
    $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" $Action"
    if ($Distro) { $arguments += " -Distro `"$Distro`"" }
    if ($UbuntuVersion -and -not $Distro) { $arguments += " -UbuntuVersion `"$UbuntuVersion`"" }
    if ($All) { $arguments += " -All" }
    if ($Force) { $arguments += " -Force" }
    Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -Verb RunAs
    exit
}

# 工具函数
function Write-Step($msg) { Write-Host "`n[步骤] $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "  ✓ $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  ! $msg" -ForegroundColor Yellow }
function Write-Err($msg) { Write-Host "  ✗ $msg" -ForegroundColor Red }

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
    return wsl --list --quiet 2>$null | Where-Object { $_ } | ForEach-Object { $_.Trim() }
}

function Test-DistroInstalled($name) {
    if ([string]::IsNullOrWhiteSpace($name)) { return $false }
    return (Get-InstalledDistros) -contains $name
}

# ========== INSTALL ==========
function Install-WSL {
    Write-Host "=== WSL 安装 ===" -ForegroundColor Cyan
    
    # 确定版本（确保不为空）
    if ([string]::IsNullOrWhiteSpace($Distro)) {
        Write-Step "检测可用 Ubuntu 版本..."
        $available = Get-UbuntuVersions
        Write-Host "  可用: $($available -join ', ')" -ForegroundColor Gray
        $Distro = Select-UbuntuVersion $available $UbuntuVersion
        if ([string]::IsNullOrWhiteSpace($Distro)) {
            $Distro = "Ubuntu"
        }
        Write-Ok "选择: $Distro (策略: $UbuntuVersion)"
    }

    # 检查是否已存在
    $existing = Test-DistroInstalled $Distro
    if ($existing) {
        Write-Warn "$Distro 已安装"
        if (-not $Force) {
            $reinstall = Read-Host "是否重新安装? 这将删除现有数据! (yes/N)"
            if ($reinstall -ne "yes") { 
                Write-Host "配置现有系统..." -ForegroundColor Yellow
                Configure-Distro $Distro
                return 
            }
            Write-Step "卸载旧版本..."
            wsl --terminate $Distro 2>$null
            wsl --unregister $Distro 2>$null
            $existing = $false
        }
    }

    # 1. 启用功能
    Write-Step "启用 WSL 功能..."
    dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart | Out-Null
    dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart | Out-Null
    Write-Ok "WSL 功能已启用"

    # 2. 设置默认 WSL2
    Write-Step "配置 WSL2..."
    wsl --set-default-version 2 2>$null
    wsl --update 2>$null
    Write-Ok "WSL2 配置完成"

    # 3. 安装发行版
    Write-Step "安装 $Distro..."
    
    if (-not $existing) {
        # 使用字符串拼接而不是数组，避免 null 问题
        $wslPath = (Get-Command wsl.exe).Source
        if (-not $wslPath) { $wslPath = "wsl.exe" }
        
        # 构建参数（确保无 null）
        $arguments = "--install"
        if ($Distro -and $Distro -ne "Ubuntu") {
            $arguments += " -d $Distro"
        }
        
        Write-Host "  执行: wsl $arguments" -ForegroundColor Gray
        
        # 使用 cmd /c 执行，避免 PowerShell 参数解析问题
        $cmd = "`"$wslPath`" $arguments"
        $proc = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $cmd -Wait -PassThru -WindowStyle Hidden
        
        if ($proc.ExitCode -ne 0 -and -not (Test-DistroInstalled $Distro)) {
            Write-Warn "安装返回错误，尝试默认安装..."
            Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "`"$wslPath`" --install" -Wait -WindowStyle Hidden
            $Distro = "Ubuntu"
        }
    }

    # 等待安装完成
    Write-Host "等待 WSL 初始化..." -ForegroundColor Yellow
    $timeout = 60
    $timer = 0
    while (-not (Test-DistroInstalled $Distro) -and $timer -lt $timeout) {
        Start-Sleep -Seconds 1
        $timer++
        if ($timer % 10 -eq 0) { Write-Host "  已等待 $timer 秒..." -ForegroundColor Gray }
    }

    if (Test-DistroInstalled $Distro) {
        Write-Ok "WSL 就绪"
        Configure-Distro $Distro
    } else {
        Write-Err "等待超时，请手动检查安装状态"
    }
}

# 配置发行版
function Configure-Distro($distroName) {
    Write-Step "配置 $distroName..."

    # 确保发行版名称有效
    if ([string]::IsNullOrWhiteSpace($distroName)) {
        $distroName = "Ubuntu"
    }

    # 创建 wsl.conf（使用 Unix 换行符）
    $configContent = "[boot]`nsystemd=true`n`n[user]`ndefault=root`n"
    $tempConfig = "$env:TEMP\wsl.conf"
    
    # 使用 .NET 写入文件确保无 BOM 和正确换行符
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($configContent)
    [System.IO.File]::WriteAllBytes($tempConfig, $bytes)
    
    # 等待 WSL 文件系统就绪
    Write-Host "  等待文件系统就绪..." -ForegroundColor Gray
    $ready = $false
    for ($i = 0; $i -lt 10; $i++) {
        $test = wsl -d $distroName -e echo "ready" 2>&1
        if ($test -eq "ready") {
            $ready = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    
    if (-not $ready) {
        Write-Warn "WSL 响应较慢，继续尝试..."
    }

    # 复制配置文件到 WSL
    try {
        $destPath = "\\wsl$\$distroName\etc\wsl.conf"
        Copy-Item -Path $tempConfig -Destination $destPath -Force -ErrorAction Stop
        Write-Ok "wsl.conf 已写入"
    } catch {
        # 备选：使用 base64 编码通过 bash 写入
        Write-Host "  使用备选方式写入配置..." -ForegroundColor Gray
        $base64 = [Convert]::ToBase64String($bytes)
        wsl -d $distroName -u root -e bash -c "echo $base64 | base64 -d > /etc/wsl.conf" 2>$null
        Write-Ok "wsl.conf 已写入（备选方式）"
    }
    
    Remove-Item $tempConfig -ErrorAction SilentlyContinue

    # 重启生效
    wsl --terminate $distroName 2>$null
    Start-Sleep -Seconds 3

    # 创建用户
    $defaultName = $env:USERNAME
    $username = Read-Host "`n请输入 Linux 用户名（留空使用 '$defaultName'）"
    if ([string]::IsNullOrWhiteSpace($username)) { 
        $username = $defaultName 
    }
    
    # 清理用户名中的特殊字符
    $username = $username -replace '[^\w\-]', ''
    if ([string]::IsNullOrWhiteSpace($username)) {
        $username = "user"
    }

    Write-Host "创建用户 '$username'，请按提示设置密码..." -ForegroundColor Yellow
    
    # 分步执行，避免复杂命令解析问题
    wsl -d $distroName -u root -e useradd -m -G sudo -s /bin/bash $username 2>$null
    wsl -d $distroName -u root -e bash -c "echo '$username ALL=(ALL:ALL) NOPASSWD: ALL' > /etc/sudoers.d/$username"
    wsl -d $distroName -u root -e passwd $username
    wsl -d $distroName -u root -e sed -i "s/^default=.*/default=$username/" /etc/wsl.conf
    
    wsl --terminate $distroName 2>$null
    
    Write-Ok "配置完成，默认用户: $username"
    
    # 完成提示
    Write-Host "`n========================================" -ForegroundColor Green
    Write-Host "  安装完成！" -ForegroundColor Green
    Write-Host "  启动命令: wsl -d $distroName" -ForegroundColor White
    Write-Host "========================================" -ForegroundColor Green
    
    if ((Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux).RestartNeeded) {
        Write-Warn "需要重启计算机"
    } else {
        Read-Host "`n按 Enter 启动 $distroName"
        wsl -d $distroName
    }
}

# ========== UNINSTALL ==========
function Uninstall-WSL {
    Write-Host "=== WSL 卸载 ===" -ForegroundColor Cyan

    if ($All) {
        Write-Step "完全卸载 WSL..."
        if (-not $Force) {
            $confirm = Read-Host "删除所有 WSL 发行版和配置，确认? (yes/N)"
            if ($confirm -ne "yes") { return }
        }
        
        Get-InstalledDistros | ForEach-Object {
            Write-Host "  卸载 $_..." -ForegroundColor Yellow
            wsl --unregister $_ 2>$null
        }
        
        dism.exe /online /disable-feature /featurename:Microsoft-Windows-Subsystem-Linux /norestart | Out-Null
        dism.exe /online /disable-feature /featurename:VirtualMachinePlatform /norestart | Out-Null
        Write-Ok "WSL 已完全卸载"
        
    } else {
        if ([string]::IsNullOrWhiteSpace($Distro)) {
            $installed = Get-InstalledDistros
            if ($installed.Count -eq 0) { Write-Err "没有已安装的发行版"; return }
            
            Write-Host "`n已安装发行版:" -ForegroundColor Cyan
            for ($i = 0; $i -lt $installed.Count; $i++) { Write-Host "  [$i] $($installed[$i])" }
            
            $sel = Read-Host "选择要卸载的编号（或输入名称）"
            if ($sel -match "^\d+$" -and [int]$sel -lt $installed.Count) {
                $Distro = $installed[[int]$sel]
            } else {
                $Distro = $sel
            }
        }

        if (Test-DistroInstalled $Distro) {
            Write-Step "卸载 $Distro..."
            wsl --terminate $Distro 2>$null
            wsl --unregister $Distro 2>$null
            Write-Ok "$Distro 已卸载"
        } else {
            Write-Err "$Distro 未安装"
        }
    }
}

# ========== UPDATE ==========
function Update-WSL {
    Write-Host "=== WSL 更新 ===" -ForegroundColor Cyan

    Write-Step "更新 WSL 内核..."
    wsl --update
    Write-Ok "WSL 内核已更新"

    $installed = Get-InstalledDistros | Where-Object { $_ -match "Ubuntu" }
    if (-not $installed) {
        Write-Warn "未检测到 Ubuntu 发行版"
        return
    }

    foreach ($distro in $installed) {
        Write-Step "更新 $distro..."
        wsl -d $distro -u root -e bash -c "apt update && apt upgrade -y && apt autoremove -y" 2>$null
        Write-Ok "$distro 系统包已更新"
    }

    wsl --shutdown
    Write-Host "`n========================================" -ForegroundColor Green
    Write-Host "  更新完成！" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
}

# ========== 主入口 ==========
switch ($Action) {
    "install" { Install-WSL }
    "uninstall" { Uninstall-WSL }
    "update" { Update-WSL }
}

Write-Host "`n按任意键退出..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")