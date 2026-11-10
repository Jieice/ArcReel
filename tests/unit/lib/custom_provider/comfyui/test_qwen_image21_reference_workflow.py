"""Qwen Image 2.1 reference slots survive inference and shrink with each request."""

import json
from pathlib import Path
from random import Random

import pytest

from arcreel_market_core.endpoint_definition import validate_definition
from lib.backends.image_backends.base import ImageCapability
from lib.custom_provider.comfyui.comfyui_image_backend import binding_image_capabilities, binding_reference_limit
from lib.custom_provider.comfyui.inference import InferenceNote, infer_bindings
from lib.custom_provider.comfyui.inference_rules import load_inference_rules
from lib.custom_provider.comfyui.request_builder import MediaInputs, build_workflow

DEFINITION_PATH = Path(__file__).resolve().parents[5] / "api-workflows" / "qwen21_i2i_4ref_api_definition.json"


@pytest.fixture
def definition():
    return json.loads(DEFINITION_PATH.read_text(encoding="utf-8"))


def test_the_endpoint_offers_four_references_and_only_image_to_image(definition):
    assert validate_definition(definition).valid
    assert binding_reference_limit(definition) == 4
    assert binding_image_capabilities(definition) == frozenset({ImageCapability.IMAGE_TO_IMAGE})


@pytest.mark.parametrize("reference_count", [1, 2, 3, 4])
def test_request_uses_each_reference_once_and_removes_empty_slots(definition, reference_count):
    references = tuple(f"uploaded/reference-{slot}.png" for slot in range(reference_count))
    original_workflow = json.loads(json.dumps(definition["workflow"]))

    built = build_workflow(
        definition,
        prompt="人物沿石阶向山门走去\n\nAvoid: 水印、文字",
        aspect_ratio="16:9",
        media=MediaInputs(reference_images=references),
        rng=Random(17),
    )

    targets = definition["bindings"]["reference_images"]
    encoder = built.workflow["4"]["inputs"]
    for slot, target in enumerate(targets):
        node_id = target["node"]
        input_name = target["consumer"]["input"]
        if slot < reference_count:
            assert built.workflow[node_id]["inputs"]["image"] == references[slot]
            assert encoder[input_name] == [node_id, 0]
        else:
            assert node_id not in built.workflow
            assert input_name not in encoder
    assert set(built.dropped_nodes) == {target["node"] for target in targets[reference_count:]}
    assert built.workflow["7"]["inputs"]["images"] == ["6", 0]
    assert encoder["prompt"] == "人物沿石阶向山门走去"
    assert encoder["negative_prompt"] == "水印、文字"
    assert built.workflow["5"]["inputs"]["model"] == definition["workflow"]["5"]["inputs"]["model"]
    assert built.seed != definition["workflow"]["5"]["inputs"]["seed"]
    assert definition["workflow"] == original_workflow


@pytest.mark.parametrize(("aspect_ratio", "expected_size"), [("16:9", (1536, 864)), ("9:16", (864, 1536))])
def test_native_size_follows_the_project_ratio_without_node_rounding(definition, aspect_ratio, expected_size):
    built = build_workflow(
        definition,
        prompt="一个国风3D场景",
        aspect_ratio=aspect_ratio,
        media=MediaInputs(reference_images=("scene.png",)),
    )

    assert (built.width, built.height) == expected_size
    assert (
        built.workflow["4"]["inputs"]["latent_width"],
        built.workflow["4"]["inputs"]["latent_height"],
    ) == expected_size
    assert all(edge % 32 == 0 for edge in expected_size)


def test_inference_rebuilds_consumers_after_the_workflow_is_reimported(definition):
    for target in definition["bindings"]["reference_images"]:
        target["consumer"] = {"node": "999", "input": "old_port", "class_type": "OldEncoder"}

    result = infer_bindings(definition)

    targets = result.keys["reference_images"].selected_targets
    assert result.savable
    assert [target["node"] for target in targets] == ["8", "20", "21", "22"]
    assert [target["consumer"]["input"] for target in targets] == ["image_01", "image_02", "image_03", "image_04"]
    assert {target["consumer"]["node"] for target in targets} == {"4"}
    assert InferenceNote.REFERENCE_CONSUMER_UNKNOWN not in {note.code for note in result.keys["reference_images"].notes}
    assert result.keys["width"].selected_targets[0]["step"] == 32
    assert result.keys["height"].selected_targets[0]["step"] == 32


def test_inference_discovers_all_reference_consumers_without_saved_bindings(definition):
    definition["bindings"].pop("reference_images")

    result = infer_bindings(definition)

    assert [target["consumer"]["input"] for target in result.keys["reference_images"].selected_targets] == [
        "image_01",
        "image_02",
        "image_03",
        "image_04",
    ]


@pytest.mark.parametrize("media_type", ["image", "video"])
def test_optional_reference_prefix_is_restricted_to_the_gh_encoder(media_type):
    rules = load_inference_rules(media_type)

    assert all(rules.is_optional_input("TextEncodeQwenImage21GH", f"image_{slot:02}") for slot in range(1, 11))
    assert not rules.is_optional_input("SomeOtherEncoder", "image_01")
    assert not rules.is_optional_input("TextEncodeQwenImage21GH", "vae")
    if media_type == "image":
        ports = rules.consumer_ports["reference_images"]
        assert any(port.matches("image_04", "TextEncodeQwenImage21GH") for port in ports)
        assert not any(port.matches("image_04", "SomeOtherEncoder") for port in ports)
