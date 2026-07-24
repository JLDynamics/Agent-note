"""Raw source storage for imported conversations.

The MCP tool saves source text here, then hands reasoning back to the connected
agent. Durable memory is saved through the existing create_note tool.
"""

import hashlib
import json
from datetime import datetime
from uuid import uuid4

from notes_mcp import notes_store


def _conversation_id(now):
    return f"conv-{now.strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:8]}"


def save_raw_conversation(content, title=None, original_date=None, now=None):
    """Save the transcript exactly as received plus separate JSON metadata.

    The transcript is a .txt file so the normal note index never mistakes it
    for a derived note. Exclusive creation ensures this tool never overwrites
    an existing raw record; normal filesystem access can still change it.
    """
    if not isinstance(content, str) or not content.strip():
        raise ValueError("conversation content cannot be empty")

    now = now or datetime.now()
    conversation_id = _conversation_id(now)
    root = notes_store.get_notes_folder() / ".raw" / "conversations"
    folder = root / conversation_id
    folder.mkdir(parents=True, exist_ok=False)

    transcript_path = folder / "conversation.txt"
    metadata_path = folder / "metadata.json"
    transcript_path.write_bytes(content.encode("utf-8"))

    metadata = {
        "conversation_id": conversation_id,
        "imported_at": now.isoformat(timespec="seconds"),
        "original_date": original_date,
        "title": title,
        "character_count": len(content),
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {
        "conversation_id": conversation_id,
        "transcript_path": str(transcript_path),
        "metadata_path": str(metadata_path),
        "metadata": metadata,
    }
