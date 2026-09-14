<#
.SYNOPSIS
    B站收藏夹 → bilimusic 音频仓自动同步（issue #4）。

.DESCRIPTION
    流程：BFF /api/bili-fav 拉收藏夹 bvid 清单 → 与 bilimusic/audio/ 已有文件做增量
    → yt-dlp 逐曲抽音轨（无损 copy AAC 存 .m4a，多 P 视频只取 P1）→ 超过 >18MB
    的自动 ffmpeg 无损切 HLS 分片（audio/{bvid}/index.m3u8 + seg 分片，绕开 jsdelivr
    单文件 20MB 硬限制——超限文件一律 403 不可播，见坑 6.3.20 补充）→ git add
    显式路径 → commit → push（gcore.jsdelivr 缓存约 12h，新曲上线有延迟属正常）。

    幂等：已存在 {bvid}.m4a/.mp3 或 {bvid}/ 目录（HLS 分片）任一即跳过；无增量则不产生提交。
    音质：默认无 cookie（实测未登录 132kbps AAC）；高音质升级 = 把 B 站 SESSDATA 导出为
    yt-dlp cookies.txt 放到 $CookiesFile 指定路径（默认 F:\AI\projects\bilimusic.cookies.txt，
    必须放在任何 git 仓之外——密钥不入库铁律），存在即自动启用，脚本对 <100kbps 结果告警。
    已失效视频（如收藏夹里的 BV1TJ411K7nz）下载失败会告警跳过，不影响其余曲目。
    切割阈值 $HlsThresholdMB：>该体积的音频切 HLS 分片并删除原 .m4a（避免仓内冗余）；
    播放器 BiliFloatPlayer.tsx 按 hls→.m4a→.mp3 顺序自动降级，无需人工干预。

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
    [string]$LogFile = "F:\AI\agents\ZCODE\date\run\bilimusic-sync.log",
    [int]$HlsThresholdMB = 18
)

$ErrorActionPreference = "Stop"
# PS 5.1 默认可能不含 TLS1.2，BFF HTTPS 调用需要
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$wingetLinks = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links"
$env:PATH = "$wingetLinks;$env:PATH"
$ytDlp = Join-Path $wingetLinks "yt-dlp.exe"
$ffprobe = Join-Path $wingetLinks "ffprobe.exe"
$ffmpeg = Join-Path $wingetLinks "ffmpeg.exe"

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

# 2) 增量 diff：audio/ 下已有 .m4a/.mp3 基名或 {bvid}/ 分片目录视作已入库
$existing = Get-ChildItem -Path $audioDir -File |
    ForEach-Object { [IO.Path]::GetFileNameWithoutExtension($_.Name) } |
    Select-Object -Unique
$existingSet = [System.Collections.Generic.HashSet[string]]::new([string[]]$existing)
foreach ($d in (Get-ChildItem -Path $audioDir -Directory | Select-Object -ExpandProperty Name)) {
    [void]$existingSet.Add($d)
}
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

# 3.5) 大文件自动切 HLS 分片（jsdelivr 单文件 20MB 硬限制 → 超限 403，坑 6.3.20 补充）
#      ffmpeg -c copy 无损切片保留原音质；切完删除原 .m4a（仓内不保留 >20MB 冗余）；
#      播放器按 hls → .m4a → .mp3 顺序自动降级，无需人工干预。
$cutNames = [System.Collections.Generic.HashSet[string]]::new()
$hlsDirs = [System.Collections.Generic.List[string]]::new()
if (-not (Test-Path $ffmpeg) -and @($downloaded | Where-Object {
        (Get-Item (Join-Path $audioDir $_)).Length -ge ($HlsThresholdMB * 1MB)
    }).Count -gt 0) {
    throw "存在超阈值大文件但 ffmpeg 不存在：$ffmpeg（winget install Gyan.FFmpeg）"
}
foreach ($f in $downloaded) {
    $file = Join-Path $audioDir $f
    if (-not (Test-Path $file)) { continue }
    if ((Get-Item $file).Length -lt ($HlsThresholdMB * 1MB)) { continue }
    $bvid = [IO.Path]::GetFileNameWithoutExtension($f)
    $outDir = Join-Path $audioDir $bvid
    if (Test-Path (Join-Path $outDir "index.m3u8")) {
        Log "  $bvid 已有 HLS 分片，跳过切割"
        [void]$cutNames.Add($f); [void]$hlsDirs.Add("audio/$bvid")
        continue
    }
    Log "  ✂ $bvid（$([math]::Round((Get-Item $file).Length/1MB,1))MB > ${HlsThresholdMB}MB）切 HLS 分片..."
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null
    $eap = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    $ffOut = & $ffmpeg -y -loglevel error -i $file -c copy -f hls -hls_time 240 `
        -hls_playlist_type vod -hls_segment_filename (Join-Path $outDir "seg%03d.ts") `
        (Join-Path $outDir "index.m3u8") 2>&1
    $ErrorActionPreference = $eap
    $ffOut | ForEach-Object { "$_" } | Select-Object -First 3 | ForEach-Object { Log "    $_" }
    if ($LASTEXITCODE -ne 0) { throw "ffmpeg 切割 $bvid 失败" }
    Remove-Item -Force $file
    [void]$cutNames.Add($f)
    [void]$hlsDirs.Add("audio/$bvid")
    $sumMB = [math]::Round((Get-ChildItem $outDir -File | Measure-Object Length -Sum).Sum / 1MB, 1)
    Log "  ✓ $bvid 已切 HLS 分片并移除原 .m4a（分片共 ${sumMB}MB，单片均 <20MB）"
}

# 4) git 提交推送（显式路径铁律；无增量不产生空提交）
$gitAdds = @()
foreach ($f in $downloaded) { if (-not $cutNames.Contains($f)) { $gitAdds += "audio/$f" } }
$gitAdds += $hlsDirs
if ($gitAdds.Count -eq 0) { Log "无新增文件，结束（幂等）"; exit 0 }
foreach ($a in $gitAdds) { git -C $CloneDir add $a }
$commitMsg = "sync: 收藏夹音频增量 $($gitAdds.Count) 项（bilimusic-sync $(Get-Date -Format 'yyyy-MM-dd')）"
git -C $CloneDir commit -m $commitMsg | Out-Null
if ($LASTEXITCODE -ne 0) { Log "git commit 失败（可能无变更）"; exit 1 }
$eap = $ErrorActionPreference; $ErrorActionPreference = "Continue"
$pushOut = git -C $CloneDir push origin HEAD 2>&1
$ErrorActionPreference = $eap
if ($LASTEXITCODE -ne 0) { Log "✗ git push 失败：$($pushOut | ForEach-Object { "$_" })（检查 bilimusic 推送凭据）"; exit 1 }
Log "✓ 已推送 $commitMsg"
Log "===== bilimusic-sync 结束（jsdelivr 缓存约 12h 后全量生效） ====="