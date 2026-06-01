@echo off
chcp 65001 >nul
title proxyCodex
cd /d "%~dp0"

echo ========================================
echo   proxyCodex — 一键启动
echo ========================================

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [FAIL] 未检测到 Python，请安装 Python 3.8+
    pause
    exit /b 1
)

:: 检查是否已配置
python proxyCodex.py --check-config >nul 2>&1
if errorlevel 1 (
    echo [..] 首次使用，进入配置模式...
    python proxyCodex.py --setup
    if errorlevel 1 (
        pause
        exit /b 1
    )
)

:: 启动代理（最小化窗口）
echo [..] 启动代理...
start /min "proxyCodex" python "%~dp0proxyCodex.py"

:: 等待代理就绪
echo [..] 等待代理就绪...
setlocal enabledelayedexpansion
set count=0
:wait_loop
python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3000/v1/models', timeout=2)" >nul 2>&1
if errorlevel 1 (
    set /a count+=1
    if !count! geq 15 (
        echo [FAIL] 代理启动超时
        endlocal
        pause
        exit /b 1
    )
    timeout /t 1 >nul
    goto wait_loop
)
endlocal
echo [OK] 代理已就绪

:: 查找并启动 Codex
set "CODEX_PATHS=D:\360download\AI 工具箱\codex.exe;C:\Program Files\Codex\codex.exe;C:\Users\%USERNAME%\AppData\Local\Programs\Codex\codex.exe"
for %%p in ("%CODEX_PATHS:;=";"%") do (
    if exist "%%~p" (
        echo [OK] 启动 Codex: %%~p
        start "" "%%~p"
        goto :done
    )
)

echo [WARN] 未找到 Codex，请手动启动 codex.exe
echo        代理已在后台运行（端口 3000）

:done
echo ========================================
echo  关闭 Codex 后请手动关闭代理窗口
echo ========================================
