import json
import re
import zipfile
from pathlib import Path
from typing import Optional

from core.models import (
    ActionEvent, RequestEvent, CorrelationMap,
    VariableDep, AnalysisResult,
)


_VARIABLE_KEY_PATTERN = re.compile(r"(id|token|code|key|uid|sid|session|auth|order|trade|sn|uuid)", re.IGNORECASE)


class AnalyzerError(Exception):
    pass


class TraceParser:
    """
    解析 Playwright Trace 文件（.zip），提取操作事件与请求事件。
    """

    def __init__(self, trace_path: str):
        self._trace_path = Path(trace_path)

    def parse(self) -> tuple[list[ActionEvent], list[RequestEvent]]:
        """解构 trace.zip，返回 (操作事件列表, 请求事件列表)。"""
        if not self._trace_file.exists():
            raise AnalyzerError(f"Trace 文件不存在: {self._trace_path}")

        try:
            with zipfile.ZipFile(str(self._trace_path), "r") as z:
                if "trace.jsonl" not in z.namelist():
                    raise AnalyzerError("trace.zip 中缺少 trace.jsonl")
                with z.open("trace.jsonl") as f:
                    content = f.read().decode("utf-8")
        except zipfile.BadZipFile:
            raise AnalyzerError("Trace 文件损坏")

        actions: list[ActionEvent] = []
        requests: list[RequestEvent] = []
        action_idx = 0
        req_idx = 0

        for line in content.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            evt_type = record.get("type", "")
            ts = record.get("timestamp", 0)
            metadata = record.get("metadata", {}) or {}

            if evt_type == "action":
                action = self._parse_action(record, action_idx, ts, metadata)
                if action:
                    actions.append(action)
                    action_idx += 1

            elif evt_type == "resource-snapshot" or evt_type == "network":
                req = self._parse_request(record, req_idx, ts)
                if req:
                    requests.append(req)
                    req_idx += 1

        return actions, requests

    @property
    def _trace_file(self) -> Path:
        return self._trace_path

    def _parse_action(self, record: dict, idx: int, ts: float, metadata: dict) -> Optional[ActionEvent]:
        action_data = record.get("action", {}) or {}
        action_name = action_data.get("name", "")
        selector = action_data.get("selector", "")

        if not action_name:
            return None

        page_url = metadata.get("pageTitle", "") or record.get("page", {}).get("url", "")

        action_type = "Other"
        if action_name.startswith("click"):
            action_type = "Click"
        elif action_name.startswith("fill") or action_name.startswith("type"):
            action_type = "Input"
        elif action_name.startswith("goto") or action_name.startswith("navigate"):
            action_type = "Navigation"
        elif action_name.startswith("scroll"):
            action_type = "Scroll"

        hint = selector.get("selector", action_name) if isinstance(selector, dict) else str(selector)

        return ActionEvent(
            id=f"action_{idx}",
            action_type=action_type,
            timestamp=ts,
            description=f"{action_type} {action_name[:60]}",
            selector_hint=hint[:120],
            page_url=page_url,
        )

    def _parse_request(self, record: dict, idx: int, ts: float) -> Optional[RequestEvent]:
        req_data = record.get("request", {}) or {}
        resp_data = record.get("response", {}) or {}

        url = req_data.get("url", "")
        method = req_data.get("method", "GET")
        if not url:
            return None

        req_headers = {h.get("name", ""): h.get("value", "") for h in req_data.get("headers", []) if isinstance(h, dict)}
        resp_headers = {h.get("name", ""): h.get("value", "") for h in resp_data.get("headers", []) if isinstance(h, dict)}

        req_body = None
        post_data = req_data.get("postData")
        if post_data:
            if isinstance(post_data, str):
                req_body = post_data
            elif isinstance(post_data, dict):
                req_body = json.dumps(post_data, ensure_ascii=False)

        resp_body = None
        resp_text = resp_data.get("body") or record.get("responseBody")
        if resp_text and isinstance(resp_text, str):
            resp_body = resp_text[:50000]

        duration = 0.0
        timing = resp_data.get("timing", {}) or {}
        if isinstance(timing, dict):
            start = timing.get("startTime")
            end = timing.get("responseEnd")
            if start is not None and end is not None:
                duration = (end - start) * 1000
            elif timing.get("duration") is not None:
                duration = float(timing["duration"])

        return RequestEvent(
            id=f"req_{idx}",
            timestamp=ts,
            url=url,
            method=method,
            request_headers=req_headers,
            request_body=req_body,
            response_status=resp_data.get("status", 0),
            response_headers=resp_headers,
            response_body=resp_body,
            duration=duration,
            session_id="",
        )


