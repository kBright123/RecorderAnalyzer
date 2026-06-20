import asyncio
import json
import threading

import flet as ft

from core.recorder import Recorder, RecorderError
from core.analyzer import Analyzer, AnalyzerError
from core.generator import generate_collection_json
from core.executor import Executor, ExecutorError
from core.models import ActionEvent, RequestEvent, VariableDep, CorrelationMap
from ui.panels import ToolBar, ActionTimeline, RequestWaterfall, DetailPanel


class RecorderApp:
    """
    主应用控制器 — 协调各模块与 UI 的交互。
    所有耗时操作（Playwright、分析）在后台线程执行，
    UI 更新通过 page.run_task / page.add 调度回主线程。
    """

    def __init__(self, page: ft.Page):
        self.page = page
        self._recorder = Recorder()
        self._analyzer = Analyzer(max_delta_ms=5000.0)
        self._executor = Executor()
        self._result = None
        self._last_trace_path = None
        self._snackbar = ft.SnackBar(ft.Text(""), duration=4000)
        self._file_picker = ft.FilePicker()
        self._file_picker.on_result = self._on_file_picked
        self._load_picker = ft.FilePicker()
        self._load_picker.on_result = self._on_load_picked
        self._save_picker = ft.FilePicker()
        self._save_picker.on_result = self._on_save_picked
        self._loop = None

        page.overlay.append(self._snackbar)
        page.overlay.append(self._file_picker)
        page.overlay.append(self._load_picker)
        page.overlay.append(self._save_picker)
        self._setup_page()

    def _setup_page(self):
        self.page.title = "操作-请求关联分析客户端"
        self.page.padding = 0
        self.page.spacing = 0
        self.page.window.width = 1400
        self.page.window.height = 900
        self.page.theme = ft.Theme(
            color_scheme=ft.ColorScheme(
                primary=ft.Colors.INDIGO,
                tertiary=ft.Colors.TEAL,
            ),
        )

        self.toolbar = ToolBar(
            on_start=lambda e: self._on_start(),
            on_stop=lambda e: self._on_stop(),
            on_execute=lambda e: self._on_execute(),
            on_export=lambda e: self._on_export(),
            on_save=lambda e: self._on_save(),
            on_load=lambda e: self._on_load(),
            on_window_change=lambda v: self._on_window_change(v),
        )
        self.timeline = ActionTimeline()
        self.waterfall = RequestWaterfall()
        self.detail = DetailPanel()

        self.timeline.set_actions([], on_select=self._on_action_select)
        self.waterfall.set_requests([], on_select=self._on_request_select)

        main_content = ft.Row(
            [self.timeline, ft.VerticalDivider(), self.waterfall],
            spacing=0,
            expand=True,
        )

        self.page.add(
            self.toolbar,
            ft.Divider(height=1, thickness=0),
            main_content,
            self.detail,
        )

        self._loop = asyncio.get_running_loop()

    # ────────────── 异步调度 ──────────────

    def _run_async(self, coro):
        """安全地将协程提交到主线程事件循环执行。"""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, self._loop)

    def _run_in_thread(self, target, on_done=None):
        """在后台线程执行 target()，完成后回调 on_done（主线程）。"""
        def _wrapper():
            try:
                result = target()
                if on_done:
                    self._run_async(on_done(result))
            except Exception as e:
                self._run_async(self._on_error(e))

        threading.Thread(target=_wrapper, daemon=True).start()

    async def _on_error(self, error: Exception):
        self._show_toast(str(error))
        self.toolbar.set_status("idle")

    # ────────────── 录制流程 ──────────────

    def _on_start(self):
        url = self.toolbar.get_url().strip()
        if not url:
            self._show_toast("请输入起始 URL")
            return
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url

        self.toolbar.set_status("recording")
        self.toolbar.set_buttons_enabled(execute=False, export=False)
        self.page.update()

        def _start():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._recorder.start(url))
            return None

        self._run_in_thread(_start, on_done=lambda _: self._start_polling())

    def _start_polling(self):
        if not self._recorder.is_recording:
            return
        self._run_async(self._poll_once())

    async def _poll_once(self):
        count = await self._recorder.get_captured_count()
        self.toolbar.set_status("recording", count=count)
        self.page.update()
        await asyncio.sleep(1)
        self._start_polling()

    def _on_stop(self):
        self.toolbar.set_status("analyzing")

        def _stop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            trace_path = loop.run_until_complete(self._recorder.stop())
            result = self._analyzer.analyze(trace_path)
            return (trace_path, result)

        self._run_in_thread(_stop, on_done=self._on_analysis_done)

    async def _on_analysis_done(self, data):
        trace_path, result = data
        self._last_trace_path = trace_path
        self._result = result

        self.toolbar.set_status("done", count=len(result.requests))
        self.timeline.set_actions(result.actions, on_select=self._on_action_select)
        self.waterfall.set_requests(result.requests, on_select=self._on_request_select)
        self.detail.show_variables(result.variables, on_var_click=self._on_var_click)
        self.detail.show_dep_graph(result.variables, result)

        if result.actions:
            self._on_action_select(result.actions[0])

    # ────────────── 交互回调 ──────────────

    def _on_action_select(self, action):
        if not self._result:
            return
        for c in self._result.correlations:
            if c.action_id == action.id:
                self.waterfall.highlight_for_action(c.request_ids)
                self.detail.show_request(None)
                return
        self.waterfall.clear_highlight()

    def _on_request_select(self, req: RequestEvent):
        self.detail.show_request(req)

    def _on_var_click(self, var: VariableDep):
        if not self._result:
            return
        self.waterfall.highlight_for_variable([var], self._result.requests)
        self.detail.show_request(None)

    def _on_export(self):
        if not self._result or not self._result.requests:
            self._show_toast("无数据可导出")
            return

        try:
            self._export_json = generate_collection_json(self._result, "录制分析 Collection")
        except Exception as ex:
            self._show_toast(f"生成失败: {ex}")
            return

        self._file_picker.save_file(
            file_name="collection.postman_collection.json",
            allowed_extensions=["json"],
        )

    def _on_file_picked(self, e):
        if e.path and hasattr(self, "_export_json"):
            try:
                with open(e.path, "w", encoding="utf-8") as f:
                    f.write(self._export_json)
                self._show_toast(f"已导出到 {e.path}")
            except Exception as ex:
                self._show_toast(f"写入失败: {ex}")

    def _show_toast(self, msg: str):
        self._snackbar.content = ft.Text(msg)
        self._snackbar.open = True
        self.page.update()

    # ────────────── 时间窗口 ──────────────

    def _on_window_change(self, value: int):
        self._analyzer = Analyzer(max_delta_ms=float(value))
        self._show_toast(f"关联时间窗口已设为 {value}ms")

    # ────────────── 保存/加载 ──────────────

    def _on_save(self):
        if not self._result:
            self._show_toast("无数据可保存")
            return
        self._save_picker.save_file(
            file_name="session.json",
            allowed_extensions=["json"],
        )

    async def _on_save_picked(self, e):
        if not e.path or not self._result:
            return
        try:
            with open(e.path, "w", encoding="utf-8") as f:
                f.write(self._result.to_json())
            self._show_toast(f"已保存到 {e.path}")
        except Exception as ex:
            self._show_toast(f"保存失败: {ex}")

    def _on_load(self):
        self._load_picker.pick_files(
            file_type="json",
            allow_multiple=False,
        )

    async def _on_load_picked(self, e):
        if not e.files:
            return
        path = e.files[0].path
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            from core.models import AnalysisResult
            self._result = AnalysisResult(
                actions=[ActionEvent(**a) for a in data.get("actions", [])],
                requests=[RequestEvent(**r) for r in data.get("requests", [])],
                correlations=[CorrelationMap(**c) for c in data.get("correlations", [])],
                variables=[VariableDep(**v) for v in data.get("variables", [])],
                orphan_requests=data.get("orphan_requests", []),
            )
            await self._on_analysis_done((None, self._result))
            self._show_toast(f"已加载 {path}")
        except Exception as ex:
            self._show_toast(f"加载失败: {ex}")

    # ────────────── 执行（流式进度） ──────────────

    def _on_execute(self):
        if not self._result or not self._result.requests:
            self._show_toast("无数据可执行")
            return

        self.toolbar.set_buttons_enabled(execute=False, export=False)
        self._show_toast("开始执行请求...")
        self.detail.show_execution_results([])

        partial_results = []

        def on_progress(result: dict):
            partial_results.append(result)
            self._run_async(self._on_execution_progress(partial_results))

        def _execute():
            self._executor.execute(self._result, progress_callback=on_progress)

        self._run_in_thread(_execute, on_done=lambda _: self._on_execution_done(partial_results))

    async def _on_execution_progress(self, results: list):
        self.detail.show_execution_results(results)

    async def _on_execution_done(self, results):
        self.detail.show_execution_results(results)
        self.toolbar.set_buttons_enabled(execute=True, export=True)

        success = sum(1 for r in results if r["success"])
        self._show_toast(f"执行完成: {success}/{len(results)} 成功")


def create_app(page: ft.Page):
    RecorderApp(page)
