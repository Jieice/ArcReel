"""Evidence provenance and selective application through real temporary projects."""

from __future__ import annotations

import errno
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from lib.artifacts.visual_artifact_provenance import build_asset_sheet_visual_basis
from lib.character_appearance.basis import CharacterAppearanceError
from lib.character_appearance.models import (
    AppearanceProposalDraft,
    ApplyCharacterAppearanceProposalRequest,
    CollectCharacterEvidenceRequest,
    EvidenceCitation,
    SaveCharacterAppearanceProposalRequest,
)
from lib.character_appearance.service import CharacterAppearanceService
from lib.project.project_manager import ProjectManager

CHARACTER = "古月方源"
USER = "analyst"
BOOK = "第一节 前世\r\n古月方源穿碧绿长袍，黑发披散。\r\n第二节 重生\r\n重生后的古月方源成为少年，穿灰色长衫。"
BASE_DESCRIPTION = "少年，瘦削，鹅蛋脸，平直眉、杏眼、直鼻、薄唇，黑发中分，穿灰色长衫、深裤和黑布鞋。"
DERIVATIVE_DESCRIPTION = "相对本体改穿碧绿色长袍，长发由束起改为披散。"


@pytest.fixture
def appearance_project(tmp_path: Path) -> tuple[ProjectManager, Path, CharacterAppearanceService]:
    manager = ProjectManager(tmp_path / "data")
    project_dir = manager.create_project("demo", content_mode="drama")
    manager.create_project_metadata("demo", "人物原文", "", "drama")
    for relative, content in {
        "source/book.txt": BOOK.encode(),
        "source/afterword.txt": "方正与方源同行。".encode(),
        "characters/方源.png": b"existing sheet",
        "characters/refs/方源.png": b"existing reference",
        "characters/derivatives/方源/血袍.png": b"existing derivative sheet",
        "scripts/unchanged.json": b'{"author_text":"keep"}',
    }.items():
        path = project_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def configure(project: dict[str, Any]) -> None:
        project["source_language"] = "zh"
        project["whole_source_files"] = [
            {"source_file": "source/book.txt"},
            {"source_file": "source/afterword.txt"},
        ]
        project["characters"] = {
            CHARACTER: {
                "description": "旧的少年外貌",
                "aliases": ["方源"],
                "voice_style": "低沉",
                "character_sheet": "characters/方源.png",
                "reference_image": "characters/refs/方源.png",
                "derivatives": {
                    "血袍": {
                        "description": "旧的血袍变化",
                        "character_sheet": "characters/derivatives/方源/血袍.png",
                    },
                    "夜行衣": {"description": "黑色夜行衣", "character_sheet": ""},
                },
            },
            "方正": {"description": "孪生少年，圆眼，黑发", "aliases": ["弟弟"]},
            "古月博": {"description": "中年族长", "aliases": ["族长"]},
            "白族长": {"description": "白氏老人", "aliases": ["族长"]},
        }

    manager.update_project("demo", configure)
    return manager, project_dir, CharacterAppearanceService(manager, "demo")


def collect(service: CharacterAppearanceService, **overrides: Any) -> dict[str, Any]:
    fields = {
        "character_name": CHARACTER,
        "comparison_characters": ["方正"],
        "declared_user_constraints": ["保留已确认的面部身份"],
        **overrides,
    }
    return service.collect(CollectCharacterEvidenceRequest(**fields), USER, "embedded")


def read_all(service: CharacterAppearanceService, snapshot: dict[str, Any], user: str = USER) -> list[dict[str, Any]]:
    return [service.read(snapshot["snapshot_id"], page, user, "embedded") for page in range(snapshot["page_count"])]


def citation(passage: dict[str, Any], quote: str) -> EvidenceCitation:
    offset = passage["text"].index(quote)
    start = passage["start"] + offset
    return EvidenceCitation(evidence_id=passage["evidence_id"], start=start, end=start + len(quote), quote=quote)