class Correlator:
    """
    核心关联算法 — 基于时间窗口建立操作→请求的映射。
    """

    def __init__(self, max_delta_ms: float = 5000.0):
        self.max_delta_ms = max_delta_ms

    def correlate(self, actions: list[ActionEvent], requests: list[RequestEvent]) -> tuple[list[CorrelationMap], list[str]]:
        results: list[CorrelationMap] = []
        orphan_requests: list[str] = []

        for req in requests:
            best_action = None
            best_delta = float("inf")

            for act in reversed(actions):
                delta = req.timestamp - act.timestamp
                if 0 <= delta <= self.max_delta_ms:
                    if delta < best_delta:
                        best_delta = delta
                        best_action = act

            if best_action:
                existing = next(
                    (c for c in results if c.action_id == best_action.id),
                    None,
                )
                if existing:
                    existing.request_ids.append(req.id)
                    existing.time_delta_ms = best_delta
                else:
                    results.append(CorrelationMap(
                        action_id=best_action.id,
                        request_ids=[req.id],
                        time_delta_ms=best_delta,
                    ))
            else:
                orphan_requests.append(req.id)

        return results, orphan_requests


class VariableExtractor:
    """
    自动变量提取 — 从响应体中挖掘动态值并验证依赖。
    """

    def __init__(self):
        self._variables: list[VariableDep] = []

    def extract(self, requests: list[RequestEvent]) -> list[VariableDep]:
        self._variables = []
        candidates = self._mine_candidates(requests)
        self._validate_candidates(candidates, requests)
        return self._variables

    def _mine_candidates(self, requests: list[RequestEvent]) -> list[dict]:
        candidates = []
        for req in requests:
            if not req.response_body:
                continue
            try:
                data = json.loads(req.response_body)
            except (json.JSONDecodeError, TypeError):
                continue
            self._walk_json(data, "", req.id, candidates)
        return candidates

    def _walk_json(self, obj, prefix: str, req_id: str, candidates: list):
        if isinstance(obj, dict):
            for k, v in obj.items():
                path = f"{prefix}.{k}" if prefix else k
                if isinstance(v, (str, int, float)) and not isinstance(v, bool):
                    if _VARIABLE_KEY_PATTERN.search(k):
                        candidates.append({
                            "name": k,
                            "source_request_id": req_id,
                            "source_json_path": path,
                            "sample_value": str(v),
                        })
                else:
                    self._walk_json(v, path, req_id, candidates)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                self._walk_json(item, f"{prefix}[{i}]", req_id, candidates)

    def _validate_candidates(self, candidates: list, requests: list[RequestEvent]):
        for cand in candidates:
            refs = self._find_references(cand["sample_value"], cand["source_request_id"], requests)
            if refs:
                dep = VariableDep(
                    name=cand["name"],
                    source_request_id=cand["source_request_id"],
                    source_json_path=cand["source_json_path"],
                    sample_value=cand["sample_value"],
                    referenced_by=refs,
                )
                self._variables.append(dep)

    def _find_references(self, value: str, source_id: str, requests: list[RequestEvent]) -> list[str]:
        refs = []
        for req in requests:
            if req.id == source_id:
                continue
            if value in req.url or value in (req.request_body or ""):
                refs.append(req.id)
        return refs


class Analyzer:
    """
    解析与关联层 — 整合 Trace 解析、关联和变量提取。
    """

    def __init__(self, max_delta_ms: float = 5000.0):
        self.max_delta_ms = max_delta_ms

    def analyze(self, trace_path: str) -> AnalysisResult:
        parser = TraceParser(trace_path)
        actions, requests = parser.parse()

        correlator = Correlator(self.max_delta_ms)
        correlations, orphan_ids = correlator.correlate(actions, requests)

        extractor = VariableExtractor()
        variables = extractor.extract(requests)

        return AnalysisResult(
            actions=actions,
            requests=requests,
            correlations=correlations,
            variables=variables,
            orphan_requests=orphan_ids,
        )
