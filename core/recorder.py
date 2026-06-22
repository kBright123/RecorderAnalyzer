import asyncio
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

from core.models import RequestEvent


class RecorderError(Exception):
    pass


def _find_bundled_browser() -> Optional[str]:
    """查找工具目录下的 browser/ 目录（内网环境离线打包）。"""
    if "PLAYWRIGHT_BROWSERS_PATH" in os.environ:
        return os.environ["PLAYWRIGHT_BROWSERS_PATH"]
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).parent / "browser")
        # .deb 安装路径（FHS 标准）
        candidates.append(Path("/usr/share/RecorderAnalyzer/browser"))
    else:
        candidates.append(Path(__file__).resolve().parent.parent / "browser")
    for browser_dir in candidates:
        if browser_dir.is_dir() and any(browser_dir.iterdir()):
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_dir)
            return str(browser_dir)
    return None


# 模块加载时自动检测并设置浏览器路径
_find_bundled_browser()


class Recorder:
    """
    采集与控制层 — 封装 Playwright 浏览器自动化引擎。
    支持两种模式：
      - launch: 自动启动新浏览器 + Tracing
      - cdp:    连接到已有 Chromium，手动捕获请求
    """

    _BROWSER_CACHE = Path.home() / ".cache" / "ms-playwright"

    def __init__(self):
        self._browser = None
        self._context = None
        self._page = None
        self._pw = None
        self._tracing = False
        self._trace_path: Optional[str] = None
        self._start_time: float = 0.0
        self._request_count: int = 0
        self._mode: str = "launch"
        self._captured_requests: list[RequestEvent] = []
        self._pending: dict[int, dict] = {}
        self._req_seq: int = 0

    def _on_request_launch(self, request) -> None:
        self._request_count += 1

    @property
    def is_recording(self) -> bool:
        return self._tracing

    @property
    def mode(self) -> str:
        return self._mode

    @staticmethod
    def is_browser_installed() -> bool:
        if not Recorder._BROWSER_CACHE.is_dir():
            return False
        for d in Recorder._BROWSER_CACHE.iterdir():
            if d.name.startswith("chromium-") and not d.name.startswith("chromium_headless"):
                for binary in ("chrome-linux", "chrome-win", "chrome-mac", "chrome", "chrome.exe"):
                    if (d / binary).exists():
                        return True
                if any(d.iterdir()):
                    return True
        return False

    @staticmethod
    def ensure_browser(progress_callback: Optional[Callable[[str], None]] = None) -> None:
        if Recorder.is_browser_installed():
            return

        proc = subprocess.Popen(
            [sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )

        if progress_callback:
            progress_callback("正在下载 Playwright Chromium ...")

        for line in proc.stdout or []:
            line = line.strip()
            if line:
                if progress_callback:
                    progress_callback(line)
                sys.stdout.flush()

        proc.wait(timeout=300)
        if proc.returncode != 0:
            raise RecorderError("浏览器安装失败")
        if not Recorder.is_browser_installed():
            raise RecorderError("浏览器安装后仍无法检测到")

    async def start(self, url: str, headless: bool = False) -> None:
        """启动新浏览器并导航到目标 URL（launch 模式）。"""
        if self._tracing:
            raise RecorderError("已在录制中")
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RecorderError("请先安装 Playwright: pip install playwright")

        self._mode = "launch"
        self._pw = await async_playwright().start()
        try:
            self._browser = await self._pw.chromium.launch(
                headless=headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            self._context = await self._browser.new_context(
                viewport={"width": 1280, "height": 720},
            )
            self._page = await self._context.new_page()
            self._request_count = 0
            self._page.on("request", self._on_request_launch)

            fd, self._trace_path = tempfile.mkstemp(suffix=".zip", prefix="recorder_trace_")
            os.close(fd)

            await self._context.tracing.start(
                screenshots=True, snapshots=True, sources=True,
            )
            self._start_time = time.time()
            self._tracing = True
            await self._page.goto(url, wait_until="domcontentloaded")
        except Exception as e:
            await self._cleanup()
            raise RecorderError(f"浏览器启动失败: {e}")

    async def start_cdp(self, port: int = 9222) -> None:
        """连接到已有的 Chromium 实例（CDP 模式），手动捕获请求。"""
        if self._tracing:
            raise RecorderError("已在录制中")
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RecorderError("请先安装 Playwright: pip install playwright")

        self._mode = "cdp"
        self._pw = await async_playwright().start()
        try:
            self._browser = await self._pw.chromium.connect_over_cdp(
                f"http://127.0.0.1:{port}"
            )
            contexts = self._browser.contexts
            if contexts:
                self._context = contexts[0]
            else:
                self._context = await self._browser.new_context()

            pages = self._context.pages
            self._page = pages[0] if pages else await self._context.new_page()

            self._setup_capture()
            self._start_time = time.time()
            self._tracing = True
        except Exception as e:
            await self._cleanup()
            raise RecorderError(f"CDP 连接失败 (端口 {port}): {e}")

    def _setup_capture(self):
        """设置请求/响应监听器（CDP 模式），手动构建 RequestEvent。"""
        self._captured_requests = []
        self._pending = {}
        self._req_seq = 0

        async def on_request(req):
            self._req_seq += 1
            seq = self._req_seq
            body = None
            if req.method in ("POST", "PUT", "PATCH"):
                try:
                    body = await req.body()
                except Exception:
                    pass
            self._pending[id(req)] = {
                "seq": seq,
                "url": req.url,
                "method": req.method,
                "request_headers": dict(req.headers),
                "request_body": body.decode(errors="replace") if body else None,
                "start_time": time.perf_counter(),
            }
            self._request_count += 1

        async def on_response(resp):
            entry = self._pending.pop(id(resp.request), None)
            if not entry:
                return
            resp_body = None
            try:
                body = await resp.body()
                if body:
                    resp_body = body.decode(errors="replace")[:50000]
            except Exception:
                pass
            duration = (time.perf_counter() - entry["start_time"]) * 1000
            req_event = RequestEvent(
                id=f"cdp_req_{entry['seq']}",
                timestamp=(entry["start_time"] - self._start_time) * 1000,
                url=entry["url"],
                method=entry["method"],
                request_headers=entry["request_headers"],
                request_body=entry["request_body"],
                response_status=resp.status,
                response_headers=dict(resp.headers),
                response_body=resp_body,
                duration=duration,
                session_id="",
            )
            self._captured_requests.append(req_event)

        self._page.on("request", on_request)
        self._page.on("response", on_response)

    async def stop(self) -> str:
        """停止录制。launch 模式返回 trace 路径；CDP 模式返回空字符串。"""
        if not self._tracing:
            raise RecorderError("未在录制中")

        if self._mode == "launch":
            try:
                await self._context.tracing.stop(path=self._trace_path)
            except Exception as e:
                raise RecorderError(f"Tracing 关闭失败: {e}")
            finally:
                await self._cleanup()
            self._tracing = False
            return self._trace_path
        else:
            await self._cleanup()
            self._tracing = False
            return ""

    def get_captured_requests(self) -> list[RequestEvent]:
        """返回 CDP 模式下捕获的请求列表。launch 模式下返回空列表。"""
        return self._captured_requests if self._mode == "cdp" else []

    async def get_captured_count(self) -> int:
        return self._request_count

    async def _cleanup(self):
        for obj in ("_page", "_context", "_browser", "_pw"):
            try:
                attr = getattr(self, obj, None)
                if attr:
                    if obj == "_page":
                        await attr.close()
                    elif obj == "_context":
                        await attr.close()
                    elif obj == "_browser":
                        await attr.close()
                    elif obj == "_pw":
                        await attr.stop()
            except Exception:
                pass
        self._page = None
        self._context = None
        self._browser = None
        self._pw = None
