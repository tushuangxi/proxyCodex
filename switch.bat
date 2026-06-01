@echo off
chcp 65001 >nul
title proxyCodex — 切换提供商
cd /d "%~dp0"

if "%1"=="" (
    echo ========================================
    echo   proxyCodex — 切换提供商
    echo ========================================
    echo.
    echo  用法: switch deepseek
    echo        switch moonshot
    echo.
    pause
    exit /b
)

:: 停止旧代理
echo [..] 关闭旧代理...
taskkill /f /im python.exe >nul 2>&1
timeout /t 2 >nul

:: 运行配置
python proxyCodex.py --setup

echo.
echo [OK] 已切换到新提供商
echo [..] 请重新运行 start.bat 启动
pause
