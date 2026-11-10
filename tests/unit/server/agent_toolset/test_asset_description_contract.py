"""Description guidance is exposed by the real schemas without changing values."""

from copy import deepcopy

import pytest

from lib.script.script_models import NewAssetDecision, PlanNewAsset
from server.agent_toolset.repair_channel import PATCH_PROJECT
from server.tool_runtime import PatchProjectRequest


def test_actual_schema_fields_expose_base_and_derivative_description_guidance() -> None:
    planned = PlanNewAsset.model_json_schema()["properties"]["description"]
    patched = PATCH_PROJECT.input_schema["properties"]["entries"]

    assert "自足、稳定、可直接绘制" in planned["description"]
    assert "相对本体的外观变化" in planned["description"]
    assert planned["default"] == ""
    assert planned["type"] == "string"
    assert "自足、稳定、可直接绘制" in patched["description"]
    assert "相对本体的变化" in patched["description"]
    assert patched["default"] is None
    assert "自足、稳定、可直接绘制" in PATCH_PROJECT.description
    assert set(PATCH_PROJECT.input_schema["properties"]) == {"table", "entries", "settings", "overview"}


@pytest.mark.parametrize(
    ("decision", "description"),
    [
        ("register", "像姐姐，喜欢低头看鞋尖；这是用户明确写下的文本。"),
        ("derivative", "左颊擦伤，因失血面色苍白"),
        ("merge", ""),
        ("skip", ""),
    ],
)
def test_planning_model_preserves_author_text_and_existing_decision_fields(
    decision: NewAssetDecision, description: str
) -> None:
    entry = PlanNewAsset(type="character", name="小禾", decision=decision, reason="原文依据", description=description)

    assert entry.description == description
    assert entry.decision == decision
    assert set(entry.model_dump()) == {
        "type",
        "name",
        "decision",
        "reason",
        "description",
        "aliases",
        "target",
        "asset_name",
    }


def test_patch_request_keeps_author_text_and_asset_image_fields_unchanged() -> None:
    entries = {
        "小禾": {
            "description": "比姐姐稍矮，喜欢低头看鞋尖；保留用户的原句。",
            "character_sheet": "characters/小禾.png",
            "reference_image": "characters/refs/小禾.png",
            "derivatives": {"受伤": {"description": "左颊擦伤，因失血面色苍白"}},
        }
    }
    original = deepcopy(entries)

    request = PatchProjectRequest(table="characters", entries=entries)

    assert request.entries == original
    assert entries == original
