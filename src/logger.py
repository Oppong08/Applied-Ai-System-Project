import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

LOGS_DIR = Path(__file__).parent.parent / "logs"
QUERIES_LOG = LOGS_DIR / "queries.jsonl"


def validate_raw_input(raw_text: str) -> str:
    """Guardrail: strip whitespace and enforce length bounds."""
    cleaned = raw_text.strip()
    if len(cleaned) < 10:
        raise ValueError("Input is too short — please describe what music you want in more detail (at least 10 characters).")
    if len(cleaned) > 500:
        raise ValueError("Input is too long — please keep your request under 500 characters.")
    return cleaned


def log_query(
    raw_input: str,
    parsed_profile: dict | None,
    top_songs: list | None,
    narrative: str | None,
    latency_seconds: float,
    error: str | None = None,
    agent_steps: list | None = None,
) -> None:
    """Append one JSON record to logs/queries.jsonl."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    record = {
        "query_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "raw_input": raw_input,
        "parsed_profile": parsed_profile,
        "top_songs": top_songs,
        "narrative": narrative,
        "latency_seconds": round(latency_seconds, 3),
        "error": error,
        "agent_steps": agent_steps,
    }

    with QUERIES_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
