@echo off
chcp 65001 >nul
title RecorderAnalyzer 构建工具

echo ============================================
echo  RecorderAnalyzer Windows 打包脚本
echo ============================================
echo.

REM 检查 Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

REM 检查并创建虚拟环境
if not exist ".venv\" (
    echo [1/5] 创建虚拟环境...
    python -m venv .venv
)

echo [2/5] 安装依赖...
call .venv\Scripts\pip install -r requirements.txt pyinstaller
if %errorlevel% neq 0 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

REM 下载浏览器
echo [3/5] 下载 Playwright Chromium 到 browser\...
if not exist "browser\" mkdir browser
set PLAYWRIGHT_BROWSERS_PATH=%CD%\browser
call .venv\Scripts\python -m playwright install chromium
if %errorlevel% neq 0 (
    echo [警告] 浏览器下载失败，运行时将自动下载
)

echo [4/5] 清理旧构建...
if exist "dist\" rmdir /s /q dist
if exist "build\" rmdir /s /q build
if exist "RecorderAnalyzer.spec" del RecorderAnalyzer.spec

echo [5/5] 打包中...
call .venv\Scripts\pyinstaller --onefile --name RecorderAnalyzer ^
    --add-data "core;core" ^
    --add-data "ui;ui" ^
    --add-data "fonts;fonts" ^
    --hidden-import core ^
    --hidden-import ui ^
    --hidden-import core.models ^
    --hidden-import core.analyzer ^
    --hidden-import core.generator ^
    --hidden-import core.executor ^
    --hidden-import core.recorder ^
    --hidden-import ui.panels ^
    --hidden-import ui.app ^
    --collect-all flet ^
    --collect-all playwright ^
    --noconfirm ^
    main.py

if %errorlevel% equ 0 (
    REM 复制浏览器到输出目录
    if exist "browser\" (
        echo [INFO] 复制 browser\ 到 dist\browser\...
        xcopy /E /I /Q browser dist\browser >nul
    )
    echo.
    echo ============================================
    echo  构建成功！
    echo  可执行文件: dist\RecorderAnalyzer.exe
    echo ============================================
) else (
    echo [错误] 打包失败
)

pause
