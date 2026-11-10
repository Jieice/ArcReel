"""Freeze the entire registered corpus and appearance inputs under the project lock."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from lib.infra.content_digest import digest_stream, prefixed_canonical_json_digest
from lib.project.asset_types import resolve_asset_key
from lib.project.source_revision import SourceFileRead, SourceScope, _registered_source_paths, compute_source_revision


class CharacterAppearanceError(Exception):
    def __init__(self, code: str, detail: str, *, params: dict[str, Any] | None = None):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.params = params


def canonical_character(project: Mapping[str, Any], name: str) -> tuple[str, dict[str, Any]]:
    characters = project.get("characters")
    key = resolve_asset_key(characters, name)
    if not isinstance(characters, Mapping) or key is None:
        raise CharacterAppearanceError("character_not_found", f"已登记角色不存在：{name}")
    entry = characters[key]
    if not isinstance(entry, dict):
        raise CharacterAppearanceError("appearance_character_invalid", f"角色条目不是对象：{key}")
    return key, entry


def guard_local_path(project_dir: Path, path: Path) -> None:
    try:
        relative = path.relative_to(project_dir)
        path.resolve().relative_to(project_dir.resolve())
    except ValueError as exc:
        raise CharacterAppearanceError("appearance_unsafe_path", "分析文件路径越出项目") from exc
    current = project_dir
    for part in relative.parts:
        current = current / part
        if current.is_symlink() or current.is_junction():
            raise CharacterAppearanceError("appearance_unsafe_path", "分析输入或存储路径不得经过符号链接/目录联接")


def _reference_identity(project_dir: Path, value: str) -> dict[str, Any]:
    if "://" in value:
        return {"path": value, "state": "external_identity_only", "sha256": None}
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or "\\" in value or "\x00" in value:
        raise CharacterAppearanceError("appearance_unsafe_reference", "角色参考路径必须是安全的项目相对路径")
    path = project_dir.joinpath(*pure.parts)
    guard_local_path(project_dir, path)
    if not path.exists():
        return {"path": value, "state": "missing", "sha256": None}
    if not path.is_file():
        raise CharacterAppearanceError("appearance_invalid_reference", f"角色参考路径不是文件：{value}")
    try:
        with path.open("rb") as handle:
            digest, size, _ = digest_stream(handle.read)
    except OSError as exc:
        raise CharacterAppearanceError("appearance_unreadable_reference", f"无法读取角色参考文件：{value}") from exc
    return {"path": value, "state": "local_file_identity_only", "sha256": digest, "bytes": size}


def _reference_paths(entry: Mapping[str, Any]) -> list[str]:
    paths: list[str] = []
    for field in ("reference_image", "character_sheet", "reference_audio"):
        value = entry.get(field)
        if isinstance(value, str) and value and value not in paths:
            paths.append(value)
    derivatives = entry.get("derivatives")
    for derivative in derivatives.values() if isinstance(derivatives, Mapping) else []:
        if isinstance(derivative, Mapping):
            for path in _reference_paths(derivative):
                if path not in paths:
                    paths.append(path)
    return paths


def compute_appearance_basis(
    project_dir: Path,
    project: Mapping[str, Any],
    character_name: str,
    declared_context: Mapping[str, Any],
) -> tuple[dict[str, Any], list[SourceFileRead]]:
    """Caller holds the ProjectManager lock; reuse strict registered-source semantics."""
    canonical, entry = canonical_character(project, character_name)
    registered = _registered_source_paths(project)
    if not registered:
        raise CharacterAppearanceError("appearance_no_registered_source", "项目没有登记原文，不能声称全原文分析")
    guard_local_path(project_dir, project_dir / "source")
    sources = compute_source_revision(project_dir, project, SourceScope(kind="files", files=registered))
    if sources.blockers or sources.revision is None:
        raise CharacterAppearanceError(
            "appearance_source_blocked",
            "登记原文不完整或不可安全读取；未创建证据快照",
            params={"blockers": [item.model_dump() for item in sources.blockers]},
        )
    by_path = {read.rel_path: read for read in sources.documents}
    ordered_paths = [unicodedata.normalize("NFC", path) for path in registered]
    documents = [by_path[path] for path in ordered_paths]
    characters = project.get("characters", {})
    registry = [
        {
            "name": name,
            "aliases": attrs.get("aliases", []) if isinstance(attrs, Mapping) else None,
            "description": attrs.get("description") if isinstance(attrs, Mapping) else None,
            "derivatives": attrs.get("derivatives") if isinstance(attrs, Mapping) else None,
        }
        for name, attrs in characters.items()
    ]
    raw_episodes = project.get("episodes")
    episodes = (
        [
            {
                key: episode.get(key)
                for key in ("episode", "source_origin", "source_range", "source_kind", "source_language")
            }
            for episode in raw_episodes
            if isinstance(episode, Mapping)
        ]
        if isinstance(raw_episodes, list)
        else []
    )
    payload = {
        "source_revision": sources.revision,
        "ordered_source_paths": ordered_paths,
        "registration": {"whole_source_files": project.get("whole_source_files"), "episodes": episodes},
        "character_registry": registry,
        "character_name": canonical,
        "target_context": {
            key: entry.get(key)
            for key in ("description", "derivatives", "reference_image", "character_sheet", "reference_audio")
        },
        "reference_files": [_reference_identity(project_dir, value) for value in _reference_paths(entry)],
        "declared_context": dict(declared_context),
        "style_context": {key: project.get(key) for key in ("style", "style_description")},
    }
    return {**payload, "revision": prefixed_canonical_json_digest(payload)}, documents
