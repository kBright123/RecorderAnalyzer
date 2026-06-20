import json
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class ActionEvent:
    id: str
    action_type: str  # Click | Input | Navigation | Scroll | Other
    timestamp: float  # ms
    description: str
    selector_hint: str
    page_url: str


@dataclass
class RequestEvent:
    id: str
    timestamp: float
    url: str
    method: str
    request_headers: dict
    request_body: Optional[str]
    response_status: int
    response_headers: dict
    response_body: Optional[str]
    duration: float = 0.0
    session_id: str = ""


@dataclass
class CorrelationMap:
    action_id: str
    request_ids: list[str] = field(default_factory=list)
    time_delta_ms: float = 0.0


@dataclass
class VariableDep:
    name: str
    source_request_id: str
    source_json_path: str
    sample_value: str
    referenced_by: list[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    actions: list[ActionEvent] = field(default_factory=list)
    requests: list[RequestEvent] = field(default_factory=list)
    correlations: list[CorrelationMap] = field(default_factory=list)
    variables: list[VariableDep] = field(default_factory=list)
    orphan_requests: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, default=str)
