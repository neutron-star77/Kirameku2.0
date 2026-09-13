<#
.SYNOPSIS
    B站收藏夹 → bilimusic 音频仓自动同步（issue #4）。

.DESCRIPTION
    流程：BFF /api/bili-fav 拉收藏夹 bvid 清单 → 与 bilimusic/audio/ 已有文件做增量
    → yt-dlp 逐曲抽音轨（无损 copy AAC 存 .m4a，多 P 视频只取 P1）→ git add 显式路径
    → commit → push（gcore.jsdelivr 缓存约 12h，新曲上线有延迟属正常）。

    幂等：已存在 {bvid}.m4a 或 {bvid}.mp3 任一即跳过；无增量则不产生提交。
    音质：默认无 cookie（实测未登录 132kbps AAC）；高音质升级 = 把 B 站 SESSDATA 导出为
    yt-dlp cookies.txt 放到 $CookiesFile 指定路径（默认 F:\AI\projects\bilimusic.cookies.txt，
    必须放在任何 git 仓之外——密钥不入库铁律），存在即自动启用，脚本对 <100kbps 结果告警。
    已失效视频（如收藏夹里的 BV1TJ411K7nz）下载失败会告警跳过，不影响其余曲目。

.NOTES
    定时注册（Windows 任务计划程序，每日 09:30）：
    schtasks /Create /TN "bilimusic-sync" /SC DAILY /ST 09:30 /F /TR ^
      "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File F:\AI\projects\Kirameku2.0\scripts\bilimusic-sync.ps1"
    日志：F:\AI\agents\ZCODE\date\run\bilimusic-sync.log（追加）
#>
param(
    [switch]$DryRun,
    [switch]$Force,
    [string]$CloneDir = "F:\AI\projects\bilimusic",
    [string]$Fid = "3631802308",
    [string]$BffBase = "https://bff.neutronstar.fun",
    [string]$CookiesFile = "F:\AI\projects\bilimusic.cookies.txt",
    [string]$LogFile = "F:\AI\agents\ZCODE\date\run\bilimusic-sync.log"
)

$ErrorActionPreference = "Stop"
# PS 5.1 默认可能不含 TLS1.2，BFF HTTPS 调用需要
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$wingetLinks = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links"
$env:PATH = "$wingetLinks;$env:PATH"
$ytDlp = Join-Path $wingetLinks "yt-dlp.exe"
$ffprobe = Join-Path $wingetLinks "ffprobe.exe"

function Log([string]$msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Write-Host $line
    try { Add-Content -Path $LogFile -Value $line -Encoding UTF8 } catch {}
}

Log "===== bilimusic-sync 开始 ====="

# 0) 前置检查
if (-not (Test-Path $ytDlp)) { throw "yt-dlp 不存在：$ytDlp（winget install yt-dlp.yt-dlp）" }
if (-not (Test-Path $CloneDir)) { throw "bilimusic 克隆不存在：$CloneDir" }
$audioDir = Join-Path $CloneDir "audio"
if (-not (Test-Path $audioDir)) { New-Item -ItemType Directory -Path $audioDir | Out-Null }

$useCookies = Test-Path $CookiesFile
if ($useCookies) { Log "检测到 cookie 文件，启用高音质下载：$CookiesFile" }
else { Log "无 cookie 文件，按未登录音质下载（实测约 132kbps）；升级方法见脚本头注释" }

# 1) BFF 拉收藏夹清单（后端已做 B 站风控处理，勿在客户端直连 B 站 API）
# PS5.1 坑：IRM/Invoke-WebRequest 对无 charset 的 JSON 按 Latin-1 解码→中文乱码；手动按 UTF-8 解
$api = "$BffBase/api/bili-fav?media_id=$Fid"
$resp = Invoke-WebRequest -Uri $api -UseBasicParsing -TimeoutSec 30
if ($resp.RawContentStream) {
    $fav = [Text.Encoding]::UTF8.GetString($resp.RawContentStream.ToArray()) | ConvertFrom-Json
} else {
    $fav = $resp.Content | ConvertFrom-Json
}
$bvids = @($fav.tracks | Where-Object { $_.bvid } | ForEach-Object { $_.bvid } | Select-Object -Unique)
Log "收藏夹「$($fav.title)」共 $($bvids.Count) 个 bvid"

# 2) 增量 diff：audio/ 下已有 .m4a/.mp3 基名视作已入库
$existing = Get-ChildItem -Path $audioDir -File |
    ForEach-Object { [IO.Path]::GetFileNameWithoutExtension($_.Name) } |
    Select-Object -Unique
