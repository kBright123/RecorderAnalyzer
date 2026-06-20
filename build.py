#!/usr/bin/env python3
"""
跨平台构建脚本 — 自动打包 RecorderAnalyzer 为可执行文件。
用法:
    python build.py                  # 构建当前平台
    python build.py --onefile        # 单文件模式（默认）
    python build.py --onedir         # 目录模式
"""
import os
import sys
import subprocess
import shutil
import platform

APP_NAME = "RecorderAnalyzer"
MAIN_SCRIPT = "main.py"


def ensure_venv():
    if os.environ.get("VIRTUAL_ENV"):
        return
    venv_dir = os.path.join(os.path.dirname(__file__), ".venv")
    if not os.path.exists(venv_dir):
        print("[build] Creating virtual environment...")
        subprocess.check_call([sys.executable, "-m", "venv", venv_dir])
    pip = os.path.join(venv_dir, "bin", "pip") if os.name != "nt" else os.path.join(venv_dir, "Scripts", "pip")
    print("[build] Installing dependencies...")
    subprocess.check_call([pip, "install", "-r", "requirements.txt", "pyinstaller"])


def build(mode: str = "onefile"):
    print(f"[build] Packaging {APP_NAME} for {platform.system()} ({mode})")

    dist_dir = os.path.join(os.path.dirname(__file__), "dist")
    build_dir = os.path.join(os.path.dirname(__file__), "build")
    spec_file = os.path.join(os.path.dirname(__file__), f"{APP_NAME}.spec")

    for d in [dist_dir, build_dir]:
        os.makedirs(d, exist_ok=True)

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
        "--noconfirm",
        MAIN_SCRIPT,
    ]

    print(f"[build] Running: {' '.join(cmd)}")
    subprocess.check_call(cmd, cwd=os.path.dirname(__file__))

    print(f"[build] Done! Executable in: {dist_dir}")


def clean():
    for d in ["build", "dist"]:
        path = os.path.join(os.path.dirname(__file__), d)
        if os.path.exists(path):
            shutil.rmtree(path)
            print(f"[build] Removed {d}")
    spec = os.path.join(os.path.dirname(__file__), f"{APP_NAME}.spec")
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
    parser.add_argument("--no-venv", action="store_true",
                        help="Skip virtual environment setup")
    args = parser.parse_args()

    if args.action == "clean":
        clean()
    else:
        if not args.no_venv:
            ensure_venv()
        mode = "onedir" if args.onedir else "onefile"
        build(mode)
