import asyncio
import os
import tempfile
import time
from pathlib import Path
from typing import Optional


class RecorderError(Exception):
    pass


class Recorder:
    """
    采集与控制层 — 封装 Playwright 浏览器自动化引擎。
    """

    def __init__(self):
        self._browser = None
        self._context = None
        self._page = None
        self._tracing = False
        self._trace_path: Optional[str] = None
        self._start_time: float = 0.0
        self._request_count: int = 0

    @property
    def is_recording(self) -> bool:
        return self._tracing

    async def start(self, url: str, headless: bool = False) -> None:
        """启动浏览器并导航到目标 URL，开启 Tracing。"""
        if self._tracing:
            raise RecorderError("已在录制中")

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RecorderError("请先安装 Playwright: pip install playwright && playwright install chromium")

        self._pw = await async_playwright().start()
        try:
            self._browser = await self._pw.chromium.launch(
                headless=headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            self._context = await self._browser.new_context(
                viewport={"width": 1280, "height": 720},
                record_video_dir=None,
            )
            self._page = await self._context.new_page()
            self._request_count = 0
            self._page.on("request", lambda _: setattr(self, "_request_count", self._request_count + 1))

            fd, self._trace_path = tempfile.mkstemp(suffix=".zip", prefix="recorder_trace_")
            os.close(fd)

            await self._context.tracing.start(
                screenshots=True,
                snapshots=True,
                sources=True,
            )

            self._start_time = time.time()
            self._tracing = True

            await self._page.goto(url, wait_until="domcontentloaded")
        except Exception as e:
            await self._cleanup()
            raise RecorderError(f"浏览器启动失败: {e}")

    async def stop(self) -> str:
        """
        停止录制，关闭 Tracing 并保存 trace 文件。
        返回 trace 文件路径。
        """
        if not self._tracing:
            raise RecorderError("未在录制中")

        try:
            await self._context.tracing.stop(path=self._trace_path)
        except Exception as e:
            raise RecorderError(f"Tracing 关闭失败: {e}")
        finally:
            await self._cleanup()

        self._tracing = False
        return self._trace_path

    async def get_captured_count(self) -> int:
        """返回当前已捕获的请求数量（通过 Playwright 路由监听）。"""
        return self._request_count

    async def _cleanup(self):
        """清理浏览器资源。"""
        try:
            if self._page:
                await self._page.close()
        except Exception:
            pass
        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass
        self._page = None
        self._context = None
        self._browser = None
        self._pw = None
