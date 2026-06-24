from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Course:
    id: str
    name: str
    url: str


@dataclass(slots=True)
class ProblemSetSummary:
    id: str
    title: str
    url: str
    starts_at: str = ""
    ends_at: str = ""
    owner: str = ""


@dataclass(slots=True)
class ExportSourceSummary:
    id: str
    title: str
    url: str
    source_kind: str
    parent_problem_set_id: str = ""
    parent_title: str = ""
    type_label: str = ""
    starts_at: str = ""
    ends_at: str = ""
    owner: str = ""
    problem_count: int = 0

    @classmethod
    def from_problem_set(cls, problem_set: ProblemSetSummary) -> "ExportSourceSummary":
        return cls(
            id=problem_set.id,
            title=problem_set.title,
            url=problem_set.url,
            source_kind="problem_set",
            parent_problem_set_id=problem_set.id,
            parent_title=problem_set.title,
            starts_at=problem_set.starts_at,
            ends_at=problem_set.ends_at,
            owner=problem_set.owner,
        )

    @property
    def problem_set_id(self) -> str:
        return self.parent_problem_set_id or self.id

    @property
    def problem_set_title(self) -> str:
        return (self.parent_title or self.title).strip()

    @property
    def type_title(self) -> str:
        return (self.type_label or self.title).strip()

    def queue_label(self) -> str:
        if self.source_kind == "problem_type":
            return f"{self.problem_set_title} / {self.type_title}"
        return self.title.strip()

    def export_title(self) -> str:
        if self.source_kind == "problem_type":
            parts = [self.problem_set_title, self.type_title]
            return "_".join(part for part in parts if part)
        return self.title.strip()


@dataclass(slots=True)
class ProblemSection:
    kind: str
    title: str
    content: str


@dataclass(slots=True)
class ProblemSample:
    input_text: str
    output_text: str
    note: str = ""


@dataclass(slots=True)
class ProblemImage:
    url: str
    alt: str = ""
    local_path: str | None = None


@dataclass(slots=True)
class Problem:
    id: str
    title: str
    url: str
    score: str = ""
    sequence_label: str = ""
    title_source: str = ""
    sections: list[ProblemSection] = field(default_factory=list)
    samples: list[ProblemSample] = field(default_factory=list)
    images: list[ProblemImage] = field(default_factory=list)


@dataclass(slots=True)
class ExportWarning:
    code: str
    category: str
    message: str
    source_title: str = ""
    problem_title: str = ""


@dataclass(slots=True)
class Assignment:
    id: str
    title: str
    url: str
    course_name: str = ""
    expected_problem_total: int = 0
    parsed_problem_total: int = 0
    warnings: list[str] = field(default_factory=list)
    warning_details: list[ExportWarning] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)


@dataclass(slots=True)
class ExportResult:
    output_path: str
    output_paths: list[str] = field(default_factory=list)
    export_mode: str = "merged"
    warnings: list[str] = field(default_factory=list)
    warning_details: list[ExportWarning] = field(default_factory=list)
    summary: "ExportSummary" = field(default_factory=lambda: ExportSummary())


@dataclass(slots=True)
class ExportSummary:
    exported_problem_set_count: int = 0
    expected_problem_total: int = 0
    parsed_problem_total: int = 0
    failed_problem_total: int = 0
    warning_count: int = 0
    image_warning_count: int = 0
    missing_problem_warning_count: int = 0
    page_warning_count: int = 0
    content_warning_count: int = 0
    warning_category_counts: dict[str, int] = field(default_factory=dict)


def model_to_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        data = {}
        for key in value.__dataclass_fields__:
            data[key] = model_to_dict(getattr(value, key))
        return data
    if isinstance(value, dict):
        return {key: model_to_dict(item) for key, item in value.items()}
    if isinstance(value, list):
        return [model_to_dict(item) for item in value]
    return value
