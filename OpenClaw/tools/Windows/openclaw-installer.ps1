# ============================================================
# OpenClaw Windows 管理脚本（增强版 v2.3）
# 支持: install, uninstall, update 操作
# 改进: 移除 cmd /c 依赖，改用 PowerShell 原生方式执行 npm
# ============================================================

param(
    [Parameter(Position=0)]
    [ValidateSet("install", "update", "uninstall", "")]
    [string]$Command = "install",
    
    [switch]$Help,
    [switch]$h
)

# 设置错误处理
$ErrorActionPreference = "Stop"

# 配置
$script:PackageName = "openclaw"
$script:NodeVersion = "v22.14.0"
$script:NodeUrl = "https://nodejs.org/dist/v22.14.0/node-v22.14.0-x64.msi"
$script:InstallerPath = "$env:TEMP\node-v22.14.0-x64.msi"
$env:NPM_REGISTRY = "https://registry.npmmirror.com"

# 打印带颜色的消息
function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    $colors = @{
        "Red" = [ConsoleColor]::Red
        "Green" = [ConsoleColor]::Green
        "Yellow" = [ConsoleColor]::Yellow
        "Cyan" = [ConsoleColor]::Cyan
        "White" = [ConsoleColor]::White
    }
    if ($colors.ContainsKey($Color)) {
        Write-Host $Message -ForegroundColor $colors[$Color]
    } else {
        Write-Host $Message
    }
}

