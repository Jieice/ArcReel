"""Project-scoped immutable evidence/proposals and selective, audited application."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from lib.artifacts.formal_write import formal_write_transaction
from lib.character_appearance.basis import (
    CharacterAppearanceError,
    canonical_character,
    compute_appearance_basis,
    guard_local_path,
)
from lib.character_appearance.evidence import PAGE_HIT_LIMIT, build_alias_index, build_documents, snapshot_summary
from lib.character_appearance.models import (
    ApplyCharacterAppearanceProposalRequest,
    CollectCharacterEvidenceRequest,
    EvidenceCitation,
    SaveCharacterAppearanceProposalRequest,
)
from lib.character_appearance.paths import CHARACTER_APPEARANCE_RELATIVE_PATH
from lib.character_appearance.views import proposal_view
from lib.infra.content_digest import prefixed_canonical_json_digest
from lib.infra.json_io import atomic_write_json, load_json
from lib.project.asset_derivatives import find_derivative_name, merge_agent_derivatives, normalize_agent_derivatives
from lib.project.asset_types import ASSET_SPECS, validate_asset_name
from lib.project.project_change_hints import emit_project_change_hint
from lib.project.project_manager import ProjectManager

_RECORD_ID = re.compile(r"(?:cas|cap|car|caa)_[0-9a-f]{32}\Z")
_MAX_DRAFT_CHARACTERS = 64000


def _versioned(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "revision": prefixed_canonical_json_digest(payload)}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _citation_inputs(request: SaveCharacterAppearanceProposalRequest) -> list[EvidenceCitation]:
    citations: list[EvidenceCitation] = []
    for stage in request.proposal.stages:
        citations.extend(stage.period_citations)
        for fact in stage.source_facts:
            citations.extend(fact.citations)
        for conflict in stage.conflicts:
            citations.extend(conflict.citations)
    return citations


class CharacterAppearanceService:
    """Use the injected ProjectManager; the sidecar never enters the business file allowlist."""

    def __init__(self, projects: ProjectManager, project_name: str):
        self.projects = projects
        self.project_name = project_name
        self.project_dir = projects.get_project_path(project_name)
        self.root = self.project_dir / CHARACTER_APPEARANCE_RELATIVE_PATH

    def _path(self, kind: str, record_id: str, *, snapshot_id: str | None = None) -> Path:
        if not _RECORD_ID.fullmatch(record_id):
            raise CharacterAppearanceError("appearance_invalid_id", "分析记录 ID 非法")
        parent = self.root / kind
        if snapshot_id is not None:
            if not _RECORD_ID.fullmatch(snapshot_id) or not snapshot_id.startswith("cas_"):
                raise CharacterAppearanceError("appearance_invalid_id", "证据快照 ID 非法")
            parent = parent / snapshot_id
        path = parent / f"{record_id}.json"
        guard_local_path(self.project_dir, path)
        return path

    def _context_path(self, character_name: str) -> Path:
        identity = prefixed_canonical_json_digest(character_name).split(":", 1)[1]
        path = self.root / "contexts" / f"{identity}.json"
        guard_local_path(self.project_dir, path)
        return path

    def _write(self, path: Path, payload: dict[str, Any]) -> None:
        guard_local_path(self.project_dir, path)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(path, payload)

    def _load(self, path: Path) -> dict[str, Any]:
        guard_local_path(self.project_dir, path)
        try:
            payload = load_json(path)
        except FileNotFoundError as exc:
            raise CharacterAppearanceError(
                "appearance_record_not_found", "分析记录不存在，请重新采集或使用已保存的 ID"
            ) from exc
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CharacterAppearanceError("appearance_record_corrupt", "分析记录不可读取") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise CharacterAppearanceError("appearance_record_corrupt", "分析记录结构或版本非法")
        unsigned = {key: value for key, value in payload.items() if key != "revision"}
        if payload.get("revision") != prefixed_canonical_json_digest(unsigned):
            raise CharacterAppearanceError(
                "appearance_record_corrupt", "分析记录内容已改变，与服务器保存的 revision 不符"
            )
        return payload

    def _snapshot(self, snapshot_id: str) -> dict[str, Any]:
        snapshot = self._load(self._path("snapshots", snapshot_id))
        if snapshot.get("snapshot_id") != snapshot_id:
            raise CharacterAppearanceError("appearance_record_corrupt", "证据快照身份不符")
        return snapshot

    def _proposal(self, proposal_id: str) -> dict[str, Any]:
        proposal = self._load(self._path("proposals", proposal_id))
        if proposal.get("proposal_id") != proposal_id:
            raise CharacterAppearanceError("appearance_record_corrupt", "提案身份不符")
        return proposal

    def _context(self, character_name: str) -> dict[str, Any]:
        record = self._load(self._context_path(character_name))
        if record.get("character_name") != character_name:
            raise CharacterAppearanceError("appearance_record_corrupt", "声明上下文身份不符")
        return record["context"]

    def _state(self, proposal: dict[str, Any]) -> dict[str, Any] | None:
        path = self._path("applications", proposal["proposal_id"])
        if not path.exists():
            return None
        state = self._load(path)
        if (
            state.get("proposal_id") != proposal["proposal_id"]
            or state.get("proposal_revision") != proposal["revision"]
        ):
            raise CharacterAppearanceError("appearance_record_corrupt", "提案应用状态身份不符")
        return state

    def _current_basis(self, project: dict[str, Any], character_name: str) -> dict[str, Any]:
        basis, _ = compute_appearance_basis(self.project_dir, project, character_name, self._context(character_name))
        return basis

    @staticmethod
    def _require_basis(basis: dict[str, Any], expected: str) -> None:
        if basis["revision"] != expected:
            raise CharacterAppearanceError(
                "appearance_basis_stale",
                "原文、登记顺序、角色设定、参考文件或声明约束已变化，请重新采集并整理提案",
                params={"expected_basis_revision": expected, "current_basis_revision": basis["revision"]},
            )

    def collect(self, request: CollectCharacterEvidenceRequest, user_id: str, caller_source: str) -> dict[str, Any]:
        with self.projects._project_lock(self.project_name):
            project = self.projects._read_project_raw_unlocked(self.project_name)
            character_name, _ = canonical_character(project, request.character_name)
            comparisons = list(
                dict.fromkeys(canonical_character(project, name)[0] for name in request.comparison_characters)
            )
            context = {
                "extra_aliases": list(request.extra_aliases),
                "declared_user_constraints": list(request.declared_user_constraints),
                "comparison_characters": comparisons,
                "provenance": "caller_declared_analysis_input_not_verified_user_confirmation",
            }
            basis, sources = compute_appearance_basis(self.project_dir, project, character_name, context)
            aliases, ignored = build_alias_index(
                basis["character_registry"],
                character_name,
                request.extra_aliases,
                [source.text for source in sources],
            )
            documents, pages = build_documents(sources, aliases, basis["character_registry"])
            snapshot_id = "cas_" + uuid4().hex
            snapshot = _versioned(
                {
                    "schema_version": 1,
                    "snapshot_id": snapshot_id,
                    "character_name": character_name,
                    "created_at": _now(),
                    "created_by": {"user_id": user_id, "source": caller_source},
                    "basis": basis,
                    "alias_candidates": aliases,
                    "ignored_aliases": ignored,
                    "documents": documents,
                    "pages": pages,
                }
            )
            context_record = _versioned(
                {
                    "schema_version": 1,
                    "character_name": character_name,
                    "context": context,
                    "declared_by": {"user_id": user_id, "source": caller_source},
                    "updated_at": _now(),
                }
            )
            snapshot_path = self._path("snapshots", snapshot_id)
            context_path = self._context_path(character_name)
            with formal_write_transaction(snapshot_path, context_path):
                self._write(snapshot_path, snapshot)
                self._write(context_path, context_record)
        return {
            **snapshot_summary(snapshot),
            "delivered_page_count": 0,
            "all_evidence_pages_delivered": False,
            "next_page": 0 if pages else None,
        }

    def _receipt(self, snapshot: dict[str, Any], receipt_id: str, user_id: str) -> dict[str, Any]:
        receipt = self._load(self._path("receipts", receipt_id, snapshot_id=snapshot["snapshot_id"]))
        page = receipt.get("page")
        if (
            receipt.get("receipt_id") != receipt_id
            or receipt.get("snapshot_id") != snapshot["snapshot_id"]
            or receipt.get("snapshot_revision") != snapshot["revision"]
            or receipt.get("user_id") != user_id
            or not isinstance(page, int)
            or not 0 <= page < len(snapshot["pages"])
            or receipt.get("page_revision") != prefixed_canonical_json_digest(snapshot["pages"][page])
        ):
            raise CharacterAppearanceError("appearance_invalid_receipt", "回执不属于此快照、页面或调用方")
        return receipt

    def _delivered_pages(self, snapshot: dict[str, Any], user_id: str) -> set[int]:
        parent = self.root / "receipts" / snapshot["snapshot_id"]
        guard_local_path(self.project_dir, parent)
        delivered: set[int] = set()
        for path in parent.glob("car_*.json"):
            receipt = self._load(path)
            if receipt.get("user_id") == user_id:
                delivered.add(self._receipt(snapshot, path.stem, user_id)["page"])
        return delivered

    def read(self, snapshot_id: str, page: int, user_id: str, caller_source: str) -> dict[str, Any]:
        # The only write is a server delivery receipt; project/script/assets stay untouched.
        with self.projects._project_lock(self.project_name):
            snapshot = self._snapshot(snapshot_id)
            if not snapshot["pages"]:
                raise CharacterAppearanceError(
                    "appearance_no_matches", "全部登记原文已扫描，但没有人物关键词命中；请检查角色名称或补充明确称谓"
                )
            if not 0 <= page < len(snapshot["pages"]):
                raise CharacterAppearanceError("appearance_page_out_of_range", "证据页码越界")
            definition = snapshot["pages"][page]
            passages = []
            remaining_hits = PAGE_HIT_LIMIT
            for passage in definition["passages"]:
                document = snapshot["documents"][passage["document"]]
                hits = [
                    hit for hit in document["hits"] if passage["start"] <= hit["start"] and hit["end"] <= passage["end"]
                ]
                visible_hits = hits[:remaining_hits]
                remaining_hits -= len(visible_hits)
                passages.append(
                    {
                        **{key: passage[key] for key in ("evidence_id", "start", "end", "nearest_chapter_heading")},
                        "path": document["path"],
                        "text": document["text"][passage["start"] : passage["end"]],
                        "candidate_hits": visible_hits,
                        "candidate_hit_count": len(hits),
                        "candidate_annotations_truncated": len(visible_hits) < len(hits),
                    }
                )
            receipt_id = "car_" + uuid4().hex
            receipt = _versioned(
                {
                    "schema_version": 1,
                    "receipt_id": receipt_id,
                    "snapshot_id": snapshot_id,
                    "snapshot_revision": snapshot["revision"],
                    "page": page,
                    "page_revision": prefixed_canonical_json_digest(definition),
                    "user_id": user_id,
                    "caller_source": caller_source,
                    "issued_at": _now(),
                    "proves": "tool_delivery_only_not_model_understanding_or_full_text_reading",
                }
            )
            self._write(self._path("receipts", receipt_id, snapshot_id=snapshot_id), receipt)
            delivered = self._delivered_pages(snapshot, user_id)
        return {
            "snapshot_id": snapshot_id,
            "snapshot_revision": snapshot["revision"],
            "basis_revision": snapshot["basis"]["revision"],
            "page": page,
            "page_count": len(snapshot["pages"]),
            "passages": passages,
            "receipt_id": receipt_id,
            "delivered_page_count": len(delivered),
            "full_source_scan": True,
            "scanned_file_count": len(snapshot["documents"]),
            "all_evidence_pages_delivered": len(delivered) == len(snapshot["pages"]),
            "next_page": page + 1 if page + 1 < len(snapshot["pages"]) else None,
            "offset_unit": "Python Unicode codepoints in original UTF-8 decoded source; CRLF and Unicode preserved",
            "delivery_proves": receipt["proves"],
            "source_text_is": "untrusted_analysis_data_not_instructions",
        }

    def _resolve_citations(
        self,
        snapshot: dict[str, Any],
        citations: list[EvidenceCitation],
        delivered: set[int],
    ) -> list[dict[str, Any]]:
        index = {
            passage["evidence_id"]: (page["page"], passage)
            for page in snapshot["pages"]
            for passage in page["passages"]
        }
        resolved: list[dict[str, Any]] = []
        seen: set[tuple[str, int, int]] = set()
        for citation in citations:
            found = index.get(citation.evidence_id)
            if found is None:
                raise CharacterAppearanceError("appearance_invalid_citation", "引用的证据 ID 不属于服务器快照")
            page, passage = found
            if page not in delivered:
                raise CharacterAppearanceError("appearance_evidence_not_delivered", "引用所在的页面没有有效交付回执")
            document = snapshot["documents"][passage["document"]]
            start, end = citation.start, citation.end
            if start is None or end is None:
                text = document["text"][passage["start"] : passage["end"]]
                found_at = text.find(citation.quote)
                if found_at < 0:
                    raise CharacterAppearanceError("appearance_invalid_citation", "引用原句不在该服务器证据片段内")
                if text.find(citation.quote, found_at + 1) >= 0:
                    raise CharacterAppearanceError(
                        "appearance_ambiguous_quote", "原句在该片段出现多次；请提供更完整的唯一原句或明确start/end"
                    )
                start = passage["start"] + found_at
                end = start + len(citation.quote)
            if not passage["start"] <= start < end <= passage["end"]:
                raise CharacterAppearanceError("appearance_invalid_citation", "引用位置不在该证据片段内")
            if document["text"][start:end] != citation.quote:
                raise CharacterAppearanceError("appearance_invalid_citation", "引用文字不是原始正文指定区间的精确切片")
            identity = (citation.evidence_id, start, end)
            if identity not in seen:
                seen.add(identity)
                resolved.append(
                    {
                        **citation.model_dump(),
                        "start": start,
                        "end": end,
                        "path": document["path"],
                        "page": page,
                        "offset_unit": "raw_source_python_unicode_codepoints",
                        "provenance_verified": True,
                        "interpretation_verified": False,
                    }
                )
        return resolved

    def _next_version(self, character_name: str) -> int:
        parent = self.root / "proposals"
        guard_local_path(self.project_dir, parent)
        versions = [self._load(path) for path in parent.glob("cap_*.json")]
        return 1 + max(
            (item["version"] for item in versions if item.get("character_name") == character_name), default=0
        )

    def save(self, request: SaveCharacterAppearanceProposalRequest, user_id: str, caller_source: str) -> dict[str, Any]:
        with self.projects._project_lock(self.project_name):
            snapshot = self._snapshot(request.snapshot_id)
            if snapshot["revision"] != request.snapshot_revision:
                raise CharacterAppearanceError("appearance_snapshot_stale", "快照 revision 不符，请使用服务器返回值")
            project = self.projects._read_project_raw_unlocked(self.project_name)
            self._require_basis(self._current_basis(project, snapshot["character_name"]), snapshot["basis"]["revision"])
            if not snapshot["pages"]:
                raise CharacterAppearanceError("appearance_no_matches", "没有人物关键词命中，不能保存为原文外貌提案")
            delivered = {self._receipt(snapshot, receipt_id, user_id)["page"] for receipt_id in request.receipt_ids}
            if request.coverage == "all_match_contexts" and delivered != set(range(len(snapshot["pages"]))):
                raise CharacterAppearanceError(
                    "appearance_incomplete_delivery",
                    "尚未交付全部匹配上下文页，不能标记 all_match_contexts",
                    params={"delivered_page_count": len(delivered), "page_count": len(snapshot["pages"])},
                )
            draft = request.proposal.model_dump(mode="json")
            if len(json.dumps(draft, ensure_ascii=False)) > _MAX_DRAFT_CHARACTERS:
                raise CharacterAppearanceError(
                    "appearance_proposal_too_large", "提案超过有界读取上限，请精简事实和重复引文"
                )
            resolved = self._resolve_citations(snapshot, _citation_inputs(request), delivered)
            reference_paths = {item["path"] for item in snapshot["basis"]["reference_files"]}
            for note in request.proposal.reference_notes:
                if note.reference_path is not None and note.reference_path not in reference_paths:
                    raise CharacterAppearanceError(
                        "appearance_invalid_reference_note", "参考说明路径不属于冻结的角色参考身份"
                    )
            if request.parent_proposal_id is not None:
                parent = self._proposal(request.parent_proposal_id)
                if parent["character_name"] != snapshot["character_name"]:
                    raise CharacterAppearanceError("appearance_invalid_parent", "前一版提案属于另一个角色")
            selections = []
            for stage in request.proposal.stages:
                if stage.base_description is not None:
                    selections.append(
                        {
                            "selection_id": "csel_" + uuid4().hex,
                            "stage_id": stage.stage_id,
                            "target": "base",
                            "description": stage.base_description,
                            "derivative_name": None,
                        }
                    )
                for derivative in stage.derivatives:
                    name = validate_asset_name(derivative.name)
                    selections.append(
                        {
                            "selection_id": "csel_" + uuid4().hex,
                            "stage_id": stage.stage_id,
                            "target": "derivative",
                            "description": derivative.description,
                            "derivative_name": name,
                        }
                    )
            proposal_id = "cap_" + uuid4().hex
            proposal = _versioned(
                {
                    "schema_version": 1,
                    "proposal_id": proposal_id,
                    "version": self._next_version(snapshot["character_name"]),
                    "parent_proposal_id": request.parent_proposal_id,
                    "character_name": snapshot["character_name"],
                    "snapshot_id": snapshot["snapshot_id"],
                    "snapshot_revision": snapshot["revision"],
                    "created_at": _now(),
                    "created_by": {"user_id": user_id, "source": caller_source},
                    "basis": snapshot["basis"],
                    "coverage": request.coverage,
                    "delivery": {
                        "receipt_ids": list(dict.fromkeys(request.receipt_ids)),
                        "delivered_page_count": len(delivered),
                        "page_count": len(snapshot["pages"]),
                        "proves": "tool_delivery_only_not_model_understanding",
                    },
                    "draft": draft,
                    "verified_citations": resolved,
                    "selections": selections,
                    "source_facts_are": "analyst_interpretations_with_verified_quotations_not_server_semantic_verification",
                    "references_are": "file_identities_and_unverified_caller_notes_not_server_visual_recognition",
                }
            )
            self._write(self._path("proposals", proposal_id), proposal)
        return {
            "proposal": proposal_view(proposal),
            "currentness": "current",
            "applied": False,
            "project_assets_changed": False,
        }

    def get(self, proposal_id: str) -> dict[str, Any]:
        with self.projects._project_lock(self.project_name):
            proposal = self._proposal(proposal_id)
            state = self._state(proposal)
            expected = state["expected_basis_revision"] if state is not None else proposal["basis"]["revision"]
            try:
                project = self.projects._read_project_raw_unlocked(self.project_name)
                basis = self._current_basis(project, proposal["character_name"])
                current = basis["revision"] == expected
                issues = (
                    [] if current else [{"code": "appearance_basis_stale", "detail": "当前依据与冻结/已提交的依据不同"}]
                )
            except CharacterAppearanceError as exc:
                basis = None
                current = False
                issues = [{"code": exc.code, "detail": exc.detail, "params": exc.params}]
            except (OSError, ValueError) as exc:
                basis = None
                current = False
                issues = [{"code": "appearance_current_basis_unavailable", "detail": str(exc)}]
        return {
            "proposal": proposal_view(proposal),
            "currentness": ("applied_current" if state else "current") if current else "stale",
            "basis_is_current": current,
            "frozen_basis_revision": proposal["basis"]["revision"],
            "frozen_basis_is_current": basis is not None and basis["revision"] == proposal["basis"]["revision"],
            "expected_basis_revision": expected,
            "current_basis_revision": basis["revision"] if basis else None,
            "application_state": state,
            "stale_reasons": issues,
        }

    def apply(
        self, request: ApplyCharacterAppearanceProposalRequest, user_id: str, caller_source: str
    ) -> dict[str, Any]:
        proposal = self._proposal(request.proposal_id)
        if proposal["revision"] != request.proposal_revision:
            raise CharacterAppearanceError(
                "appearance_proposal_revision_mismatch", "提案 revision 不符，请重新读取选定版本"
            )
        selection = next(
            (item for item in proposal["selections"] if item["selection_id"] == request.selection_id), None
        )
        if selection is None or selection["target"] != request.target:
            raise CharacterAppearanceError("appearance_invalid_selection", "选中的服务器 selection_id 与应用目标不符")
        if (
            request.target == "derivative"
            and validate_asset_name(request.derivative_name) != selection["derivative_name"]
        ):
            raise CharacterAppearanceError("appearance_invalid_selection", "选中的衍生名称与明确应用目标不符")
        state_path = self._path("applications", request.proposal_id)
        audit_id = "caa_" + uuid4().hex
        audit_path = self._path("audit", audit_id)
        pending: dict[str, Any] = {}

        def mutate(project: dict[str, Any]) -> None:
            character_name, entry = canonical_character(project, request.character_name)
            if character_name != proposal["character_name"]:
                raise CharacterAppearanceError("appearance_target_mismatch", "提案只能应用到其冻结的本体角色")
            # Re-read server state and recompute the full live basis inside the real write lock.
            state = self._state(proposal)
            before_basis = self._current_basis(project, character_name)
            expected = state["expected_basis_revision"] if state is not None else proposal["basis"]["revision"]
            self._require_basis(before_basis, expected)
            applied = dict(state["applied_selections"]) if state else {}
            if request.selection_id in applied:
                pending["already_applied"] = True
                pending["audit_id"] = applied[request.selection_id]
                return
            if request.target == "base":
                before_description = entry.get("description", "")
                entry["description"] = selection["description"]
            else:
                normalized = normalize_agent_derivatives(
                    {selection["derivative_name"]: {"description": selection["description"]}},
                    spec=ASSET_SPECS["character"],
                    field_path="character_appearance",
                )
                table = entry.get("derivatives")
                previous_name = find_derivative_name(table, selection["derivative_name"])
                before_description = (
                    table[previous_name].get("description", "") if isinstance(table, dict) and previous_name else ""
                )
                merge_agent_derivatives(entry, normalized)
            after_basis = self._current_basis(project, character_name)
            if (
                before_basis["source_revision"] != after_basis["source_revision"]
                or before_basis["reference_files"] != after_basis["reference_files"]
            ):
                raise CharacterAppearanceError("appearance_basis_stale", "应用过程中原文或参考文件发生变化，已拒绝提交")
            audit = _versioned(
                {
                    "schema_version": 1,
                    "audit_id": audit_id,
                    "proposal_id": proposal["proposal_id"],
                    "proposal_revision": proposal["revision"],
                    "selection_id": request.selection_id,
                    "character_name": character_name,
                    "target": request.target,
                    "derivative_name": selection["derivative_name"],
                    "before_description_digest": prefixed_canonical_json_digest(before_description),
                    "after_description_digest": prefixed_canonical_json_digest(selection["description"]),
                    "before_basis_revision": before_basis["revision"],
                    "result_basis_revision": after_basis["revision"],
                    "applied_by": {"user_id": user_id, "source": caller_source},
                    "applied_at": _now(),
                }
            )
            applied[request.selection_id] = audit_id
            pending.update(
                {
                    "already_applied": False,
                    "audit_id": audit_id,
                    "audit": audit,
                    "state": _versioned(
                        {
                            "schema_version": 1,
                            "proposal_id": proposal["proposal_id"],
                            "proposal_revision": proposal["revision"],
                            "expected_basis_revision": after_basis["revision"],
                            "applied_selections": applied,
                            "previous_state_revision": state["revision"] if state else None,
                        }
                    ),
                }
            )

        def committed(_project_file: Path) -> None:
            if not pending["already_applied"]:
                self._write(audit_path, pending["audit"])
                self._write(state_path, pending["state"])

        project_file = self.project_dir / self.projects.PROJECT_FILE
        with self.projects._project_lock(self.project_name):
            state = self._state(proposal)
            if state is not None and request.selection_id in state["applied_selections"]:
                project = self.projects._read_project_raw_unlocked(self.project_name)
                canonical, _ = canonical_character(project, request.character_name)
                if canonical != proposal["character_name"]:
                    raise CharacterAppearanceError("appearance_target_mismatch", "提案只能应用到其冻结的本体角色")
                self._require_basis(self._current_basis(project, canonical), state["expected_basis_revision"])
                pending.update({"already_applied": True, "audit_id": state["applied_selections"][request.selection_id]})
            else:
                # Use PM's existing lock-held normalization/write seam with its formal rollback boundary.
                with formal_write_transaction(project_file, audit_path, state_path):
                    self.projects.update_project_locked(self.project_name, mutate)
                    committed(project_file)
        if not pending["already_applied"]:
            emit_project_change_hint(self.project_name, changed_paths=[self.projects.PROJECT_FILE])
        return {
            "proposal_id": proposal["proposal_id"],
            "proposal_revision": proposal["revision"],
            "selection_id": request.selection_id,
            "character_name": proposal["character_name"],
            "target": request.target,
            "derivative_name": selection["derivative_name"],
            "description": selection["description"],
            "already_applied": pending["already_applied"],
            "audit_id": pending["audit_id"],
            "images_generated": False,
            "existing_image_currency": "reuses_generation_input_currency_comparison",
        }
