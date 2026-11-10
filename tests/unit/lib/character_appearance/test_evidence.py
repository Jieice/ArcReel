"""Original-source registration, ambiguous names, and bounded complete match delivery."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from lib.character_appearance.basis import CharacterAppearanceError, compute_appearance_basis
from lib.character_appearance.evidence import build_alias_index, build_documents
from lib.project.source_revision import SourceFileRead


def source(text: str, path: str = "source/book.txt") -> SourceFileRead:
    return SourceFileRead(name=Path(path).name, rel_path=path, text=text)


def test_corpus_includes_registered_own_originals_and_excludes_copies_and_unregistered_files(tmp_path: Path) -> None:
    project = {
        "characters": {"古月方源": {"description": "少年", "aliases": ["方源"]}},
        "whole_source_files": [{"source_file": "source/z.txt"}, {"source_file": "source/a.md"}],
        "episodes": [
            {"episode": 3, "source_origin": "own"},
            {"episode": 7, "source_origin": "whole_source"},
            {"episode": 4, "source_origin": "none"},
        ],
    }
    originals = {"z.txt": "🙂古月方源\r\n前世", "a.md": "方源重生。", "episode_3.txt": "方源的新原文。"}
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    for name, text in originals.items():
        (source_dir / name).write_bytes(text.encode())
    for name in ("episode_7.txt", "episode_4.txt", "unregistered.txt"):
        (source_dir / name).write_bytes("这个副本也含古月方源。".encode())

    basis, reads = compute_appearance_basis(tmp_path, project, "古月方源", {})
    assert [read.rel_path for read in reads] == ["source/z.txt", "source/a.md", "source/episode_3.txt"]
    assert [read.text for read in reads] == list(originals.values())
    for name in ("episode_7.txt", "episode_4.txt", "unregistered.txt"):
        (source_dir / name).write_bytes("任意副本改动不属于原文依据。".encode())
    unchanged, _ = compute_appearance_basis(tmp_path, project, "古月方源", {})
    assert unchanged["revision"] == basis["revision"]

    reordered = deepcopy(project)
    reordered["whole_source_files"].reverse()
    changed, ordered_reads = compute_appearance_basis(tmp_path, reordered, "古月方源", {})
    assert changed["revision"] != basis["revision"]
    assert [read.rel_path for read in ordered_reads] == ["source/a.md", "source/z.txt", "source/episode_3.txt"]
    (source_dir / "episode_3.txt").unlink()
    with pytest.raises(CharacterAppearanceError) as caught:
        compute_appearance_basis(tmp_path, project, "古月方源", {})
    assert caught.value.code == "appearance_source_blocked"
    assert caught.value.params["blockers"][0]["path"] == "source/episode_3.txt"


def test_unregistered_text_alone_does_not_authorize_full_original_analysis(tmp_path: Path) -> None:
    (tmp_path / "source").mkdir()
    (tmp_path / "source" / "orphan.txt").write_bytes("古月方源穿灰色长衫。".encode())
    project = {"characters": {"古月方源": {"description": "少年"}}, "whole_source_files": [], "episodes": []}
    with pytest.raises(CharacterAppearanceError) as caught:
        compute_appearance_basis(tmp_path, project, "古月方源", {})
    assert caught.value.code == "appearance_no_registered_source"


@pytest.mark.parametrize(
    ("name", "text", "expected_starts"),
    [
        ("古月方源", "古月方源" * 1500, list(range(0, 6000, 4))),
        ("阿阿", "阿" * 6000, list(range(5999))),
    ],
    ids=["dense", "overlapping"],
)
def test_dense_and_overlapping_occurrences_survive_every_passage_split(
    name: str,
    text: str,
    expected_starts: list[int],
) -> None:
    registry = [{"name": name, "aliases": []}]
    aliases, _ = build_alias_index(registry, name, [])
    documents, pages = build_documents([source(text)], aliases, registry)
    assert [hit["start"] for hit in documents[0]["hits"]] == expected_starts
    passages = [passage for page in pages for passage in page["passages"]]
    assert len(pages) > 1
    assert passages[0]["start"] == 0
    assert passages[-1]["end"] == len(text)
    for start in expected_starts:
        assert any(passage["start"] <= start and start + len(name) <= passage["end"] for passage in passages)
    for page in pages:
        assert len(page["passages"]) <= 4
        assert sum(item["end"] - item["start"] for item in page["passages"]) <= 4000
        assert all(0 < item["end"] - item["start"] <= 2000 for item in page["passages"])


def test_distant_matches_and_last_document_are_delivered_without_including_the_entire_book() -> None:
    registry = [{"name": "古月方源", "aliases": []}]
    aliases, _ = build_alias_index(registry, "古月方源", [])
    block = "古月方源穿灰色长衫。" + "景" * 3000
    text = block * 12
    tail = "第十三章 最后\r\n古月方源换上黑衣。"
    documents, pages = build_documents([source(text), source(tail, "source/tail.txt")], aliases, registry)
    assert [len(document["hits"]) for document in documents] == [12, 1]
    assert [hit["start"] for hit in documents[0]["hits"]] == [len(block) * index for index in range(12)]
    assert sum(page["characters"] for page in pages) < len(text) + len(tail)
    assert pages[-1]["passages"][-1]["document"] == 1
    assert pages[-1]["passages"][-1]["end"] == len(tail)
    assert [page["page"] for page in pages] == list(range(len(pages)))


def test_shared_titles_stay_ambiguous_and_nearby_aliases_return_canonical_character_names() -> None:
    registry = [
        {"name": "古月方源", "aliases": ["方源", "弟弟", "他"]},
        {"name": "古月方正", "aliases": ["方正", "弟弟"]},
    ]
    aliases, ignored = build_alias_index(registry, "古月方源", ["自己", "He"])
    assert {item["term"] for item in ignored} == {"他", "自己", "He"}
    assert not {"他", "自己", "He"} & {item["term"] for item in aliases}
    title = next(item for item in aliases if item["term"] == "弟弟")
    assert title["candidate_owners"] == ["古月方正", "古月方源"]
    assert set(title["ambiguity_reasons"]) == {"shared_alias", "generic_title"}

    documents, _ = build_documents([source("方源与方正同行，弟弟转身。他独自说话。")], aliases, registry)
    brother = next(hit for hit in documents[0]["hits"] if hit["term"] == "弟弟")
    assert brother["nearby_character_names"] == ["古月方源", "古月方正"]
    assert "nearby_other_characters" in brother["ambiguity_reasons"]
    assert brother["attribution"] == "candidate_only"
    assert all(hit["requires_context_review"] for hit in documents[0]["hits"])


def test_chapter_hints_describe_match_locations_without_turning_chapters_into_life_stages() -> None:
    text = "第一章 前世\r\n古月方源穿碧绿长袍。" + "景" * 1200 + "\r\n第二章 重生\r\n古月方源穿灰色长衫。"
    registry = [{"name": "古月方源", "aliases": []}]
    aliases, _ = build_alias_index(registry, "古月方源", [])
    documents, _ = build_documents([source(text)], aliases, registry)
    assert [hit["nearest_chapter_heading"] for hit in documents[0]["hits"]] == ["第一章 前世", "第二章 重生"]
    assert "stages" not in documents[0]
