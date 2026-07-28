"""Deterministic create and import workflows used by the Agent-note CLI."""

from agent_note import conversation_import, embeddings, notes_store


def create_note(
    content: str,
    tags: list[str] | None = None,
    title: str | None = None,
) -> dict:
    """Create and best-effort embed one note, returning the public result."""
    try:
        path, warning = notes_store.create_entry(content, tags=tags, title=title)
    except ValueError as exc:
        return {"error": str(exc)}

    embedded = embeddings.try_embed_note(path)
    info = notes_store.note_info(path)
    return {
        "path": str(path),
        "title": info["title"],
        "tags": info["tags"],
        "embedded": embedded,
        "warning": warning,
    }


def import_conversation(
    content: str,
    original_date: str | None = None,
    title: str | None = None,
) -> dict:
    """Preserve a raw conversation and return the agent handoff contract."""
    raw_record = conversation_import.save_raw_conversation(
        content,
        title=title,
        original_date=original_date,
    )
    conversation_id = raw_record["conversation_id"]
    source_lines = []
    if original_date:
        source_lines.append(f"Original conversation date: {original_date}")
    source_lines.append(f"Source conversation: {conversation_id}")
    source_block = "\n".join(source_lines)

    return {
        "status": "raw_saved",
        "agent_processing_required": True,
        "conversation_id": conversation_id,
        "transcript_path": raw_record["transcript_path"],
        "metadata_path": raw_record["metadata_path"],
        "source_block_for_notes": source_block,
        "next_action": (
            "Process the complete transcript now. First run create once for "
            "a broad session handoff covering its important themes. Then run "
            "search for related notes and run create for each useful, "
            "non-duplicate standalone item with a title, a few useful tags "
            "(up to eight) that help retrieval, and "
            f"this exact final source block:\n{source_block}"
        ),
    }