# 检查管理员权限
function Test-Admin {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# 打印横幅
function Print-Banner {
    Write-Host ""
    Write-Host "╔═══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║           OpenClaw Windows 管理脚本 v2.3                     ║" -ForegroundColor Cyan
    Write-Host "╚═══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

# 显示帮助信息
function Show-Help {
    Print-Banner
    Write-Host @"
使用方法:
    .\openclaw-manager.ps1 [命令] [选项]

命令:
    install      安装 OpenClaw（默认）
    uninstall    卸载 OpenClaw
    update       更新 OpenClaw 到最新版本

选项:
    -Help, -h    显示此帮助信息

示例:
    .\openclaw-manager.ps1                    # 默认安装
    .\openclaw-manager.ps1 install            # 安装
    .\openclaw-manager.ps1 uninstall          # 卸载
    .\openclaw-manager.ps1 update             # 更新

注意:
    - 安装/卸载建议以管理员身份运行 PowerShell
    - 更新操作不需要管理员权限

"@ -ForegroundColor Cyan
}

# 刷新环境变量
function Refresh-Environment {
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + 
                [System.Environment]::GetEnvironmentVariable("Path","User")
    
    # 重新加载环境变量
    foreach($level in "Machine","User") {
        [Environment]::GetEnvironmentVariables($level).GetEnumerator() | ForEach-Object {
            $name = $_.Name
            $value = $_.Value
            Set-Item -Path Env:$name -Value $value -ErrorAction SilentlyContinue
        }
    }
}

# 检查 Node.js 是否已安装
function Test-NodeInstalled {
    try {
        $nodeVersion = & node --version 2>$null
        return [bool]$nodeVersion
    } catch {
        return $false
    }
}

# 获取 Node.js 版本
function Get-NodeVersion {
    try {
        return & node --version 2>$null
    } catch {
        return $null
    }
}

# 检查 npm 是否可用
function Test-NpmAvailable {
    try {
        $npmVersion = & npm --version 2>$null
        return [bool]$npmVersion
    } catch {
        return $false
    }
}

# 检查 OpenClaw 是否已安装
function Test-OpenClawInstalled {
    try {
        $version = & openclaw --version 2>$null
        return [bool]$version
    } catch {
        return $false
    }
}

# 获取 OpenClaw 版本
function Get-OpenClawVersion {
    try {
        return & openclaw --version 2>$null
    } catch {
        return $null
    }
}

# 查找 Node.js 安装路径
function Find-NodeInstallation {
    Write-ColorOutput "正在扫描 Node.js 安装位置..." Yellow
    
    $possiblePaths = @(
        "C:\Program Files\nodejs",
        "C:\Program Files (x86)\nodejs",
        "$env:LOCALAPPDATA\Programs\nodejs",
        "$env:ProgramFiles\nodejs",
        "$env:ProgramFiles(x86)\nodejs",
        "C:\nodejs"
    )
    
    foreach ($path in $possiblePaths) {
        $nodeExe = Join-Path $path "node.exe"
        if (Test-Path $nodeExe) {
            Write-ColorOutput "  ✓ 发现 Node.js: $path" Green
            return $path
        }
    }
    
    # 尝试从 where 命令查找
    try {
        $whereNode = & where.exe node 2>$null
        if ($whereNode) {
            $foundPath = Split-Path $whereNode[0] -Parent
            Write-ColorOutput "  ✓ 发现 Node.js: $foundPath (via where.exe)" Green
            return $foundPath
        }
    } catch {
        # ignore
    }
    
    return $null
}

# 验证 Node.js 安装完整性
function Test-NodeInstallationIntegrity {
    param([string]$NodePath)
    
    $results = @{
        NodeExe = Test-Path (Join-Path $NodePath "node.exe")
        NpmCmd = Test-Path (Join-Path $NodePath "npm.cmd")
        NpmCli = Test-Path (Join-Path $NodePath "node_modules\npm\bin\npm-cli.js")
    }
    
    return $results
}

# 修复 Node.js PATH 环境变量（增强版）
function Add-NodeToPath {
    Write-ColorOutput "正在检查 Node.js 环境变量..." Yellow
    
    $modified = $false
    
    # 1. 查找 Node.js 安装路径
    $nodePath = Find-NodeInstallation
    
    if (-not $nodePath) {
        Write-ColorOutput "  ✗ 未找到 Node.js 安装" Red
        return $false
    }
    
    # 2. 验证安装完整性
    $integrity = Test-NodeInstallationIntegrity -NodePath $nodePath
    Write-ColorOutput "  检查安装完整性:" Yellow
    Write-ColorOutput "    node.exe: $(if($integrity.NodeExe){'✓'}else{'✗'})" $(if($integrity.NodeExe){'Green'}else{'Red'})
    Write-ColorOutput "    npm.cmd: $(if($integrity.NpmCmd){'✓'}else{'✗'})" $(if($integrity.NpmCmd){'Green'}else{'Red'})
    Write-ColorOutput "    npm-cli.js: $(if($integrity.NpmCli){'✓'}else{'✗'})" $(if($integrity.NpmCli){'Green'}else{'Red'})
    
    if (-not $integrity.NodeExe) {
        Write-ColorOutput "  ✗ Node.exe 不存在，安装可能损坏" Red
        return $false
    }
    
    # 3. 检查并修复用户 PATH - 确保不破坏现有路径
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    
    # 检查是否已在 PATH 中（当前会话）
    $currentPathLower = $env:Path.ToLower()
    $nodePathLower = $nodePath.ToLower()
    
    if ($currentPathLower -notlike "*$nodePathLower*") {
        Write-ColorOutput "  → Node.js 不在 PATH 中，正在修复..." Yellow
        
        # 添加到用户 PATH（追加到末尾，避免破坏现有路径）
        if ($userPath -notlike "*$nodePath*") {
            # 使用追加方式，不要覆盖
            if ([string]::IsNullOrEmpty($userPath)) {
                $newUserPath = $nodePath
            } else {
                $newUserPath = "$userPath;$nodePath"
            }
            [Environment]::SetEnvironmentVariable("Path", $newUserPath, "User")
            Write-ColorOutput "  ✓ 已添加到用户 PATH" Green
            $modified = $true
        }
    } else {
        Write-ColorOutput "  ✓ Node.js 已在 PATH 中" Green
    }
    
    # 4. 检查 npm 全局路径
    $npmGlobalPath = "$env:APPDATA\npm"
    if (Test-Path $npmGlobalPath) {
        if ($userPath -notlike "*$npmGlobalPath*" -and $env:Path -notlike "*$npmGlobalPath*") {
            $currentUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
            if ([string]::IsNullOrEmpty($currentUserPath)) {
                $newUserPath = $npmGlobalPath
            } else {
                $newUserPath = "$currentUserPath;$npmGlobalPath"
            }
            [Environment]::SetEnvironmentVariable("Path", $newUserPath, "User")
            Write-ColorOutput "  ✓ 已添加 npm 全局路径到 PATH" Green
            $modified = $true
        }
    }
    
    # 5. 刷新当前会话环境变量
    if ($modified) {
        Refresh-Environment
        Write-ColorOutput "  ✓ 环境变量已刷新" Green
    }
    
    return $modified
}

# 安装 Node.js
function Install-NodeJS {
    Write-ColorOutput "开始安装 Node.js $script:NodeVersion..." Yellow

    # 检查是否已下载
    if (Test-Path $script:InstallerPath) {
        Remove-Item $script:InstallerPath -Force
    }

    Write-ColorOutput "正在下载 Node.js..." Cyan
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $script:NodeUrl -OutFile $script:InstallerPath -UseBasicParsing
    } catch {
        Write-ColorOutput "下载失败: $_" Red
        return $false
    }

    if (Test-Path $script:InstallerPath) {
        Write-ColorOutput "正在安装 Node.js（需要管理员权限）..." Yellow
        
        try {
            $process = Start-Process msiexec.exe -ArgumentList "/i `"$($script:InstallerPath)`" /qn /norestart" -Wait -PassThru -Verb RunAs
            
            if ($process.ExitCode -eq 0) {
                Write-ColorOutput "Node.js 安装完成！" Green
                Start-Sleep -Seconds 3
                Add-NodeToPath
                return $true
            } else {
                Write-ColorOutput "Node.js 安装失败，退出码: $($process.ExitCode)" Red
                return $false
            }
        } catch {
            Write-ColorOutput "安装过程出错: $_" Red
            return $false
        }
    } else {
        Write-ColorOutput "Node.js 安装包下载失败！" Red
        return $false
    }
}

# 配置 npm
function Configure-Npm {
    Write-ColorOutput "正在配置 npm..." Yellow
    
    try {
        $registry = $env:NPM_REGISTRY
        
        # 使用数组形式传参，避免字符串解析问题
        $null = & npm config set registry $registry 2>&1 | Where-Object { $_ -notmatch "^npm warn" }
        
        $npmCache = "$env:LOCALAPPDATA\npm-cache"
        if (-not (Test-Path $npmCache)) {
            New-Item -ItemType Directory -Path $npmCache -Force | Out-Null
        }
        $null = & npm config set cache $npmCache 2>&1 | Where-Object { $_ -notmatch "^npm warn" }
        
        # 清理缓存时过滤掉警告信息
        $null = & npm cache clean --force 2>&1 | Where-Object { $_ -notmatch "^npm warn" }
        
        Write-ColorOutput "npm 配置完成！" Green
        return $true
    } catch {
        $errorString = $_.ToString()
        if ($errorString -match "npm warn") {
            Write-ColorOutput "npm 配置完成（有警告，已忽略）" Green
            return $true
        }
        Write-ColorOutput "npm 配置失败: $_" Red
        return $false
    }
}

# ==================== INSTALL ====================
function Invoke-Install {
    Print-Banner
    Write-ColorOutput "【安装模式】" Cyan
    Write-Host ""

    # 检查管理员权限
    $isAdmin = Test-Admin
    if (-not $isAdmin) {
        Write-ColorOutput "⚠️  建议使用管理员权限运行以安装 Node.js" Yellow
    }

    # 检查 Node.js
    if (-not (Test-NodeInstalled)) {
        Write-ColorOutput "检测到 Node.js 未安装！" Yellow
        
        if ($isAdmin) {
            $success = Install-NodeJS
            if (-not $success) {
                Write-ColorOutput "Node.js 安装失败，请手动安装后重试" Red
                Write-ColorOutput "下载地址: https://nodejs.org/" Yellow
                exit 1
            }
        } else {
            Write-ColorOutput "❌ 需要管理员权限安装 Node.js" Red
            Write-ColorOutput "请右键 PowerShell 选择'以管理员身份运行'" Yellow
            exit 1
        }
    } else {
        Write-ColorOutput "✓ Node.js 已安装: $(Get-NodeVersion)" Green
    }

    # 修复 PATH（增强逻辑）
    $pathFixed = Add-NodeToPath
    if ($pathFixed) {
        Write-ColorOutput "环境变量已修改，正在重新加载..." Yellow
        Start-Sleep -Seconds 2
        Refresh-Environment
    }

    # 检查 npm - 如果不可用，尝试额外修复
    $npmRetryCount = 0
    $maxRetries = 2
    
    while (-not (Test-NpmAvailable) -and $npmRetryCount -lt $maxRetries) {
        $npmRetryCount++
        Write-ColorOutput "npm 不可用，尝试修复 (尝试 $npmRetryCount/$maxRetries)..." Yellow
        
        Refresh-Environment
        Start-Sleep -Seconds 2
        
        if (-not (Test-NpmAvailable)) {
            $nodePath = Find-NodeInstallation
            if ($nodePath) {
                $npmFullPath = Join-Path $nodePath "npm.cmd"
                if (Test-Path $npmFullPath) {
                    Write-ColorOutput "  尝试直接使用完整路径: $npmFullPath" Yellow
                    try {
                        $testVer = & $npmFullPath --version 2>$null
                        if ($testVer) {
                            Write-ColorOutput "  ✓ npm 可以运行，但不在 PATH 中" Green
                            $env:Path = "$nodePath;$env:Path"
                        }
                    } catch {
                        Write-ColorOutput "  ✗ 即使完整路径也无法运行" Red
                    }
                }
            }
        }
    }
    
    if (-not (Test-NpmAvailable)) {
        Write-ColorOutput "❌ npm 仍然不可用" Red
        Write-ColorOutput "" Red
        Write-ColorOutput "可能的原因:" Yellow
        Write-ColorOutput "  1. Node.js 安装不完整（npm 组件损坏）" White
        Write-ColorOutput "  2. 防病毒软件阻止了 npm.cmd 执行" White
        Write-ColorOutput "  3. 企业组策略限制了脚本执行" White
        Write-ColorOutput "" Yellow
        Write-ColorOutput "建议解决方案:" Yellow
        Write-ColorOutput "  1. 重新安装 Node.js: https://nodejs.org/dist/v22.14.0/node-v22.14.0-x64.msi" Cyan
        Write-ColorOutput "  2. 安装完成后重启电脑" White
        Write-ColorOutput "  3. 或使用 nvm-windows 管理 Node.js 版本" White
        exit 1
    }

    Write-ColorOutput "✓ npm 可用: v$(npm --version)" Green

    # 配置 npm
    Configure-Npm

    # 检查是否已安装
    if (Test-OpenClawInstalled) {
        Write-ColorOutput "⚠️  OpenClaw 已安装: $(Get-OpenClawVersion)" Yellow
        Write-ColorOutput "如需更新，请使用: .\openclaw-manager.ps1 update" Cyan
        return
    }

    # 安装 OpenClaw
    Write-ColorOutput "正在安装 OpenClaw..." Yellow
    
    try {
        # 方法1: 官方脚本
        Write-ColorOutput "尝试官方安装脚本..." Cyan
        Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force 2>$null
        
        $installScript = "https://openclaw.ai/install.ps1"
        Invoke-Expression ((New-Object System.Net.WebClient).DownloadString($installScript))
        
        if (Test-OpenClawInstalled) {
            Write-ColorOutput "✓ OpenClaw 安装成功！" Green
            Show-PostInstallInfo
            return
        }
    } catch {
        Write-ColorOutput "官方脚本失败，尝试 npm 安装..." Yellow
    }

    # 方法2: npm 全局安装
    try {
        Write-ColorOutput "使用 npm 全局安装..." Cyan
        & npm install -g $script:PackageName --registry $env:NPM_REGISTRY
        
        if ($LASTEXITCODE -eq 0 -and (Test-OpenClawInstalled)) {
            Write-ColorOutput "✓ OpenClaw 安装成功！" Green
            Show-PostInstallInfo
            return
        }
    } catch {
        Write-ColorOutput "npm 安装失败: $_" Red
    }

    # 方法3: 提示手动安装
    Write-ColorOutput "❌ 自动安装失败" Red
    Write-ColorOutput "您可以尝试手动安装:" Yellow
    Write-Host "  npm install -g $script:PackageName" -ForegroundColor Cyan
}

# ==================== UNINSTALL ====================
function Invoke-Uninstall {
    Print-Banner
    Write-ColorOutput "【卸载模式】" Cyan
    Write-Host ""

    $packageName = $script:PackageName

    if (-not (Test-OpenClawInstalled)) {
        Write-ColorOutput "⚠️  OpenClaw 未安装或不在 PATH 中" Yellow
        
        if (Test-NpmAvailable) {
            Write-ColorOutput "检查 npm 全局包列表..." Cyan
            $globalPackages = & npm list -g --depth=0 2>$null
            
            if ($globalPackages -match $packageName) {
                Write-ColorOutput "发现残留，执行清理..." Yellow
            } else {
                Write-ColorOutput "确认未安装 OpenClaw" Green
                return
            }
        } else {
            return
        }
    } else {
        $version = Get-OpenClawVersion
        Write-ColorOutput "即将卸载 OpenClaw $version" Yellow
    }

    Write-Host ""
    $confirm = Read-Host "确认卸载? (y/N)"
    if ($confirm -ne 'y' -and $confirm -ne 'Y') {
        Write-ColorOutput "已取消卸载" Yellow
        return
    }

    Write-ColorOutput "正在卸载 OpenClaw..." Yellow
    
    try {
        & npm uninstall -g $packageName
        
        if ($LASTEXITCODE -eq 0) {
            Write-ColorOutput "✓ OpenClaw 已卸载" Green
        } else {
            throw "npm 返回错误码: $LASTEXITCODE"
        }
        
        Write-ColorOutput "✓ OpenClaw 卸载成功" Green
        
    } catch {
        Write-ColorOutput "❌ 卸载失败: $_" Red
        Write-ColorOutput "您可以尝试手动卸载:" Yellow
        Write-Host "  npm uninstall -g $packageName" -ForegroundColor Cyan
        exit 1
    }

    Write-ColorOutput "清理相关数据..." Yellow
    
    try {
        & npm cache clean --force 2>$null | Out-Null
        Write-ColorOutput "  ✓ npm 缓存已清理" Green
    } catch {
        Write-ColorOutput "  ⚠️ npm 缓存清理警告: $_" Yellow
    }
    
    $configPaths = @(
        "$env:USERPROFILE\.openclaw",
        "$env:APPDATA\openclaw",
        "$env:LOCALAPPDATA\openclaw"
    )
    
    $configDeleted = $false
    foreach ($path in $configPaths) {
        if (Test-Path $path) {
            try {
                Remove-Item -Path $path -Recurse -Force -ErrorAction SilentlyContinue
                Write-ColorOutput "  ✓ 已删除: $path" Green
                $configDeleted = $true
            } catch {
                Write-ColorOutput "  ⚠️ 无法删除 $path : $_" Yellow
            }
        }
    }
    
    if (-not $configDeleted) {
        Write-ColorOutput "  ℹ️ 未找到 OpenClaw 配置文件" Cyan
    }
    
    Write-ColorOutput "✓ 卸载清理完成" Green
}

# ==================== UPDATE ====================
function Invoke-Update {
    Print-Banner
    Write-ColorOutput "【更新模式】" Cyan
    Write-Host ""

    if (-not (Test-OpenClawInstalled)) {
        Write-ColorOutput "❌ OpenClaw 未安装，无法更新" Red
        Write-ColorOutput "请先运行: .\openclaw-manager.ps1 install" Yellow
        exit 1
    }

    $oldVersion = Get-OpenClawVersion
    Write-ColorOutput "当前版本: $oldVersion" Cyan

    if (-not (Test-NpmAvailable)) {
        Write-ColorOutput "❌ npm 不可用，尝试修复环境变量..." Yellow
        Add-NodeToPath
        Refresh-Environment
        
        if (-not (Test-NpmAvailable)) {
            Write-ColorOutput "❌ 无法找到 npm，请检查 Node.js 安装" Red
            exit 1
        }
    }

    # 更新 npm 本身 - 使用 PowerShell 原生方式，不使用 cmd /c
    Write-ColorOutput "检查 npm 更新..." Yellow
    $registry = $env:NPM_REGISTRY
    
    try {
        # 使用 Start-Process 替代 cmd /c，避免环境变量问题
        $process = Start-Process -FilePath "npm" -ArgumentList "install", "-g", "npm", "--registry", $registry -Wait -PassThru -WindowStyle Hidden -ErrorAction SilentlyContinue
        if ($process.ExitCode -ne 0) {
            Write-ColorOutput "  ⚠️ npm 自身更新失败或已是最新，继续..." Yellow
        }
    } catch {
        Write-ColorOutput "  ⚠️ npm 自身更新跳过" Yellow
    }

    # 更新 OpenClaw - 使用 PowerShell 原生方式
    Write-ColorOutput "正在更新 OpenClaw..." Yellow
    
    try {
        $package = $script:PackageName
        
        # 方法1: 尝试更新
        Write-ColorOutput "  尝试 npm update..." Cyan
        $updateOutput = & npm update -g $package --registry $registry 2>&1
        $updateOutput | Where-Object { $_ -notmatch "^npm (warn|error)" } | Out-Null
        
        # 验证更新
        Refresh-Environment
        Start-Sleep -Seconds 2
        
        if (-not (Test-NpmAvailable)) {
            Add-NodeToPath
            Start-Sleep -Seconds 1
        }
        
        $newVersion = Get-OpenClawVersion
        
        if ($newVersion -eq $oldVersion) {
            Write-ColorOutput "  尝试强制安装最新版本..." Cyan
            
            # 方法2: 强制安装最新版 - 使用 Start-Process 获取更好的错误处理
            $process = Start-Process -FilePath "npm" -ArgumentList "install", "-g", "$package@latest", "--registry", $registry, "--force" -Wait -PassThru -WindowStyle Hidden
            
            if ($process.ExitCode -eq 0) {
                Write-ColorOutput "  ✓ 强制安装完成" Green
            } else {
                Write-ColorOutput "  ⚠️ 强制安装返回码: $($process.ExitCode)" Yellow
            }
        }
        
        # 再次验证
        Refresh-Environment
        Start-Sleep -Seconds 2
        $finalVersion = Get-OpenClawVersion
        
        if ($finalVersion -ne $oldVersion) {
            Write-ColorOutput "✓ 更新成功: $oldVersion → $finalVersion" Green
        } else {
            Write-ColorOutput "✓ 已是最新版本: $finalVersion" Green
        }
        
        # 清理缓存
        Write-ColorOutput "清理更新缓存..." Yellow
        $null = & npm cache clean --force 2>&1 | Where-Object { $_ -notmatch "^npm warn" }
        
    } catch {
        Write-ColorOutput "❌ 更新失败: $_" Red
        Write-ColorOutput "您可以尝试手动更新:" Yellow
        Write-Host "  npm install -g $script:PackageName@latest" -ForegroundColor Cyan
        exit 1
    }
}

# 显示安装后信息
function Show-PostInstallInfo {
    Write-Host ""
    Write-ColorOutput "═══════════════════════════════════════════════════════════════" Cyan
    Write-ColorOutput "安装完成！后续操作：" Cyan
    Write-ColorOutput "═══════════════════════════════════════════════════════════════" Cyan
    Write-Host @"

常用命令:
  openclaw --version          查看版本
  openclaw status             查看状态
  openclaw health             健康检查
  openclaw help               显示帮助

管理脚本用法:
  .\openclaw-manager.ps1 update       更新到最新版
  .\openclaw-manager.ps1 uninstall    卸载 OpenClaw

文档: https://docs.openclaw.ai
"@ -ForegroundColor White
}

# ==================== 主入口 ====================
function Main {
    if ($Help -or $h) {
        Show-Help
        return
    }

    switch ($Command.ToLower()) {
        "install" { 
            Invoke-Install 
        }
        "uninstall" { 
            Invoke-Uninstall 
        }
        "update" { 
            Invoke-Update 
        }
        default { 
            Invoke-Install 
        }
    }
}

Main