# 本地演示启动脚本（不会把 Key 写进任何文件）
# 用法：
#   .\start_demo.ps1 -DeepSeekKey "sk-xxxx"      # 真实翻译（DeepSeek）
#   .\start_demo.ps1 -Mock                      # 不调外部模型，纯本地降级演示
param(
    [string]$DeepSeekKey = "",
    [int]$Port = 8000,
    [switch]$Mock
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 本地演示用的会话密钥：每次启动随机生成（不落盘）；生产请用固定强随机值
if (-not $env:SECRET_KEY) {
    $env:SECRET_KEY = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
}

if ($Mock) {
    $env:MT_PROVIDER = "mock"
    $env:LLM_PROVIDER = "mock"
    Write-Host "[demo] 本地降级模式（不调用外部模型）" -ForegroundColor Yellow
} else {
    if (-not $DeepSeekKey) { $DeepSeekKey = $env:DEEPSEEK_API_KEY }
    if (-not $DeepSeekKey) {
        Write-Host "[demo] 未提供 DeepSeek Key：翻译将使用 MyMemory 免费端口（额度可能耗尽），问答为检索摘录模式。" -ForegroundColor Yellow
        Write-Host "       如需真实翻译：.\start_demo.ps1 -DeepSeekKey \"sk-...\"" -ForegroundColor Yellow
    } else {
        $env:DEEPSEEK_API_KEY = $DeepSeekKey
        $env:MT_PROVIDER = "deepseek"
        $env:LLM_PROVIDER = "deepseek"
        Write-Host "[demo] 已启用 DeepSeek：翻译与问答走真实模型" -ForegroundColor Green
    }
}

Write-Host "[demo] http://127.0.0.1:$Port" -ForegroundColor Cyan
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port $Port