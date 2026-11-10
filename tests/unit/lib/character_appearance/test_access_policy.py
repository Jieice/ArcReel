"""Server-owned analysis records reject builtin writes through the real access policy."""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.character_appearance.paths import CHARACTER_APPEARANCE_RELATIVE_PATH
from lib.infra.data_root_layout import DataRootLayout
from server.agent_runtime.agent_access_policy import AgentAccessPolicy
from server.agent_runtime.options_assembler import OptionsAssembler


@pytest.fixture(params=[True, False], ids=["sandbox", "windows-fallback"])
def appearance_access_policy(tmp_path: Path, request: pytest.FixtureRequest) -> tuple[AgentAccessPolicy, Path]:
    data_root = tmp_path / "data"
    cwd = DataRootLayout(data_root).projects_dir / "demo"
    cwd.mkdir(parents=True)
    policy = AgentAccessPolicy(
        project_root=tmp_path / "repo",
        data_root=data_root,
        agent_profile_root=tmp_path / "profile",
        claude_projects_dir=tmp_path / "claude" / "projects",
        sandbox_enabled=request.param,
    )
    return policy, cwd


@pytest.mark.parametrize("tool_name", ["Write", "Edit"])
@pytest.mark.parametrize(
    "partition", ["snapshots", "contexts", "receipts/cas_sample", "proposals", "applications", "audit"]
)
def test_builtin_writes_cannot_bypass_server_owned_analysis_records(
    appearance_access_policy, tool_name: str, partition: str
) -> None:
    policy, cwd = appearance_access_policy
    relative = Path(CHARACTER_APPEARANCE_RELATIVE_PATH) / partition / "record.json"
    target = cwd / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(b'{"server_owned":true}')
    allowed, reason = policy.check_path_access(str(relative), tool_name, cwd, user_id="analyst")
    assert allowed is False
    assert "character_evidence" in reason or "character_appearance_proposal" in reason
    assert target.read_bytes() == b'{"server_owned":true}'


@pytest.mark.parametrize("tool_name", ["Write", "Edit"])
@pytest.mark.parametrize("spelling", ["absolute", "dot_segments", "uppercase"])
def test_normal_path_spellings_retain_the_same_analysis_write_protection(
    appearance_access_policy, tool_name: str, spelling: str
) -> None:
    policy, cwd = appearance_access_policy
    relative = f"{CHARACTER_APPEARANCE_RELATIVE_PATH}/proposals/new.json"
    if spelling == "absolute":
        path = str(cwd / relative)
    elif spelling == "dot_segments":
        path = "drafts/temporary/../character_appearance/./proposals/new.json"
    else:
        path = relative.upper()
    allowed, reason = policy.check_path_access(path, tool_name, cwd, user_id="analyst")
    assert allowed is False
    assert reason


@pytest.mark.parametrize("tool_name", ["Write", "Edit"])
def test_analysis_reading_and_ordinary_temporary_draft_writes_remain_available(
    appearance_access_policy, tool_name: str
) -> None:
    policy, cwd = appearance_access_policy
    allowed, reason = policy.check_path_access(
        f"{CHARACTER_APPEARANCE_RELATIVE_PATH}/proposals/record.json", "Read", cwd, user_id="analyst"
    )
    assert (allowed, reason) == (True, None)
    for path in ("drafts/research.md", "drafts/character_appearance_notes.json", "drafts/episode_1/scratch.txt"):
        allowed, reason = policy.check_path_access(path, tool_name, cwd, user_id="analyst")
        assert (allowed, reason) == (True, None)


def test_sandbox_projection_contains_the_analysis_subtree(appearance_access_policy) -> None:
    policy, cwd = appearance_access_policy
    settings = policy.build_sandbox_settings(cwd)
    if not policy.sandbox_enabled:
        assert settings == {"enabled": False}
        return
    assert str(cwd / CHARACTER_APPEARANCE_RELATIVE_PATH) in settings["filesystem"]["denyWrite"]
    assert settings["allowUnsandboxedCommands"] is False


@pytest.mark.parametrize("tool_name", ["Write", "Edit"])
async def test_public_sdk_options_attach_deny_hooks_even_when_builtin_tools_are_allowed(
    appearance_access_policy, tool_name: str
) -> None:
    policy, cwd = appearance_access_policy

    async def credential_environment() -> dict[str, str]:
        return {}

    assembler = OptionsAssembler(
        data_root=policy.data_root,
        allowed_tools=["Read", "Write", "Edit"],
        setting_sources=[],
        access_policy_provider=lambda: policy,
        max_turns_provider=lambda: None,
        resolve_project_cwd=lambda _name: cwd,
        provider_env_loader=credential_environment,
        user_id_provider=lambda: "analyst",
    )
    options = await assembler.build("demo")
    assert tool_name in options.allowed_tools
    input_data = {
        "tool_name": tool_name,
        "tool_input": {"file_path": f"{CHARACTER_APPEARANCE_RELATIVE_PATH}/proposals/new.json", "content": "{}"},
    }
    outcomes = [
        await hook(input_data, "builtin-record-write", None)
        for matcher in options.hooks["PreToolUse"]
        if matcher.matcher is None
        for hook in matcher.hooks
    ]
    assert any(outcome.get("hookSpecificOutput", {}).get("permissionDecision") == "deny" for outcome in outcomes)
