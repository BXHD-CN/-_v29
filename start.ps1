# 启动本地开发服务器（首次运行会自动建库、导入数据、生成切片）
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path .venv)) { python -m venv .venv }
./.venv/Scripts/python.exe -m pip install --quiet -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
if (-not (Test-Path data/app.db)) {
    ./.venv/Scripts/python.exe scripts/seed_public.py
    ./.venv/Scripts/python.exe scripts/build_slices.py
    ./.venv/Scripts/python.exe scripts/embed_chunks.py
}
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
