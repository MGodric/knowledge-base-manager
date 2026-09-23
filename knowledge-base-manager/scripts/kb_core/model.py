"""Data models and serialization structures for kb_core."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


VALID_PAGE_TYPES = frozenset({"concept", "method", "source", "decision", "project", "map"})
VALID_PAGE_STATUSES = frozenset({"draft", "stable", "deprecated"})
VALID_INCLUDES = frozenset({"sections", "relations", "sources"})


@dataclass
class Diagnostic:
    code: str
    severity: str  # 'error' | 'warning'
    file: str | None
    span: dict[str, Any] | None
    target: str | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "file": self.file,
            "span": self.span,
            "target": self.target,
            "message": self.message,
        }


@dataclass
class Issue:
    code: str
    severity: str  # 'error' | 'warning'
    file: str
    span: dict[str, Any] | None
    target: str | None
    message: str
    origin: str  # 'legacy' | 'collection'
    in_changed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "file": self.file,
            "span": self.span,
            "target": self.target or "",
            "message": self.message,
            "origin": self.origin,
            "in_changed": self.in_changed,
        }


@dataclass
class Envelope:
    command: str
    status: str
    root: str | None
    data: Any = None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "command": self.command,
            "status": self.status,
            "root": self.root,
            "data": self.data,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }


@dataclass
class LinkOccurrence:
    target: str
    label: str
    line: str
    line_number: int
    is_explicit_external_local: bool
    is_image: bool
    is_in_collection: bool
    collection_well_formed: bool
    id: str = ""
    is_direct_collection: bool = False
    span: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "target": self.target,
            "label": self.label,
            "line": self.line,
            "line_number": self.line_number,
            "is_explicit_external_local": self.is_explicit_external_local,
            "is_image": self.is_image,
            "is_in_collection": self.is_in_collection,
            "collection_well_formed": self.collection_well_formed,
            "is_direct_collection": self.is_direct_collection,
            "span": self.span,
        }


@dataclass
class Page:
    path: str
    entry_id: str | None
    title: str
    type: str | None
    status: str | None
    tags: list[str]
    source_locators: list[dict[str, Any]]
    content_hash: str
    raw_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "id": self.entry_id,
            "title": self.title,
            "type": self.type,
            "status": self.status,
            "tags": list(self.tags),
            "source_locators": [dict(sl) for sl in self.source_locators],
            "content_hash": self.content_hash,
        }


@dataclass
class Section:
    key: str
    title: str
    heading_path: list[str]
    level: int
    span: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "heading_path": list(self.heading_path),
            "level": self.level,
            "span": self.span,
        }


@dataclass
class SourceDeclaration:
    id: str
    span: dict[str, Any]
    raw_text: str
    locator: str | None
    project_id: str | None
    project_relative_path: str | None
    verified: str | None
    revision: str | None
    version_state: str | None
    support_text: str | None
    recognition: str  # 'structured' | 'partial' | 'unclassified'

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "span": self.span,
            "raw_text": self.raw_text,
            "locator": self.locator,
            "project_id": self.project_id,
            "project_relative_path": self.project_relative_path,
            "verified": self.verified,
            "revision": self.revision,
            "version_state": self.version_state,
            "support_text": self.support_text,
            "recognition": self.recognition,
        }

    def to_locator_dict(self) -> dict[str, Any]:
        kind = "unresolved"
        if self.locator:
            if self.locator.startswith(("http://", "https://")):
                kind = "web"
            elif ":/" in self.locator or ":\\" in self.locator or self.locator.startswith(("//", "\\\\")):
                kind = "external-local"
            else:
                kind = "internal"
        elif self.project_id:
            kind = "external-local"

        return {
            "kind": kind,
            "locator": self.locator,
            "project_id": self.project_id,
            "project_relative_path": self.project_relative_path,
        }


@dataclass
class Relation:
    kind: str  # 'reference' | 'collection' | 'provenance'
    from_endpoint: dict[str, Any]  # {"kind": "page"|"external", "locator": "..."}
    to_endpoint: dict[str, Any]  # {"kind": "page"|"external", "locator": "..."}
    evidence_refs: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "from": self.from_endpoint,
            "to": self.to_endpoint,
            "evidence_refs": list(self.evidence_refs),
        }