def draft(pages: list[dict[str, Any]]) -> AppearanceProposalDraft:
    passage = next(passage for page in pages for passage in page["passages"] if "灰色长衫" in passage["text"])
    quote = citation(passage, "灰色长衫")
    return AppearanceProposalDraft.model_validate(
        {
            "summary": "原文明确服装，五官设计另列制作补足。",
            "stages": [
                {
                    "stage_id": "young",
                    "label": "少年造型",
                    "period_status": "unknown",
                    "period_reason": "候选的时期仍待审阅，不按文件编号推定。",
                    "source_facts": [
                        {
                            "statement": "该段写灰色长衫",
                            "citations": [quote.model_dump()],
                            "attribution": "contextual",
                            "attribution_reason": "同段点名重生后的古月方源。",
                        }
                    ],
                    "production_supplements": [
                        {
                            "statement": "脸型与眉眼鼻唇的具体形状",
                            "reason": "绘图所需的相容设计，原文没有这些细节。",
                        }
                    ],
                    "base_description": BASE_DESCRIPTION,
                    "derivatives": [
                        {
                            "name": "血袍",
                            "description": DERIVATIVE_DESCRIPTION,
                            "change_kind": "wardrobe",
                            "persistence_reason": "一个时期内持续使用的另一套衣装。",
                        }
                    ],
                }
            ],
        }
    )


def save_request(
    snapshot: dict[str, Any], pages: list[dict[str, Any]], **overrides: Any
) -> SaveCharacterAppearanceProposalRequest:
    return SaveCharacterAppearanceProposalRequest(
        snapshot_id=snapshot["snapshot_id"],
        snapshot_revision=snapshot["snapshot_revision"],
        receipt_ids=[page["receipt_id"] for page in pages],
        coverage="all_match_contexts",
        proposal=draft(pages),
        **overrides,
    )


def saved_proposal(service: CharacterAppearanceService) -> dict[str, Any]:
    snapshot = collect(service)
    return service.save(save_request(snapshot, read_all(service, snapshot)), USER, "embedded")["proposal"]


def application(
    proposal: dict[str, Any], target: str = "base", **overrides: Any
) -> ApplyCharacterAppearanceProposalRequest:
    selected = next(item for item in proposal["selections"] if item["target"] == target)
    return ApplyCharacterAppearanceProposalRequest(
        proposal_id=proposal["proposal_id"],
        proposal_revision=proposal["revision"],
        selection_id=selected["selection_id"],
        character_name=CHARACTER,
        target=target,
        derivative_name=selected["derivative_name"],
        **overrides,
    )


def protected_files(project_dir: Path) -> dict[str, bytes]:
    return {
        path.relative_to(project_dir).as_posix(): path.read_bytes()
        for root in ("source", "characters", "scripts")
        for path in (project_dir / root).rglob("*")
        if path.is_file()
    }


def test_collect_read_save_preserve_creative_files_and_distinguish_delivery(appearance_project) -> None:
    _, project_dir, service = appearance_project
    original_project = (project_dir / "project.json").read_bytes()
    protected = protected_files(project_dir)

    snapshot = collect(service)
    assert snapshot["full_source_scan"] is True
    assert snapshot["scanned_file_count"] == 2
    assert snapshot["scanned_character_count"] == len(BOOK) + len("方正与方源同行。")
    assert snapshot["delivered_page_count"] == 0
    assert snapshot["all_evidence_pages_delivered"] is False
    pages = read_all(service, snapshot)
    assert pages[-1]["all_evidence_pages_delivered"] is True
    assert pages[-1]["next_page"] is None
    result = service.save(save_request(snapshot, pages), USER, "embedded")

    assert result["currentness"] == "current"
    assert result["project_assets_changed"] is False
    assert result["proposal"]["coverage"] == "all_match_contexts"
    assert result["proposal"]["verified_citations"][0]["quote"] == "灰色长衫"
    assert result["proposal"]["verified_citations"][0]["interpretation_verified"] is False
    assert (project_dir / "project.json").read_bytes() == original_project
    assert protected_files(project_dir) == protected


def test_missing_registered_source_blocks_collection_without_creating_snapshot(appearance_project) -> None:
    _, project_dir, service = appearance_project
    (project_dir / "source" / "afterword.txt").unlink()
    with pytest.raises(CharacterAppearanceError) as caught:
        collect(service)
    assert caught.value.code == "appearance_source_blocked"
    assert not list((project_dir / "drafts" / "character_appearance" / "snapshots").glob("*.json"))


