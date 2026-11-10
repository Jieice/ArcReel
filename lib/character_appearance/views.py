"""Bounded tool projections; complete frozen bases stay in server-owned records."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lib.infra.content_digest import prefixed_canonical_json_digest

_CONTEXT_CHAR_BUDGET = 12000
_FILE_LIMIT = 64
_DERIVATIVE_LIMIT = 8


def _appearance_context(entry: Mapping[str, Any], budget: int) -> dict[str, Any]:
    description = entry.get("description")
    description = description if isinstance(description, str) else ""
    raw_derivatives = entry.get("derivatives")
    derivatives = raw_derivatives if isinstance(raw_derivatives, Mapping) else {}
    description_limit = max(1, budget * 2 // 3) if derivatives else budget
    remaining = max(0, budget - min(len(description), description_limit))
    view: dict[str, Any] = {
        "description": description[:description_limit],
        "description_truncated": len(description) > description_limit,
        "derivative_count": len(derivatives),
        "derivatives": {},
    }
    selected = list(derivatives.items())[:_DERIVATIVE_LIMIT]
    per_derivative = remaining // max(1, len(selected))
    for name, derivative in selected:
        text = derivative.get("description", "") if isinstance(derivative, Mapping) else ""
        text = text if isinstance(text, str) else ""
        view["derivatives"][name] = {
            "description": text[:per_derivative],
            "description_truncated": len(text) > per_derivative,
        }
    view["derivatives_truncated"] = len(derivatives) > _DERIVATIVE_LIMIT
    for field in ("reference_image", "character_sheet", "reference_audio"):
        if field in entry:
            view[field] = entry[field]
    return view


def basis_summary(basis: Mapping[str, Any]) -> dict[str, Any]:
    context = basis["declared_context"]
    comparisons = set(context.get("comparison_characters", []))
    selected = [entry for entry in basis["character_registry"] if entry["name"] in comparisons]
    per_context = _CONTEXT_CHAR_BUDGET // (1 + len(selected))
    paths = basis["ordered_source_paths"]
    files = basis["reference_files"]
    return {
        "revision": basis["revision"],
        "source_revision": basis["source_revision"],
        "ordered_source_paths": paths[:_FILE_LIMIT],
        "registered_source_count": len(paths),
        "source_paths_truncated": len(paths) > _FILE_LIMIT,
        "registration_revision": prefixed_canonical_json_digest(basis["registration"]),
        "character_registry_revision": prefixed_canonical_json_digest(basis["character_registry"]),
        "character_count": len(basis["character_registry"]),
        "character_name": basis["character_name"],
        "target_context": _appearance_context(basis["target_context"], per_context),
        "comparison_contexts": [
            {"name": entry["name"], **_appearance_context(entry, per_context)} for entry in selected
        ],
        "reference_files": files[:_FILE_LIMIT],
        "reference_file_count": len(files),
        "reference_files_truncated": len(files) > _FILE_LIMIT,
        "declared_context": context,
        "style_context_revision": prefixed_canonical_json_digest(basis["style_context"]),
        "visual_recognition_performed": False,
        "complete_basis_retained_by_server": True,
    }


def proposal_view(proposal: Mapping[str, Any]) -> dict[str, Any]:
    return {**proposal, "basis": basis_summary(proposal["basis"])}
