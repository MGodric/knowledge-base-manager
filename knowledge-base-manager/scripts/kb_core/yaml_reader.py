"""Restricted YAML reader for kb.yaml and Markdown front matter."""

from __future__ import annotations

import re
from typing import Any

import yaml
from yaml.composer import ComposerError
from yaml.constructor import ConstructorError

from .model import Diagnostic


from yaml.events import AliasEvent


class RestrictedYamlLoader(yaml.SafeLoader):
    """SafeLoader that prohibits aliases, anchors, merge keys, duplicate keys, and implicit type coercions."""

    def compose_node(self, parent: Any, index: Any) -> yaml.Node:
        if self.check_event(AliasEvent):
            event = self.get_event()
            raise ComposerError(
                "while composing a node",
                event.start_mark,
                "found alias, but aliases and anchors are not permitted",
                event.start_mark,
            )
        event = self.peek_event()
        if getattr(event, "anchor", None) is not None:
            raise ComposerError(
                "while composing a node",
                event.start_mark,
                f"found anchor '{event.anchor}', but aliases and anchors are not permitted",
                event.start_mark,
            )
        return super().compose_node(parent, index)

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[str, Any]:
        if not isinstance(node, yaml.MappingNode):
            raise ConstructorError(
                None,
                None,
                f"expected a mapping node, but found {node.id}",
                node.start_mark,
            )
        mapping: dict[str, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key == "<<":
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "merge keys ('<<') are not permitted",
                    key_node.start_mark,
                )
            if key in mapping:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found duplicate key: '{key}'",
                    key_node.start_mark,
                )
            value = self.construct_object(value_node, deep=deep)
            mapping[key] = value
        return mapping


# Remove implicit resolvers for timestamp and bool so that dates and booleans remain strings
RestrictedYamlLoader.yaml_implicit_resolvers = {
    k: [
        r
        for r in v
        if r[0] not in ("tag:yaml.org,2002:timestamp", "tag:yaml.org,2002:bool")
    ]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def parse_yaml_text(
    text: str, filename: str | None = None
) -> tuple[dict[str, Any], list[Diagnostic]]:
    """Parse a YAML document into a dictionary using RestrictedYamlLoader."""
    diagnostics: list[Diagnostic] = []
    if not text.strip():
        return {}, diagnostics

    try:
        data = yaml.load(text, Loader=RestrictedYamlLoader)
        if data is None:
            return {}, diagnostics
        if not isinstance(data, dict):
            diagnostics.append(
                Diagnostic(
                    code="YAML_NOT_MAPPING",
                    severity="error",
                    file=filename,
                    span=None,
                    target=None,
                    message="YAML content must be a mapping.",
                )
            )
            return {}, diagnostics
        return data, diagnostics
    except (yaml.YAMLError, Exception) as exc:
        msg = str(exc)
        diagnostics.append(
            Diagnostic(
                code="PARSE_FAILED",
                severity="error",
                file=filename,
                span=None,
                target=None,
                message=f"YAML parse error: {msg}",
            )
        )
        return {}, diagnostics


def extract_front_matter(
    content: str, filename: str | None = None
) -> tuple[bool, int, dict[str, Any], list[Diagnostic]]:
    """Extract YAML front matter from a markdown file.

    Front matter must start at line 1 with '---' and close with '---'.
    Returns (present, end_line_index_0based, fields, diagnostics).
    """
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return False, -1, {}, []

    end_index = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_index = i
            break

    if end_index == -1:
        return False, -1, {}, []

    yaml_text = "".join(lines[1:end_index])
    fields, diagnostics = parse_yaml_text(yaml_text, filename=filename)
    return True, end_index, fields, diagnostics


def read_yaml_fields(path: str) -> dict[str, Any]:
    """Read a YAML file into a dict using RestrictedYamlLoader."""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    data, _ = parse_yaml_text(content, filename=path)
    return data
