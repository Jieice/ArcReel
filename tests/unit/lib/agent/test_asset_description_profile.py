"""Materialized SDK profiles carry the shared appearance guide in every mode."""

from pathlib import Path

import pytest

from lib.agent.profile_manifest import ContentMode, load_manifest, sync_profile_to_project
from lib.infra.env_init import PROJECT_ROOT
from lib.prompts.prompt_templates import PromptTemplates
from lib.prompts.prompt_templates.builtin import BUILTIN_DIRECTORY

REFERENCE = ".claude/references/asset-description.md"


@pytest.mark.parametrize("content_mode", ["narration", "drama", "ad"])
def test_sdk_profile_materializes_shared_rules_and_leaves_project_inputs_untouched(
    tmp_path: Path, content_mode: ContentMode
) -> None:
    project_dir = tmp_path / "project"
    originals = {
        "project.json": b'{"characters":{"User":{"description":"Author text"}}}',
        "source/episode_1.txt": "原文逐字保留。".encode(),
        "scripts/episode_1.json": b'{"shots":[]}',
        "characters/User.png": b"existing-asset-image",
        "characters/refs/User.png": b"existing-reference-image",
    }
    for relative, data in originals.items():
        target = project_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    sync_profile_to_project(PROJECT_ROOT / "agent_runtime_profile", project_dir, content_mode)

    expected = PromptTemplates(BUILTIN_DIRECTORY).read_partial("shared/asset_description_rule").source.strip()
    assert (project_dir / REFERENCE).read_text(encoding="utf-8").strip() == expected
    claude = (project_dir / "CLAUDE.md").read_text(encoding="utf-8")
    assert REFERENCE in claude
    assert "自足、稳定、可直接绘制" in claude
    for skill in ("manage-project", "generate-assets"):
        text = (project_dir / ".claude" / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
        assert REFERENCE in text
    loaded = load_manifest(project_dir)
    assert loaded is not None
    manifest, _ = loaded
    assert REFERENCE in manifest.entries
    assert manifest.content_mode == content_mode
    assert {relative: (project_dir / relative).read_bytes() for relative in originals} == originals
