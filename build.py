#!/usr/bin/env python3
"""
跨平台构建脚本 — 自动打包 RecorderAnalyzer 为可执行文件。

用法:
    python build.py                  # 构建当前平台（含浏览器）
    python build.py --onefile        # 单文件模式（默认）
    python build.py --onedir         # 目录模式
    python build.py --no-browser     # 跳过浏览器下载
    python build.py clean            # 清理
"""
import os
import sys
import subprocess
import shutil
import platform

APP_NAME = "RecorderAnalyzer"
MAIN_SCRIPT = "main.py"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def ensure_venv():
    if os.environ.get("VIRTUAL_ENV"):
        return
    venv_dir = os.path.join(BASE_DIR, ".venv")
    if not os.path.exists(venv_dir):
        print("[build] Creating virtual environment...")
        subprocess.check_call([sys.executable, "-m", "venv", venv_dir])
    pip = os.path.join(venv_dir, "bin", "pip") if os.name != "nt" else os.path.join(venv_dir, "Scripts", "pip")
    print("[build] Installing dependencies...")
    subprocess.check_call([pip, "install", "-r", "requirements.txt", "pyinstaller"])


def download_browser():
    browser_dir = os.path.join(BASE_DIR, "browser")
    os.makedirs(browser_dir, exist_ok=True)
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = browser_dir
    print(f"[build] Downloading Playwright Chromium to {browser_dir} ...")
    subprocess.check_call(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        env=env,
    )
    size = sum(
        os.path.getsize(os.path.join(dirpath, f))
        for dirpath, _, filenames in os.walk(browser_dir)
        for f in filenames
    )
    print(f"[build] Browser downloaded: {size / 1024 / 1024:.0f} MB")


def build(mode: str = "onefile", with_browser: bool = True):
    print(f"[build] Packaging {APP_NAME} for {platform.system()} ({mode})")

    dist_dir = os.path.join(BASE_DIR, "dist")
    build_dir = os.path.join(BASE_DIR, "build")

    for d in [dist_dir, build_dir]:
        os.makedirs(d, exist_ok=True)

    # Download browser first
    if with_browser:
        if not os.path.isdir(os.path.join(BASE_DIR, "browser")):
            download_browser()
        else:
            print("[build] Browser already downloaded")

    pyinstaller = "pyinstaller"
    if os.environ.get("VIRTUAL_ENV"):
        pyinstaller = os.path.join(os.environ["VIRTUAL_ENV"], "bin", "pyinstaller")
        if os.name == "nt":
            pyinstaller = os.path.join(os.environ["VIRTUAL_ENV"], "Scripts", "pyinstaller")

    cmd = [
        pyinstaller,
        f"--{mode}",
        "--name", APP_NAME,
        "--add-data", f"core{os.pathsep}core",
        "--add-data", f"ui{os.pathsep}ui",
        "--add-data", f"fonts{os.pathsep}fonts",
        "--hidden-import", "core",
        "--hidden-import", "ui",
        "--hidden-import", "core.models",
        "--hidden-import", "core.analyzer",
        "--hidden-import", "core.generator",
        "--hidden-import", "core.executor",
        "--hidden-import", "core.recorder",
        "--hidden-import", "ui.panels",
        "--hidden-import", "ui.app",
        "--collect-all", "flet",
        "--collect-all", "playwright",
        "--noconfirm",
        MAIN_SCRIPT,
    ]

    print(f"[build] Running PyInstaller...")
    subprocess.check_call(cmd, cwd=BASE_DIR)

    # Copy browser to dist
    if with_browser:
        src_browser = os.path.join(BASE_DIR, "browser")
        if os.path.isdir(src_browser) and os.listdir(src_browser):
            dst_browser = os.path.join(dist_dir, "browser")
            print(f"[build] Copying browser to {dst_browser} ...")
            if os.path.exists(dst_browser):
                shutil.rmtree(dst_browser)
            shutil.copytree(src_browser, dst_browser)
            print("[build] Browser bundled for offline use")

    print(f"[build] Done! Executable in: {dist_dir}")


def clean():
    for d in ["build", "dist"]:
        path = os.path.join(BASE_DIR, d)
        if os.path.exists(path):
            shutil.rmtree(path)
            print(f"[build] Removed {d}")
    spec = os.path.join(BASE_DIR, f"{APP_NAME}.spec")
    if os.path.exists(spec):
        os.remove(spec)
        print(f"[build] Removed {APP_NAME}.spec")
    print("[build] Clean complete")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Build RecorderAnalyzer executable")
    parser.add_argument("action", nargs="?", default="build", choices=["build", "clean"],
                        help="build or clean (default: build)")
    parser.add_argument("--onefile", action="store_true", default=True,
                        help="Build as single executable (default)")
    parser.add_argument("--onedir", action="store_true",
                        help="Build as directory")
    parser.add_argument("--no-browser", action="store_true",
                        help="Skip downloading/bundling Chromium")
    parser.add_argument("--no-venv", action="store_true",
                        help="Skip virtual environment setup")
    args = parser.parse_args()

    if args.action == "clean":
        clean()
    else:
        if not args.no_venv:
            ensure_venv()
        mode = "onedir" if args.onedir else "onefile"
        build(mode, with_browser=not args.no_browser)