def test_raw_crlf_decomposed_unicode_and_non_bmp_quote_round_trip(appearance_project) -> None:
    _, project_dir, service = appearance_project
    text = "🙂序言\r\n古月方源说 cafe\u0301🙂。\r\n重生后穿灰色长衫。"
    (project_dir / "source" / "book.txt").write_bytes(text.encode())
    snapshot = collect(service, extra_aliases=["café"])
    pages = read_all(service, snapshot)
    passage = next(p for page in pages for p in page["passages"] if "cafe\u0301🙂" in p["text"])
    quoted = citation(passage, "cafe\u0301🙂。\r\n")
    assert quoted.start == text.index("cafe\u0301🙂")
    assert quoted.quote == text[quoted.start : quoted.end]
    proposal = draft(pages).model_dump()
    proposal["stages"][0]["source_facts"][0]["citations"] = [quoted.model_dump()]
    request = save_request(snapshot, pages).model_copy(
        update={"proposal": AppearanceProposalDraft.model_validate(proposal)}
    )
    saved = service.save(request, USER, "embedded")["proposal"]
    verified = saved["verified_citations"][0]
    assert verified["quote"] == quoted.quote
    assert verified["start"] == quoted.start
    assert verified["end"] == quoted.end


def test_unique_exact_quote_can_be_located_by_the_server_without_client_offsets(appearance_project) -> None:
    _, project_dir, service = appearance_project
    text = "🙂开头\r\n古月方源穿灰色长衫。"
    (project_dir / "source" / "book.txt").write_bytes(text.encode())
    snapshot = collect(service)
    pages = read_all(service, snapshot)
    fields = save_request(snapshot, pages).model_dump()
    quoted = fields["proposal"]["stages"][0]["source_facts"][0]["citations"][0]
    quoted.pop("start")
    quoted.pop("end")
    request = SaveCharacterAppearanceProposalRequest.model_validate(fields)
    saved = service.save(request, USER, "embedded")["proposal"]
    verified = saved["verified_citations"][0]
    assert verified["start"] == text.index("灰色长衫")
    assert verified["end"] == verified["start"] + len("灰色长衫")
    assert verified["quote"] == text[verified["start"] : verified["end"]] == "灰色长衫"


def test_repeated_quote_requires_an_explicit_interval_and_can_select_the_later_occurrence(appearance_project) -> None:
    _, project_dir, service = appearance_project
    text = "古月方源穿灰色长衫，随后换上另一件灰色长衫。"
    (project_dir / "source" / "book.txt").write_bytes(text.encode())
    snapshot = collect(service)
    pages = read_all(service, snapshot)
    fields = save_request(snapshot, pages).model_dump()
    quoted = fields["proposal"]["stages"][0]["source_facts"][0]["citations"][0]
    quoted.pop("start")
    quoted.pop("end")
    request = SaveCharacterAppearanceProposalRequest.model_validate(fields)
    original = (project_dir / "project.json").read_bytes()
    with pytest.raises(CharacterAppearanceError):
        service.save(request, USER, "embedded")
    assert not list((project_dir / "drafts" / "character_appearance" / "proposals").glob("*.json"))
    assert (project_dir / "project.json").read_bytes() == original
    quoted["start"] = text.rindex("灰色长衫")
    quoted["end"] = quoted["start"] + len("灰色长衫")
    explicit = SaveCharacterAppearanceProposalRequest.model_validate(fields)
    saved = service.save(explicit, USER, "embedded")["proposal"]
    verified = saved["verified_citations"][0]
    assert verified["start"] == text.rindex("灰色长衫")
    assert verified["end"] == quoted["end"]
    assert verified["quote"] == "灰色长衫"


def test_no_matches_reports_empty_delivery_and_cannot_read_a_nonexistent_page(appearance_project) -> None:
    _, project_dir, service = appearance_project
    for name in ("book.txt", "afterword.txt"):
        (project_dir / "source" / name).write_bytes("与角色无关的原文。".encode())
    snapshot = collect(service)
    assert snapshot["no_matches"] is True
    assert snapshot["page_count"] == 0
    assert snapshot["candidate_hit_count"] == 0
    assert snapshot["next_page"] is None
    with pytest.raises(CharacterAppearanceError) as caught:
        service.read(snapshot["snapshot_id"], 0, USER, "embedded")
    assert caught.value.code == "appearance_no_matches"


