import json
import re
from collections import deque
from typing import Optional

import httpx

from core.models import AnalysisResult, VariableDep, RequestEvent


class ExecutorError(Exception):
    pass


class Executor:
    """
    HTTP 执行器 — 根据分析结果按依赖顺序发送请求。
    """

    def __init__(self, max_retries: int = 2):
        self._client = httpx.Client(timeout=30.0, follow_redirects=True)
        self._max_retries = max_retries

    def execute(self, result: AnalysisResult, progress_callback=None) -> list[dict]:
        """
        按依赖顺序执行所有请求，返回每步的执行结果。

        返回列表，每项:
          {
            "request_id": str,
            "url": str,
            "method": str,
            "status": int | None,
            "success": bool,
            "error": str | None,
            "response_body": str | None,
            "duration_ms": float,
          }
        """
        if not result.requests:
            raise ExecutorError("无请求可执行")

        ordered = self._resolve_order(result)
        var_store: dict[str, str] = {
            v.name: v.sample_value for v in result.variables
        }
        outputs: list[dict] = []

        for req in ordered:
            result_dict = self._execute_one(req, result, var_store)
            outputs.append(result_dict)
            if progress_callback:
                progress_callback(result_dict)

        return outputs

    def _resolve_order(self, result: AnalysisResult) -> list[RequestEvent]:
        """
        拓扑排序：消费变量的请求排在对应生产者之后。
        """
        req_map = {r.id: r for r in result.requests}
        var_producer: dict[str, str] = {}
        for v in result.variables:
            var_producer[v.name] = v.source_request_id

        in_degree: dict[str, int] = {r.id: 0 for r in result.requests}
        graph: dict[str, list[str]] = {r.id: [] for r in result.requests}

        for v in result.variables:
            producer = v.source_request_id
            for consumer_id in v.referenced_by:
                if producer in graph and consumer_id in graph and producer != consumer_id:
                    graph[producer].append(consumer_id)
                    in_degree[consumer_id] = in_degree.get(consumer_id, 0) + 1

        queue = deque([rid for rid, deg in in_degree.items() if deg == 0])
        sorted_ids: list[str] = []

        while queue:
            rid = queue.popleft()
            sorted_ids.append(rid)
            for neighbor in graph.get(rid, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        remaining = [r.id for r in result.requests if r.id not in sorted_ids]
        if remaining:
            import warnings
            warnings.warn(f"依赖关系存在环，{len(remaining)} 个请求无法排序")
        sorted_ids.extend(remaining)

        return [req_map[rid] for rid in sorted_ids]

    def _execute_one(
        self,
        req: RequestEvent,
        result: AnalysisResult,
        var_store: dict[str, str],
    ) -> dict:
        url = self._substitute(req.url, var_store)
        headers = self._substitute_headers(req.request_headers, var_store)
        body = self._substitute(req.request_body or "", var_store) if req.request_body else None

        import time
        start = time.perf_counter()

        for attempt in range(self._max_retries + 1):
            try:
                resp = self._client.request(
                    method=req.method,
                    url=url,
                    headers=headers,
                    content=body,
                )
                status = resp.status_code
                response_body = resp.text
                if 200 <= status < 400:
                    self._extract_variables(req.id, response_body, result, var_store)
                    duration = (time.perf_counter() - start) * 1000
                    return {
                        "request_id": req.id, "url": url, "method": req.method,
                        "status": status, "success": True, "error": None,
                        "response_body": response_body, "duration_ms": round(duration, 1),
                    }
                if attempt < self._max_retries:
                    time.sleep(0.5 * (2 ** attempt))
            except Exception as ex:
                if attempt < self._max_retries:
                    time.sleep(0.5 * (2 ** attempt))
                elif attempt == self._max_retries:
                    duration = (time.perf_counter() - start) * 1000
                    return {
                        "request_id": req.id, "url": url, "method": req.method,
                        "status": None, "success": False, "error": str(ex),
                        "response_body": None, "duration_ms": round(duration, 1),
                    }

        duration = (time.perf_counter() - start) * 1000
        return {
            "request_id": req.id, "url": url, "method": req.method,
            "status": status, "success": False,
            "error": f"HTTP {status}",
            "response_body": response_body, "duration_ms": round(duration, 1),
        }

    def _substitute(self, text: str, var_store: dict[str, str]) -> str:
        def _replacer(m):
            return var_store.get(m.group(1), m.group(0))
        return re.sub(r"\{\{(\w+)\}\}", _replacer, text)

    def _substitute_headers(self, headers: dict, var_store: dict[str, str]) -> dict:
        return {k: self._substitute(v, var_store) for k, v in headers.items()}

    def _extract_variables(
        self,
        req_id: str,
        body_text: Optional[str],
        result: AnalysisResult,
        var_store: dict[str, str],
    ):
        if not body_text:
            return
        try:
            data = json.loads(body_text)
        except json.JSONDecodeError:
            return

        for var in result.variables:
            if var.source_request_id == req_id and var.name not in var_store:
                value = self._json_get(data, var.source_json_path)
                if value is not None:
                    var_store[var.name] = str(value)

    @staticmethod
    def _json_get(data, path: str):
        raw = path.strip("$.")
        parts = raw.split(".")
        current = data
        for part in parts:
            m = re.match(r"^(\w+)(?:\[(\d+)\])?$", part)
            if not m:
                return None
            key = m.group(1)
            idx = m.group(2)
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return None
            if idx is not None and isinstance(current, list):
                i = int(idx)
                current = current[i] if 0 <= i < len(current) else None
            if current is None:
                return None
        return current
