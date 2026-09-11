# 加载本地 Cloudflare 凭据并部署 worker-bff
# 用法（在 worker-bff 目录下）:
#   ./scripts/Deploy.ps1                 # = wrangler deploy
#   ./scripts/Deploy.ps1 dev              # = wrangler dev
# 凭据来源：.cf.local.env（gitignored，绝不入库）
param([Parameter(ValueFromRemainingArguments = $true)] $ArgsLeft)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$envFile = Join-Path (Get-Location) ".cf.local.env"
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([A-Z_]+)=(.*)$') { Set-Item "env:$($Matches[1])" $Matches[2] }
  }
} else {
  Write-Warning ".cf.local.env 不存在；如未 wrangler login 将无法部署"
}

$cmd = if ($ArgsLeft.Count -gt 0) { $ArgsLeft } else { @("deploy") }
npx wrangler@latest @cmd
