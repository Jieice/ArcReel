"""Asset planning shares drawable-description rules without rewriting its inputs."""

from copy import deepcopy
from typing import Any

import pytest

from lib.prompts.prompt_builders_ad import build_ad_prompt, build_ad_reference_prompt
from lib.prompts.prompt_builders_reference import build_reference_units_split_prompt
from lib.prompts.prompt_builders_script import build_narration_split_prompt, build_normalize_prompt
from lib.prompts.prompt_templates import PromptTemplates
from lib.prompts.prompt_templates.builtin import BUILTIN_DIRECTORY

SOURCE_CONTENT = "冷雨敲窗。小禾低头看着鞋尖，说自己长得像姐姐。"
RULE_NAME = "shared/asset_description_rule"


def _render_plan(route: str, source_kind: str, project: dict[str, Any]) -> str:
    assets = {key: project[key] for key in ("characters", "scenes", "props")}
    if route in {"ad_storyboard", "ad_reference"}:
        arguments = {
            "project_overview": {},
            "style": "水彩",
            "style_description": "柔和笔触",
            **assets,
            "products": project["products"],
            "brief": SOURCE_CONTENT,
            "target_duration": 30,
            "asset_registry": assets,
        }
        if route == "ad_storyboard":
            return build_ad_prompt(**arguments, generation_mode="storyboard", supported_durations=[4, 6])
        return build_ad_reference_prompt(**arguments)
    arguments = {
        "novel_text": SOURCE_CONTENT,
        "project_overview": {},
        **assets,
        "default_duration": 4,
        "supported_durations": [4, 6],
        "episode": 1,
    }
    if route == "narration":
        return build_narration_split_prompt(**arguments)
    if route == "drama":
        return build_normalize_prompt(**arguments, style="水彩", source_kind=source_kind)
    return build_reference_units_split_prompt(
        **arguments,
        max_duration=6,
        max_reference_images=4,
        source_kind=source_kind,
    )


@pytest.mark.parametrize(
    ("route", "source_kind", "with_product"),
    [
        ("narration", "novel", False),
        ("drama", "novel", False),
        ("drama", "screenplay", False),
        ("reference", "novel", False),
        ("reference", "screenplay", False),
        ("ad_storyboard", "novel", False),
        ("ad_storyboard", "novel", True),
        ("ad_reference", "novel", False),
        ("ad_reference", "novel", True),
    ],
)
def test_real_planning_routes_share_rules_and_preserve_source_and_existing_assets(
    route: str, source_kind: str, with_product: bool
) -> None:
    project = {
        "characters": {
            "小禾": {
                "description": "比姐姐稍矮，喜欢低头看鞋尖；这是用户已经写下的描述。",
                "aliases": ["禾禾"],
                "reference_image": "characters/refs/小禾.png",
                "character_sheet": "characters/小禾.png",
                "derivatives": {"受伤": {"description": "左颊擦伤，因失血面色苍白"}},
            }
        },
        "scenes": {"旧屋": {"description": "木墙，方窗，一张长桌"}},
        "props": {"银簪": {"description": "一支细长的素银簪"}},
        "products": {"保温杯": {"description": "蓝色圆柱形杯身，白色品牌文字", "selling_points": ["保温"]}}
        if with_product
        else {},
    }
    original = deepcopy(project)
    rule = PromptTemplates(BUILTIN_DIRECTORY).read_partial(RULE_NAME).source.strip()

    rendered = _render_plan(route, source_kind, project)

    assert rendered.count(rule) == 1
    assert SOURCE_CONTENT in rendered
    assert original["characters"]["小禾"]["description"] in rendered
    assert "`merge` 与 `skip` 的 `description` 留空" in rendered
    assert "`description` 只写相对本体的变化" in rendered
    assert project == original


@pytest.mark.parametrize("asset_type", ["character", "character_derivative", "scene", "prop", "product"])
def test_asset_image_prompts_keep_their_existing_description_and_layout_contract(asset_type: str) -> None:
    description = "左颊擦伤，因失血面色苍白；保留用户指定的既有外观。"
    templates = PromptTemplates(BUILTIN_DIRECTORY)

    rendered = templates.render(
        "asset/sheet",
        asset_type=asset_type,
        name="小禾",
        description=description,
        style=None,
        style_description=None,
    )

    assert description in rendered
    assert templates.read_partial(RULE_NAME).source.strip() not in rendered
    if asset_type == "character_derivative":
        assert "除上述变化外" in rendered
    elif asset_type == "product":
        assert "不得改变或臆造" in rendered
