import json
import re
from urllib.parse import urlparse
from typing import Optional

from core.models import AnalysisResult, VariableDep


class GeneratorError(Exception):
    pass


class PostmanGenerator:
    """
    推导与生成层 — 将分析结果生成为 Postman v2.1.0 Collection。
    """

    def __init__(self, collection_name: str = "录制分析 Collection"):
        self.collection_name = collection_name

    def generate(self, result: AnalysisResult) -> dict:
        """
        生成符合 Postman v2.1.0 Schema 的 Collection dict。
        """
        if not result.requests:
            raise GeneratorError("无请求可导出")

        collection = self._build_skeleton()
        folders = self._group_by_host(result)
        items = []

        for host, host_requests in sorted(folders.items()):
            folder = self._build_folder(host, host_requests, result)
            items.append(folder)

        collection["item"] = items
        collection["variable"] = self._build_variables(result.variables)
        collection["info"]["schema"] = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"

        return collection

    def _build_skeleton(self) -> dict:
        return {
            "info": {
                "name": self.collection_name,
                "description": "由 RecorderAnalyzer 自动生成的接口集合",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": [],
            "variable": [],
        }

    def _group_by_host(self, result: AnalysisResult) -> dict[str, list]:
        folders: dict[str, list] = {}
        for req in result.requests:
            host = urlparse(req.url).netloc or "unknown"
            if host not in folders:
                folders[host] = []
            folders[host].append(req)
        return folders

    def _build_folder(self, host: str, requests: list, result: AnalysisResult) -> dict:
        folder = {
            "name": host,
            "item": [],
        }
        for req in requests:
            item = self._build_request_item(req, result)
            folder["item"].append(item)
        return folder

    def _build_request_item(self, req, result: AnalysisResult) -> dict:
        url_parsed = urlparse(req.url)

        body_data = self._process_body(req, result)

        item = {
            "name": f"{req.method} {url_parsed.path or '/'}",
            "request": {
                "method": req.method,
                "header": self._build_headers(req, result),
                "url": self._build_url(url_parsed, req, result),
            },
        }

        if body_data is not None:
            item["request"]["body"] = body_data

        return item

    def _build_url(self, parsed, req, result: AnalysisResult) -> dict:
        query_items = []
        if parsed.query:
            for pair in parsed.query.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    query_items.append({
                        "key": k,
                        "value": self._substitute_vars(v, result),
                    })

        host_parts = [parsed.hostname] if parsed.hostname else parsed.netloc.split(":")
        port = parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80)
        return {
            "raw": self._substitute_vars(req.url, result),
            "protocol": parsed.scheme,
            "host": host_parts,
            "port": port,
            "path": parsed.path.split("/") if parsed.path else [],
            "query": query_items if query_items else [],
        }

    def _build_headers(self, req, result: AnalysisResult) -> list[dict]:
        headers = []
        for k, v in req.request_headers.items():
            if k.lower() in ("host", "content-length", "connection"):
                continue
            headers.append({
                "key": k,
                "value": self._substitute_vars(v, result),
                "type": "text",
            })
        return headers

    def _process_body(self, req, result: AnalysisResult) -> Optional[dict]:
        if not req.request_body:
            return None

        body_str = self._substitute_vars(req.request_body, result)

        if req.request_headers.get("content-type", "").startswith("application/json"):
            return {
                "mode": "raw",
                "raw": body_str,
                "options": {"raw": {"language": "json"}},
            }
        return {
            "mode": "raw",
            "raw": body_str,
        }

    def _substitute_vars(self, text: str, result: AnalysisResult) -> str:
        """将已识别的变量替换为 Postman 占位符。"""
        for var in result.variables:
            if var.sample_value:
                escaped = re.escape(var.sample_value)
                text = re.sub(
                    rf"(?<!\w){escaped}(?!\w)",
                    f"{{{{{var.name}}}}}",
                    text,
                )
        return text

    def _build_variables(self, variables: list[VariableDep]) -> list[dict]:
        seen = set()
        result = []
        for var in variables:
            if var.name not in seen:
                seen.add(var.name)
                result.append({
                    "key": var.name,
                    "value": var.sample_value,
                    "type": "string",
                })
        return result


def generate_collection_json(result: AnalysisResult, name: str = "录制分析 Collection") -> str:
    """便捷方法：直接返回 JSON 字符串。"""
    gen = PostmanGenerator(name)
    collection = gen.generate(result)
    return json.dumps(collection, ensure_ascii=False, indent=2)