def test_dense_page_annotations_are_bounded_while_raw_text_and_all_occurrences_remain_delivered(
    appearance_project,
) -> None:
    _, project_dir, service = appearance_project
    block = "古月方源穿灰色长衫。\r\n"
    text = block * 900
    (project_dir / "source" / "book.txt").write_bytes(text.encode())
    snapshot = collect(service)
    pages = read_all(service, snapshot)
    assert len(pages) > 1
    passages = [passage for page in pages for passage in page["passages"] if passage["path"] == "source/book.txt"]
    assert passages[-1]["end"] == len(text)
    assert any(passage["candidate_annotations_truncated"] for passage in passages)
    for page in pages:
        assert len(page["passages"]) <= 4
        assert sum(len(passage["text"]) for passage in page["passages"]) <= 4000
        assert sum(len(passage["candidate_hits"]) for passage in page["passages"]) <= 24
    for passage in passages:
        assert passage["text"] == text[passage["start"] : passage["end"]]
        assert len(passage["text"]) <= 2000
        assert passage["candidate_annotations_truncated"] == (
            len(passage["candidate_hits"]) < passage["candidate_hit_count"]
        )
    for index in range(900):
        start = len(block) * index
        assert any(passage["start"] <= start and start + len(CHARACTER) <= passage["end"] for passage in passages)
    assert pages[-1]["all_evidence_pages_delivered"] is True


def test_saved_snapshot_remains_exactly_readable_after_the_current_original_changes(appearance_project) -> None:
    _, project_dir, service = appearance_project
    snapshot = collect(service)
    first_page = service.read(snapshot["snapshot_id"], 0, USER, "embedded")
    (project_dir / "source" / "book.txt").write_bytes("古月方源改穿新衣。".encode())
    read_back = service.read(snapshot["snapshot_id"], 0, USER, "mcp")
    assert read_back["snapshot_revision"] == first_page["snapshot_revision"]
    assert read_back["passages"] == first_page["passages"]
    assert read_back["delivered_page_count"] == 1


@pytest.mark.parametrize("forgery", ["quote", "evidence_id", "range", "receipt"])
def test_forged_provenance_is_rejected_without_creative_writes(appearance_project, forgery: str) -> None:
    _, project_dir, service = appearance_project
    snapshot = collect(service)
    pages = read_all(service, snapshot)
    request = save_request(snapshot, pages)
    changed = request.model_dump()
    reference = changed["proposal"]["stages"][0]["source_facts"][0]["citations"][0]
    if forgery == "quote":
        reference["quote"] = "原文并未这样写"
    elif forgery == "evidence_id":
        reference["evidence_id"] = "cae_" + "0" * 32
    elif forgery == "range":
        reference["start"], reference["end"] = 999999, 1000000
    else:
        changed["receipt_ids"] = ["car_" + "0" * 32]
    before_project = (project_dir / "project.json").read_bytes()
    with pytest.raises(CharacterAppearanceError):
        service.save(SaveCharacterAppearanceProposalRequest.model_validate(changed), USER, "embedded")
    assert (project_dir / "project.json").read_bytes() == before_project
    assert not list((project_dir / "drafts" / "character_appearance" / "proposals").glob("*.json"))


def test_full_context_coverage_requires_every_page_receipt(appearance_project) -> None:
    _, project_dir, service = appearance_project
    (project_dir / "source" / "book.txt").write_bytes(("古月方源穿灰色长衫。" + "景" * 2200).encode() * 5)
    snapshot = collect(service)
    assert snapshot["page_count"] > 1
    first = service.read(snapshot["snapshot_id"], 0, USER, "embedded")
    with pytest.raises(CharacterAppearanceError) as caught:
        service.save(save_request(snapshot, [first]), USER, "embedded")
    assert caught.value.code == "appearance_incomplete_delivery"
    partial = save_request(snapshot, [first]).model_copy(update={"coverage": "partial"})
    saved = service.save(partial, USER, "embedded")["proposal"]
    assert saved["coverage"] == "partial"
    assert saved["delivery"]["delivered_page_count"] == 1
    assert saved["delivery"]["page_count"] == snapshot["page_count"]


