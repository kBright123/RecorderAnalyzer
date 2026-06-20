import json
import time
from typing import Optional

import flet as ft

from core.models import AnalysisResult, ActionEvent, RequestEvent, CorrelationMap, VariableDep


class ToolBar(ft.Container):
    """顶部控制栏。"""

    STATUS_ICONS = {
        "idle": ft.Icons.RADIO_BUTTON_UNCHECKED,
        "recording": ft.Icons.FIBER_MANUAL_RECORD,
        "analyzing": ft.Icons.HOURGLASS_TOP,
        "done": ft.Icons.CHECK_CIRCLE,
    }
    STATUS_COLORS = {
        "idle": ft.Colors.GREY,
        "recording": ft.Colors.RED,
        "analyzing": ft.Colors.ORANGE,
        "done": ft.Colors.GREEN,
    }

    def __init__(self, on_start, on_stop, on_execute, on_export, on_save=None, on_load=None, on_window_change=None):
        self._url_input = ft.TextField(
            hint_text="输入起始 URL，如 https://example.com",
            expand=True,
            height=48,
            text_size=16,
        )
        self._start_btn = ft.Button(content=ft.Text("开始录制"), icon=ft.Icons.PLAY_ARROW, on_click=on_start)
        self._stop_btn = ft.Button(content=ft.Text("停止录制"), icon=ft.Icons.STOP, disabled=True, on_click=on_stop)
        self._execute_btn = ft.Button(content=ft.Text("执行"), icon=ft.Icons.PLAY_CIRCLE_FILLED, disabled=True, on_click=on_execute)
        self._export_btn = ft.Button(content=ft.Text("导出 Postman"), icon=ft.Icons.FILE_DOWNLOAD, disabled=True, on_click=on_export)
        self._save_btn = ft.Button(content=ft.Text("保存"), icon=ft.Icons.SAVE, disabled=True, on_click=on_save)
        self._load_btn = ft.Button(content=ft.Text("加载"), icon=ft.Icons.FOLDER_OPEN, on_click=on_load)
        self._status_icon = ft.Icon(self.STATUS_ICONS["idle"], color=self.STATUS_COLORS["idle"])
        self._status_text = ft.Text("空闲中", size=14)
        self._count_text = ft.Text("", size=14, color=ft.Colors.GREY)
        self._window_input = ft.TextField(
            hint_text="时间窗(ms)",
            value="5000",
            width=100,
            height=36,
            text_size=12,
            on_change=lambda e: on_window_change(int(e.control.value)) if on_window_change and e.control.value.isdigit() else None,
        )

        bar = ft.Row([
            self._url_input,
            self._start_btn,
            self._stop_btn,
            ft.VerticalDivider(width=1, visible=False),
            self._execute_btn,
            self._export_btn,
            self._save_btn,
            self._load_btn,
            ft.VerticalDivider(),
            ft.Text("窗口", size=12),
            self._window_input,
            ft.VerticalDivider(),
            self._status_icon,
            self._status_text,
            self._count_text,
        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        super().__init__(content=bar, padding=10, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST)

    def get_url(self) -> str:
        return self._url_input.value or ""

    def set_status(self, status: str, count: int = 0):
        self._status_icon.name = self.STATUS_ICONS.get(status, self.STATUS_ICONS["idle"])
        self._status_icon.color = self.STATUS_COLORS.get(status, self.STATUS_COLORS["idle"])
        labels = {"idle": "空闲中", "recording": "录制中", "analyzing": "分析中", "done": "已完成"}
        self._status_text.value = labels.get(status, status)
        self._count_text.value = f"已捕获 {count} 请求" if status == "recording" else ""
        self._start_btn.disabled = status == "recording"
        self._stop_btn.disabled = status != "recording"
        is_done = status == "done"
        self._execute_btn.disabled = not is_done
        self._export_btn.disabled = not is_done
        self._save_btn.disabled = not is_done
        self.update()

    def set_buttons_enabled(self, execute: bool = True, export: bool = True, save: bool = True):
        self._execute_btn.disabled = not execute
        self._export_btn.disabled = not export
        self._save_btn.disabled = not save


class ActionTimeline(ft.Container):
    """左侧操作时间线。"""

    def __init__(self):
        self._list_view = ft.ListView(spacing=2, expand=True)
        self._actions: list[ActionEvent] = []
        self._selected_idx: Optional[int] = None
        self._on_select = None

        super().__init__(
            content=ft.Column([
                ft.Text("操作时间线", size=16, weight=ft.FontWeight.BOLD),
                self._list_view,
            ], spacing=4, expand=True),
            width=280,
            padding=8,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST,
        )

    def set_actions(self, actions: list[ActionEvent], on_select):
        self._actions = actions
        self._on_select = on_select
        self._list_view.controls.clear()
        for i, act in enumerate(actions):
            btn = ft.TextButton(
                content=ft.Row([
                    ft.Icon(self._type_icon(act.action_type), size=18),
                    ft.Column([
                        ft.Text(act.action_type, size=13, weight=ft.FontWeight.BOLD),
                        ft.Text(act.description[:50], size=12, color=ft.Colors.GREY_700),
                    ], spacing=0, tight=True),
                ], spacing=6, tight=True),
                on_click=lambda e, idx=i: self._select_action(idx),
                data=i,
            )
            self._list_view.controls.append(btn)
        self.update()

    def _type_icon(self, t: str) -> ft.Icons:
        return {
            "Click": ft.Icons.TOUCH_APP,
            "Input": ft.Icons.KEYBOARD,
            "Navigation": ft.Icons.OPEN_IN_BROWSER,
            "Scroll": ft.Icons.SWIPE_VERTICAL,
        }.get(t, ft.Icons.CIRCLE)

    def _select_action(self, idx: int):
        self._selected_idx = idx
        for i, ctrl in enumerate(self._list_view.controls):
            ctrl.bgcolor = ft.Colors.TERTIARY_CONTAINER if i == idx else None
        self.update()
        if self._on_select and 0 <= idx < len(self._actions):
            self._on_select(self._actions[idx])


class RequestWaterfall(ft.Container):
    """右侧请求瀑布流。"""

    def __init__(self):
        self._list_view = ft.ListView(spacing=2, expand=True)
        self._requests: list[RequestEvent] = []
        self._highlighted_ids: set[str] = set()
        self._on_select = None

        self._search_field = ft.TextField(
            hint_text="搜索 URL...",
            height=36,
            text_size=13,
            expand=True,
            on_change=lambda e: self._apply_filter(),
        )

        header = ft.Row([
            ft.Text("方法", size=13, weight=ft.FontWeight.BOLD, width=60),
            ft.Text("URL", size=13, weight=ft.FontWeight.BOLD, expand=True),
            ft.Text("状态", size=13, weight=ft.FontWeight.BOLD, width=60),
            ft.Text("耗时", size=13, weight=ft.FontWeight.BOLD, width=70),
        ], spacing=4)

        super().__init__(
            content=ft.Column([self._search_field, header, self._list_view], spacing=4, expand=True),
            expand=True,
            padding=8,
        )

    def set_requests(self, requests: list[RequestEvent], on_select):
        self._requests = requests
        self._on_select = on_select
        self._list_view.controls.clear()
        self._build_all_rows()
        self._apply_filter()

    def _build_all_rows(self):
        self._rows = []
        self._filtered_indices = []
        for i, req in enumerate(self._requests):
            path = self._short_path(req.url)
            method_color = {
                "GET": ft.Colors.BLUE, "POST": ft.Colors.GREEN,
                "PUT": ft.Colors.ORANGE, "DELETE": ft.Colors.RED,
                "PATCH": ft.Colors.PURPLE,
            }.get(req.method, ft.Colors.GREY)

            duration_text = f"{req.duration:.0f}ms" if req.duration > 0 else "—"

            row = ft.Container(
                content=ft.Row([
                    ft.Text(req.method, size=12, color=method_color, weight=ft.FontWeight.BOLD, width=60),
                    ft.Text(path, size=12, expand=True),
                    ft.Text(str(req.response_status), size=12, width=60),
                    ft.Text(duration_text, size=12, width=70),
                ], spacing=4, tight=True),
                padding=4,
                border_radius=4,
            )
            row.on_click = lambda e, idx=i: self._on_select(self._requests[idx]) if self._on_select else None
            self._rows.append(row)

    def _apply_filter(self):
        query = self._search_field.value or ""
        self._list_view.controls.clear()
        self._filtered_indices = []
        for i, req in enumerate(self._requests):
            if query.lower() in req.url.lower() or query.lower() in req.method.lower() or query.lower() in str(req.response_status):
                self._filtered_indices.append(i)
                row = self._rows[i]
                row.bgcolor = ft.Colors.TERTIARY_CONTAINER if req.id in self._highlighted_ids else None
                self._list_view.controls.append(row)
        self.update()

    def highlight_for_action(self, request_ids: list[str]):
        self._highlighted_ids = set(request_ids)
        self._refresh_highlight()

    def clear_highlight(self):
        self._highlighted_ids.clear()
        self._refresh_highlight()

    def highlight_for_variable(self, variables: list[VariableDep], all_requests: list[RequestEvent]):
        ids = set()
        for var in variables:
            ids.update(var.referenced_by)
        self._highlighted_ids = ids
        self._refresh_highlight()

    def _refresh_highlight(self):
        for i in self._filtered_indices:
            req = self._requests[i]
            self._rows[i].bgcolor = ft.Colors.TERTIARY_CONTAINER if req.id in self._highlighted_ids else None
        self.update()

    @staticmethod
    def _short_path(url: str) -> str:
        from urllib.parse import urlparse
        p = urlparse(url)
        path = p.path or "/"
        if len(path) > 60:
            path = path[:57] + "..."
        return path


class DetailPanel(ft.Container):
    """底部详情面板（多标签页）。"""

    def __init__(self):
        self._request_detail = ft.Column([ft.Text("选择请求以查看详情", italic=True)], scroll="auto", expand=True)
        self._variable_list = ft.Column([ft.Text("无变量", italic=True)], scroll="auto", expand=True)
        self._dep_graph = ft.Column([ft.Text("无依赖关系", italic=True)], scroll="auto", expand=True)
        self._exec_result = ft.Column([ft.Text("尚未执行", italic=True)], scroll="auto", expand=True)

        tabs = []
        for label, container in (
            ("报文详情", ft.Container(self._request_detail, padding=8, expand=True)),
            ("关联变量", ft.Container(self._variable_list, padding=8, expand=True)),
            ("依赖图谱", ft.Container(self._dep_graph, padding=8, expand=True)),
            ("执行结果", ft.Container(self._exec_result, padding=8, expand=True)),
        ):
            t = ft.Tab(label)
            t.content = container
            tabs.append(t)
        self._tabs = ft.Tabs(content=tabs, length=len(tabs), selected_index=0, expand=True)

        super().__init__(
            content=self._tabs,
            height=250,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST,
            border=ft.Border(top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
        )

    def show_request(self, req: Optional[RequestEvent]):
        self._request_detail.controls.clear()
        if not req:
            self._request_detail.controls.append(ft.Text("选择请求以查看详情", italic=True))
            self.update()
            return

        parts = [
            ft.Text(f"URL: {req.url}", size=14, selectable=True),
            ft.Text(f"Method: {req.method}  Status: {req.response_status}", size=14),
            ft.Text("请求头:", size=14, weight=ft.FontWeight.BOLD),
            ft.Text(json.dumps(req.request_headers, ensure_ascii=False, indent=2), size=12, selectable=True, font_family="monospace"),
        ]
        if req.request_body:
            parts.append(ft.Text("请求体:", size=14, weight=ft.FontWeight.BOLD))
            try:
                pretty = json.dumps(json.loads(req.request_body), ensure_ascii=False, indent=2)
            except Exception:
                pretty = req.request_body
            parts.append(ft.Text(pretty, size=12, selectable=True, font_family="monospace"))

        if req.response_body:
            parts.append(ft.Text("响应体:", size=14, weight=ft.FontWeight.BOLD))
            try:
                pretty = json.dumps(json.loads(req.response_body), ensure_ascii=False, indent=2)
            except Exception:
                pretty = req.response_body[:2000]
            parts.append(ft.Text(pretty, size=12, selectable=True, font_family="monospace"))

        self._request_detail.controls.extend(parts)
        self._tabs.selected_index = 0
        self.update()

    def show_variables(self, variables: list[VariableDep], on_var_click=None):
        self._variable_list.controls.clear()
        if not variables:
            self._variable_list.controls.append(ft.Text("未提取到变量", italic=True))
            self.update()
            return

        for var in variables:
            card = ft.Container(
                content=ft.Column([
                    ft.Text(f"变量: {var.name}", size=14, weight=ft.FontWeight.BOLD),
                    ft.Text(f"值: {var.sample_value}", size=13),
                    ft.Text(f"来源: {var.source_request_id} → {var.source_json_path}", size=12, color=ft.Colors.GREY_700),
                    ft.Text(f"引用: {len(var.referenced_by)} 处", size=12),
                ], spacing=2),
                padding=8,
                border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                border_radius=4,
            )
            if on_var_click:
                card.on_click = lambda e, v=var: on_var_click(v)
            self._variable_list.controls.append(card)

        self._tabs.selected_index = 1
        self.update()

    def show_dep_graph(self, variables: list[VariableDep], result: AnalysisResult):
        self._dep_graph.controls.clear()
        if not variables:
            self._dep_graph.controls.append(ft.Text("无依赖关系", italic=True))
            self.update()
            return

        req_map = {r.id: r for r in result.requests}
        lines = []
        for var in variables:
            src = var.source_request_id
            src_path = self._short_url_path(req_map.get(src))
            lines.append(ft.Text(f"[{src}] {src_path}", size=13, weight=ft.FontWeight.BOLD))
            lines.append(ft.Text(f"  └ 提取 {var.name} = {var.sample_value}", size=12, color=ft.Colors.GREEN))
            for ref_id in var.referenced_by:
                ref_path = self._short_url_path(req_map.get(ref_id))
                lines.append(ft.Text(f"     → [{ref_id}] {ref_path}", size=12, color=ft.Colors.BLUE))
            lines.append(ft.Text(""))

        if lines:
            self._dep_graph.controls.extend(lines)
        else:
            self._dep_graph.controls.append(ft.Text("无依赖关系", italic=True))

        self._tabs.selected_index = 2
        self.update()

    def show_execution_results(self, results: list[dict]):
        self._exec_result.controls.clear()
        if not results:
            self._exec_result.controls.append(ft.Text("无执行结果", italic=True))
            self.update()
            return

        for r in results:
            status_color = ft.Colors.GREEN if r["success"] else ft.Colors.RED
            status_icon = ft.Icons.CHECK_CIRCLE if r["success"] else ft.Icons.ERROR
            lines = [
                ft.Row([
                    ft.Icon(status_icon, size=18, color=status_color),
                    ft.Text(f"[{r['method']}] {r['url'][:80]}", size=13, expand=True),
                ], spacing=4),
                ft.Row([
                    ft.Text(f"状态: {r['status'] or '-'}", size=12, color=status_color),
                    ft.Text(f"耗时: {r['duration_ms']}ms", size=12, color=ft.Colors.GREY_700),
                ], spacing=16),
            ]
            if r["error"]:
                lines.append(ft.Text(f"错误: {r['error']}", size=12, color=ft.Colors.RED))

            self._exec_result.controls.append(
                ft.Container(
                    content=ft.Column(lines, spacing=2),
                    padding=6,
                    border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                    border_radius=4,
                )
            )

        success_count = sum(1 for r in results if r["success"])
        summary = ft.Container(
            content=ft.Text(
                f"总计 {len(results)} 请求，成功 {success_count}，失败 {len(results) - success_count}",
                size=14, weight=ft.FontWeight.BOLD,
            ),
            padding=6,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border_radius=4,
        )
        self._exec_result.controls.insert(0, summary)
        self._tabs.selected_index = 3
        self.update()

    @staticmethod
    def _short_url_path(req: Optional[RequestEvent]) -> str:
        if not req:
            return "?"
        from urllib.parse import urlparse
        return urlparse(req.url).path or "/"
