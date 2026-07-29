import os
import subprocess
import tomllib
from pathlib import Path


def test_skill_launcher_resolves_canonical_repo_through_directory_symlink(tmp_path):
    repo = Path(__file__).parents[1].resolve()
    canonical_skill = repo / "skills" / "agent-note"
    linked_skill = tmp_path / "codex-skills" / "agent-note"
    linked_skill.parent.mkdir()
    linked_skill.symlink_to(canonical_skill, target_is_directory=True)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$@\"\n",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)

    unrelated = tmp_path / "unrelated-project"
    unrelated.mkdir()
    result = subprocess.run(
        [str(linked_skill / "scripts" / "agent-note"), "tags"],
        cwd=unrelated,
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        text=True,
        capture_output=True,
        check=True,
    )

    assert result.stderr == ""
    assert result.stdout.splitlines() == [
        "run",
        "--project",
        str(repo),
        "agent-note",
        "tags",
    ]


def test_skill_keeps_reasoning_in_instructions_and_enforcement_in_cli():
    repo = Path(__file__).parents[1]
    skill = (repo / "skills" / "agent-note" / "SKILL.md").read_text()
    durable_capture = (
        repo
        / "skills"
        / "agent-note"
        / "references"
        / "durable-capture.md"
    ).read_text()
    import_reference = (
        repo
        / "skills"
        / "agent-note"
        / "references"
        / "conversation-import.md"
    ).read_text()
    skill_text = " ".join(skill.split())
    durable_text = " ".join(durable_capture.split())
    import_text = " ".join(import_reference.split())

    assert "Do not create, edit, delete, or search note-store files directly" in (
        skill_text
    )
    assert "durable, useful note that remains valuable" in skill_text
    assert "do not merely shorten it or produce a generic summary" in skill_text
    assert "Save only when the user explicitly requests durable capture" in skill_text
    assert "Write complete standalone content" in skill_text
    assert "Never save credentials, secrets, tokens" in skill_text
    assert "why it matters or the problem it solves" in durable_text
    assert "meaningful limits or constraints" in durable_text
    assert "Include a next step only when one is present" in durable_text
    assert "preserve the choice and the reason or context" in durable_text
    assert "preserve the preference and when it applies" in durable_text
    assert "Distinguish established facts from assumptions, proposals" in (
        durable_text
    )
    assert "Do not convert speculation into fact" in durable_text
    assert "broad session handoff as the first derived note" in import_text
    assert "Search for the main durable subjects before writing focused notes" in (
        import_text
    )
    assert "concise synthesis rather than" in import_text
    assert "label every note a summary" in import_text
    assert "assumptions, proposals, and unresolved" in import_text
    assert "Raw preservation alone is not completion" in skill_text
    assert "fallback" not in skill_text.lower()


def test_conversation_import_uses_lightweight_two_pass_coverage_check():
    repo = Path(__file__).parents[1]
    import_reference = (
        repo
        / "skills"
        / "agent-note"
        / "references"
        / "conversation-import.md"
    ).read_text()
    text = " ".join(import_reference.split())

    identify = "Before drafting notes, identify the conversation's genuinely durable"
    broad = "Create one broad session handoff as the first derived note"
    coverage = "Do a brief coverage check against the working list"

    assert identify in text
    assert "ideas, decisions, preferences, actions or next steps, corrections" in text
    assert "unresolved questions—but only when they exist" in text
    assert text.index(identify) < text.index(broad) < text.index(coverage)
    assert "each identified important item appears in the broad handoff" in text
    assert "add or expand only what is missing" in text
    assert "Do not copy every turn, create a note per sentence" in text
    assert "use a fixed note count" in text
    assert "force empty categories" in text


def test_durable_capture_uses_lightweight_title_and_tag_guidance():
    repo = Path(__file__).parents[1]
    skill = (repo / "skills" / "agent-note" / "SKILL.md").read_text()
    durable_capture = (
        repo
        / "skills"
        / "agent-note"
        / "references"
        / "durable-capture.md"
    ).read_text()
    import_reference = (
        repo
        / "skills"
        / "agent-note"
        / "references"
        / "conversation-import.md"
    ).read_text()
    skill_text = " ".join(skill.split())
    durable_text = " ".join(durable_capture.split())
    import_text = " ".join(import_reference.split())

    assert "clear, subject-specific title" in skill_text
    assert "Use only a few tags that help retrieval" in skill_text
    assert "Do not fill the tag allowance or force a taxonomy" in skill_text
    assert "frontmatter fields exactly: `title`, `date`, and `tags`" in durable_text
    assert "eight-tag limit; the limit is not a target" in durable_text
    assert "relevant topic tags and optionally one kind tag" in durable_text
    for kind in ("`idea`", "`decision`", "`preference`", "`session-handoff`"):
        assert kind in durable_text
    assert "reuse established tags when they fit" in durable_text
    assert "Do not force a project tag, kind tag, or arbitrary taxonomy" in durable_text
    assert "Never add tags merely for completeness" in durable_text
    assert "duplicate, near-synonym, or noisy tags" in durable_text
    assert "tags as a retrieval aid, not a complex classification system" in (
        durable_text
    )
    assert "`session-handoff` only when that kind tag helps retrieval" in import_text


def test_repository_keeps_skill_primary_and_mcp_remote_only():
    repo = Path(__file__).parents[1]
    project = tomllib.loads((repo / "pyproject.toml").read_text())

    assert not (repo / ".mcp.json").exists()
    assert not (repo / ".codex" / "config.toml").exists()
    assert (repo / "src" / "agent_note").is_dir()
    assert not (repo / "src" / "notes_mcp").exists()
    assert not (repo / "src" / "agent_note" / "server.py").exists()
    assert (repo / "src" / "agent_note" / "remote_server.py").exists()
    assert "agent-note-mcp" in project["project"]["scripts"]
    assert not any(
        dependency.lower().startswith("mcp")
        for dependency in project["project"]["dependencies"]
    )
    assert any(
        dependency.lower().startswith("mcp==")
        for dependency in project["project"]["optional-dependencies"]["remote"]
    )
