"""Tests for the VibeFinder 2.0 AI pipeline.

All Claude API calls are mocked — no real API key required.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.logger import validate_raw_input, log_query
from src.ai_parser import parse_user_input, _validate_parsed_profile
from src.ai_narrator import generate_playlist_narrative


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_client(response_text: str) -> MagicMock:
    """Return a mock Anthropic client whose messages.create returns response_text."""
    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=response_text)]
    mock_client.messages.create.return_value = mock_msg
    return mock_client


_VALID_PROFILE_JSON = json.dumps({
    "favorite_genre": "lofi",
    "favorite_mood": "chill",
    "target_energy": 0.3,
})

_SAMPLE_SONGS = [
    ({"title": "Midnight Drift", "artist": "SleepWave", "genre": "lofi", "mood": "chill", "energy": 0.28}, 3.94, "genre match; mood match; energy x2"),
    ({"title": "Focus Tape", "artist": "Brainwave", "genre": "lofi", "mood": "focused", "energy": 0.35}, 2.90, "genre match; energy x2"),
]


# ---------------------------------------------------------------------------
# Test 1: Parser happy path
# ---------------------------------------------------------------------------

def test_parse_user_input_returns_valid_profile():
    client = make_mock_client(_VALID_PROFILE_JSON)
    result = parse_user_input("I want something chill for studying", client)
    assert result["favorite_genre"] == "lofi"
    assert result["favorite_mood"] == "chill"
    assert 0.0 <= result["target_energy"] <= 1.0


# ---------------------------------------------------------------------------
# Test 2: Parser raises on non-JSON response
# ---------------------------------------------------------------------------

def test_parse_user_input_raises_on_bad_json():
    client = make_mock_client("Sorry, I cannot help with that.")
    with pytest.raises(ValueError, match="unparseable JSON"):
        parse_user_input("give me music", client)


# ---------------------------------------------------------------------------
# Test 3: Narrator returns a non-empty string
# ---------------------------------------------------------------------------

def test_generate_playlist_narrative_returns_string():
    client = make_mock_client("Here are your top late-night picks! Each track is perfectly suited to your vibe.")
    user_prefs = {"favorite_genre": "lofi", "favorite_mood": "chill", "target_energy": 0.3}
    result = generate_playlist_narrative("chill study music", user_prefs, _SAMPLE_SONGS, client)
    assert isinstance(result, str)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# Test 4: validate_raw_input rejects too-short input
# ---------------------------------------------------------------------------

def test_validate_raw_input_rejects_too_short():
    with pytest.raises(ValueError, match="too short"):
        validate_raw_input("hi")


# ---------------------------------------------------------------------------
# Test 5: validate_raw_input rejects too-long input
# ---------------------------------------------------------------------------

def test_validate_raw_input_rejects_too_long():
    with pytest.raises(ValueError, match="too long"):
        validate_raw_input("x" * 501)


# ---------------------------------------------------------------------------
# Test 6: run_pipeline logs an error record when parse fails
# ---------------------------------------------------------------------------

def test_run_pipeline_logs_error_on_parse_failure(tmp_path):
    from src import app as app_module

    bad_client = make_mock_client("not json at all")

    # Redirect the log file to a temp directory
    original_log = app_module.log_query.__module__
    with patch("src.logger.QUERIES_LOG", tmp_path / "queries.jsonl"), \
         patch("src.logger.LOGS_DIR", tmp_path):
        result = app_module.run_pipeline(
            "I want chill music for studying tonight",
            [],   # empty songs — parse fails before retrieval anyway
            bad_client,
        )

    assert result["error"] is not None
    assert "ValueError" in result["error"]
    # Pipeline must not raise
    assert result["narrative"] is None

    log_file = tmp_path / "queries.jsonl"
    assert log_file.exists()
    record = json.loads(log_file.read_text())
    assert record["error"] is not None


# ---------------------------------------------------------------------------
# Test 7: Full pipeline returns complete result dict (all mocked)
# ---------------------------------------------------------------------------

def test_run_pipeline_returns_complete_result(tmp_path):
    from src import app as app_module
    from src.recommender import load_songs
    from pathlib import Path

    # Real songs CSV for retrieval stage
    songs_csv = Path(__file__).parent.parent / "data" / "songs.csv"
    songs = load_songs(str(songs_csv))

    # Call 1 → parser, Call 2 → agent evaluator, Call 3 → narrator
    mock_client = MagicMock()
    parse_msg = MagicMock()
    parse_msg.content = [MagicMock(text=_VALID_PROFILE_JSON)]
    eval_msg = MagicMock()
    eval_msg.content = [MagicMock(text='{"score": 4, "reasoning": "Good genre and mood match", "adjustment": null}')]
    narrate_msg = MagicMock()
    narrate_msg.content = [MagicMock(text="Great playlist incoming!")]
    mock_client.messages.create.side_effect = [parse_msg, eval_msg, narrate_msg]

    with patch("src.logger.QUERIES_LOG", tmp_path / "queries.jsonl"), \
         patch("src.logger.LOGS_DIR", tmp_path):
        result = app_module.run_pipeline(
            "I want something chill for late-night studying",
            songs,
            mock_client,
        )

    assert result["error"] is None
    assert result["parsed_profile"] is not None
    assert result["top_songs"] is not None
    assert result["narrative"] == "Great playlist incoming!"
    assert isinstance(result["latency_seconds"], float)
    # Agentic step should be recorded
    assert len(result["agent_steps"]) == 1
    assert result["agent_steps"][0]["step"] == "evaluation"
    assert result["agent_steps"][0]["score"] == 4
