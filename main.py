"""
操作-请求关联分析客户端 — 命令行入口

用法:
    python main.py
"""

import sys

import flet as ft

from ui.app import RecorderApp


def main(page: ft.Page):
    RecorderApp(page)


if __name__ == "__main__":
    try:
        ft.app(target=main, view=ft.AppView.FLET_APP)
    except KeyboardInterrupt:
        sys.exit(0)