$existingSet = [System.Collections.Generic.HashSet[string]]::new([string[]]$existing)
$pending = @($bvids | Where-Object { $Force -or -not $existingSet.Contains($_) })
Log "待下载 $($pending.Count) 首（已入库 $($bvids.Count - $pending.Count)）"
if ($DryRun) { $pending | ForEach-Object { Log "  [DryRun] $_" }; exit 0 }

# 3) 逐曲下载
$downloaded = [System.Collections.Generic.List[string]]::new()
$failed = [System.Collections.Generic.List[string]]::new()
$i = 0
foreach ($bvid in $pending) {
    $i++
    $out = Join-Path $audioDir "$bvid.%(ext)s"
    Log "[$i/$($pending.Count)] 下载 $bvid ..."
    $ytArgs = @(
        "-x", "--audio-format", "m4a", "--audio-quality", "0",
        "--playlist-items", "1",
        "--sleep-requests", "2", "--no-overwrites", "--no-progress",
        "-o", $out
    )
    if ($useCookies) { $ytArgs += "--cookies=$CookiesFile" }
    # PS5.1 坑：EAP=Stop 时 native 命令 2>&1 会把 stderr 行变异常——临时降级为 Continue
    $eap = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    $output = & $ytDlp @ytArgs "https://www.bilibili.com/video/$bvid" 2>&1
    $ErrorActionPreference = $eap
    $output | ForEach-Object { "$_" } | Where-Object { $_ -match "ERROR|WARNING" } |
        Select-Object -First 3 | ForEach-Object { Log "    $_" }
    if ($LASTEXITCODE -ne 0) {
        Log "  ✗ $bvid 下载失败（失效视频或风控），跳过"
        $failed.Add($bvid)
        Get-ChildItem -Path $audioDir -Filter "$bvid.*" -ErrorAction SilentlyContinue |
            Where-Object { $_.Length -eq 0 } | Remove-Item -Force
        continue
    }
    $file = Get-ChildItem -Path $audioDir -Filter "$bvid.*" |
        Where-Object { $_.Extension -in ".m4a", ".mp3" } | Select-Object -First 1
    if (-not $file) { Log "  ✗ $bvid 未产出音频文件，跳过"; $failed.Add($bvid); continue }

    # 音质守卫：低于 100kbps 说明没拿到应有码率（cookie 失效/风控降级）
    if (Test-Path $ffprobe) {
        $probe = & $ffprobe -v quiet -show_entries format=bit_rate -of default=noprint_wrappers=1:nokey=1 $file.FullName
        [int]$kbps = 0; [void][int]::TryParse([string]$probe, [ref]$kbps); $kbps = [int]($kbps / 1000)
        if ($kbps -gt 0 -and $kbps -lt 100) {
            Log "  ⚠ $bvid 仅 ${kbps}kbps（<100，音质偏低）——建议导出 SESSDATA cookie 后 -Force 重下"
        } else {
            Log "  ✓ $($file.Name) ${kbps}kbps $([math]::Round($file.Length/1MB,1))MB"
        }
    }
    $downloaded.Add($file.Name)
}

Log "下载完成：成功 $($downloaded.Count)，失败 $($failed.Count)"

# 4) git 提交推送（显式路径铁律；无增量不产生空提交）
if ($downloaded.Count -eq 0) { Log "无新增文件，结束（幂等）"; exit 0 }
foreach ($f in $downloaded) { git -C $CloneDir add "audio/$f" }
$commitMsg = "sync: 收藏夹音频增量 $($downloaded.Count) 首（bilimusic-sync $(Get-Date -Format 'yyyy-MM-dd')）"
git -C $CloneDir commit -m $commitMsg | Out-Null
if ($LASTEXITCODE -ne 0) { Log "git commit 失败（可能无变更）"; exit 1 }
$eap = $ErrorActionPreference; $ErrorActionPreference = "Continue"
$pushOut = git -C $CloneDir push origin HEAD 2>&1
$ErrorActionPreference = $eap
if ($LASTEXITCODE -ne 0) { Log "✗ git push 失败：$($pushOut | ForEach-Object { "$_" })（检查 bilimusic 推送凭据）"; exit 1 }
Log "✓ 已推送 $commitMsg"
Log "===== bilimusic-sync 结束（jsdelivr 缓存约 12h 后全量生效） ====="