def test_other_users_delivery_does_not_authorize_an_unread_page_citation(appearance_project) -> None:
    _, project_dir, service = appearance_project
    text = ("古月方源穿灰色长衫。" + "景" * 2300) * 5
    (project_dir / "source" / "book.txt").write_bytes(text.encode())
    snapshot = collect(service)
    own_page = service.read(snapshot["snapshot_id"], 0, USER, "embedded")
    foreign_page = service.read(snapshot["snapshot_id"], 1, "another-analyst", "embedded")
    request = save_request(snapshot, [own_page]).model_copy(
        update={
            "coverage": "partial",
            "proposal": draft([foreign_page]),
        }
    )
    with pytest.raises(CharacterAppearanceError) as caught:
        service.save(request, USER, "embedded")
    assert caught.value.code == "appearance_evidence_not_delivered"


def test_one_source_file_can_support_distinct_semantic_life_periods(appearance_project) -> None:
    _, _, service = appearance_project
    snapshot = collect(service)
    pages = read_all(service, snapshot)
    passage = next(p for page in pages for p in page["passages"] if "前世" in p["text"] and "重生" in p["text"])
    proposed = draft(pages).model_dump()
    young = proposed["stages"][0]
    young.update({"period_status": "specified", "period_citations": [citation(passage, "重生").model_dump()]})
    previous = deepcopy(young)
    previous.update(
        {
            "stage_id": "previous_life",
            "label": "前世",
            "base_description": None,
            "period_citations": [citation(passage, "前世").model_dump()],
            "derivatives": [],
        }
    )
    proposed["stages"] = [previous, young]
    request = save_request(snapshot, pages).model_copy(
        update={"proposal": AppearanceProposalDraft.model_validate(proposed)}
    )
    saved = service.save(request, USER, "embedded")["proposal"]
    assert [stage["stage_id"] for stage in saved["draft"]["stages"]] == ["previous_life", "young"]
    assert {ref["path"] for ref in saved["verified_citations"]} == {"source/book.txt"}


@pytest.mark.parametrize(
    "change", ["source", "order", "alias", "description", "comparison", "reference", "constraints", "extra_alias"]
)
def test_changed_inputs_make_saved_proposal_readable_but_refuse_save_and_apply(appearance_project, change: str) -> None:
    manager, project_dir, service = appearance_project
    snapshot = collect(service)
    pages = read_all(service, snapshot)
    request = save_request(snapshot, pages)
    proposal = service.save(request, USER, "embedded")["proposal"]
    if change == "source":
        (project_dir / "source" / "book.txt").write_bytes((BOOK + "\r\n新原文").encode())
    elif change == "reference":
        (project_dir / "characters" / "refs" / "方源.png").write_bytes(b"changed reference")
    elif change == "constraints":
        collect(service, declared_user_constraints=["换成明确的新面部要求"])
    elif change == "extra_alias":
        collect(service, extra_aliases=["仙尊"])
    else:

        def mutate(project: dict[str, Any]) -> None:
            if change == "order":
                project["whole_source_files"].reverse()
            elif change == "alias":
                project["characters"]["方正"]["aliases"].append("兄弟")
            elif change == "description":
                project["characters"][CHARACTER]["description"] = "新的作者设定"
            else:
                project["characters"]["方正"]["description"] = "对照对象的新脸型"

        manager.update_project("demo", mutate)
    current_project = (project_dir / "project.json").read_bytes()

    read_back = service.get(proposal["proposal_id"])
    assert read_back["currentness"] == "stale"
    assert read_back["proposal"]["proposal_id"] == proposal["proposal_id"]
    assert read_back["proposal"]["draft"] == proposal["draft"]
    with pytest.raises(CharacterAppearanceError) as caught:
        service.save(request, USER, "embedded")
    assert caught.value.code == "appearance_basis_stale"
    with pytest.raises(CharacterAppearanceError) as caught:
        service.apply(application(proposal), USER, "embedded")
    assert caught.value.code == "appearance_basis_stale"
    assert (project_dir / "project.json").read_bytes() == current_project


