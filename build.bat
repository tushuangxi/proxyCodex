@echo off
chcp 65001 >nul
title proxyCodex — 打包 EXE
cd /d "%~dp0"

echo ========================================
echo   proxyCodex — 打包为 EXE
echo ========================================
echo.

:: 检查 PyInstaller
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [..] 安装 PyInstaller...
    pip install pyinstaller
    if errorlevel 1 (
        echo [FAIL] 安装失败，请手动运行: pip install pyinstaller
        pause
        exit /b 1
    )
)

:: 检查 UPX（可选压缩工具）
where upx >nul 2>&1 && set UPX_FLAG=--upx-dir="%PATH%" || set UPX_FLAG=

:: 打包
echo [..] 正在打包 proxyCodex.exe...
pyinstaller --onefile --console ^
    --name proxyCodex ^
    --add-data "providers.json;." ^
    --add-data "config.toml.template;." ^
    --distpath dist ^
    --workpath build ^
    --specpath . ^
    proxyCodex.py

if errorlevel 1 (
    echo [FAIL] 打包失败
    pause
    exit /b 1
)

echo.
echo [OK] 打包完成！
echo     输出文件: %~dp0dist\proxyCodex.exe
echo     大小:
dir "%~dp0dist\proxyCodex.exe" 2>nul

echo.
echo 使用方法:
echo   proxyCodex.exe          启动代理
echo   proxyCodex.exe --setup 首次配置
echo.
pause