def test_proposal_versions_remain_readable_without_rewriting_predecessor(appearance_project) -> None:
    _, _, service = appearance_project
    snapshot = collect(service)
    pages = read_all(service, snapshot)
    first = service.save(save_request(snapshot, pages), USER, "embedded")["proposal"]
    second = service.save(save_request(snapshot, pages, parent_proposal_id=first["proposal_id"]), USER, "embedded")[
        "proposal"
    ]
    assert second["version"] == first["version"] + 1
    assert second["parent_proposal_id"] == first["proposal_id"]
    assert service.get(first["proposal_id"])["proposal"]["draft"] == first["draft"]
    assert service.get(first["proposal_id"])["currentness"] == "current"


def test_base_and_derivative_application_are_selective_sequential_and_idempotent(appearance_project) -> None:
    manager, project_dir, service = appearance_project
    proposal = saved_proposal(service)
    before_characters = deepcopy(manager.load_project("demo")["characters"])
    protected = protected_files(project_dir)
    old_basis = build_asset_sheet_visual_basis(
        asset_type="character",
        asset_id=CHARACTER,
        description=before_characters[CHARACTER]["description"],
        style="",
        style_description="",
        aspect_ratio="9:16",
    )
    first = service.apply(application(proposal), USER, "embedded")
    expected = deepcopy(before_characters)
    expected[CHARACTER]["description"] = BASE_DESCRIPTION
    assert manager.load_project("demo")["characters"] == expected
    assert first["already_applied"] is False
    assert service.get(proposal["proposal_id"])["currentness"] == "applied_current"
    after_basis = build_asset_sheet_visual_basis(
        asset_type="character",
        asset_id=CHARACTER,
        description=expected[CHARACTER]["description"],
        style="",
        style_description="",
        aspect_ratio="9:16",
    )
    assert after_basis.digest != old_basis.digest

    first_project_bytes = (project_dir / "project.json").read_bytes()
    audit_files = sorted((project_dir / "drafts" / "character_appearance" / "audit").glob("*.json"))
    again = service.apply(application(proposal), USER, "embedded")
    assert again["already_applied"] is True
    assert again["audit_id"] == first["audit_id"]
    assert (project_dir / "project.json").read_bytes() == first_project_bytes
    assert sorted((project_dir / "drafts" / "character_appearance" / "audit").glob("*.json")) == audit_files

    derivative = service.apply(application(proposal, "derivative"), USER, "embedded")
    expected[CHARACTER]["derivatives"]["血袍"]["description"] = DERIVATIVE_DESCRIPTION
    assert manager.load_project("demo")["characters"] == expected
    assert derivative["images_generated"] is False
    assert protected_files(project_dir) == protected


def test_external_change_after_first_application_blocks_further_selections(appearance_project) -> None:
    manager, project_dir, service = appearance_project
    proposal = saved_proposal(service)
    service.apply(application(proposal), USER, "embedded")
    manager.update_project(
        "demo", lambda project: project["characters"][CHARACTER].update(description="作者随后亲自修改")
    )
    edited = (project_dir / "project.json").read_bytes()
    with pytest.raises(CharacterAppearanceError) as caught:
        service.apply(application(proposal, "derivative"), USER, "embedded")
    assert caught.value.code == "appearance_basis_stale"
    assert (project_dir / "project.json").read_bytes() == edited
    assert service.get(proposal["proposal_id"])["currentness"] == "stale"


def test_commit_failure_rolls_back_project_and_application_audit(
    appearance_project, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, project_dir, service = appearance_project
    proposal = saved_proposal(service)
    before = (project_dir / "project.json").read_bytes()
    replace = os.replace

    def fail_audit(source, destination, *args, **kwargs):
        target = Path(destination)
        if target.parent == project_dir / "drafts" / "character_appearance" / "audit":
            raise OSError(errno.ENOSPC, "temporary filesystem is full")
        return replace(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "replace", fail_audit)
    with pytest.raises(OSError, match="temporary filesystem is full"):
        service.apply(application(proposal), USER, "embedded")
    assert (project_dir / "project.json").read_bytes() == before
    assert not list((project_dir / "drafts" / "character_appearance" / "audit").glob("*.json"))
    loaded = service.get(proposal["proposal_id"])
    assert loaded["currentness"] == "current"
    assert loaded["application_state"] is None
