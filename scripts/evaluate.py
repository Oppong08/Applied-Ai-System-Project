"""VibeFinder 2.0 — Evaluation Harness

Runs 10 predefined test cases through the pipeline and reports:
  - Parse accuracy  : genre match, mood match, energy in expected range
  - Groundedness    : narrator only cites songs from the retrieved top-5
  - Latency         : end-to-end seconds per query
  - Overall pass/fail per test case

Usage:
    python -m scripts.evaluate           # mock mode  — no API key needed
    python -m scripts.evaluate --real    # real API calls (requires .env + key)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.recommender import load_songs, recommend_songs
from src.ai_parser import parse_user_input
from src.ai_narrator import generate_playlist_narrative
from src.retriever import retrieve_genre_guide

_SONGS_CSV = Path(__file__).parent.parent / "data" / "songs.csv"

# ---------------------------------------------------------------------------
# Predefined test suite
# ---------------------------------------------------------------------------

TEST_CASES = [
    {
        "id": 1,
        "input": "I want something upbeat and energetic for working out at the gym",
        "expected_genre": "pop",
        "expected_mood": "intense",
        "energy_min": 0.70,
        "energy_max": 1.00,
    },
    {
        "id": 2,
        "input": "chill music for late night studying, nothing too distracting",
        "expected_genre": "lofi",
        "expected_mood": "chill",
        "energy_min": 0.00,
        "energy_max": 0.55,
    },
    {
        "id": 3,
        "input": "I am feeling melancholy and want something acoustic and quiet",
        "expected_genre": "folk",
        "expected_mood": "sad",
        "energy_min": 0.00,
        "energy_max": 0.45,
    },
    {
        "id": 4,
        "input": "happy danceable songs for a weekend party with friends",
        "expected_genre": "pop",
        "expected_mood": "happy",
        "energy_min": 0.60,
        "energy_max": 1.00,
    },
    {
        "id": 5,
        "input": "something aggressive and heavy, I want pure metal",
        "expected_genre": "metal",
        "expected_mood": "aggressive",
        "energy_min": 0.80,
        "energy_max": 1.00,
    },
    {
        "id": 6,
        "input": "relaxing jazz for a Sunday morning with coffee",
        "expected_genre": "jazz",
        "expected_mood": "relaxed",
        "energy_min": 0.00,
        "energy_max": 0.55,
    },
    {
        "id": 7,
        "input": "country music with a nostalgic down-home feeling",
        "expected_genre": "country",
        "expected_mood": "nostalgic",
        "energy_min": 0.20,
        "energy_max": 0.75,
    },
    {
        "id": 8,
        "input": "high energy EDM for a rave and dance floor",
        "expected_genre": "edm",
        "expected_mood": "uplifting",
        "energy_min": 0.70,
        "energy_max": 1.00,
    },
    {
        "id": 9,
        "input": "peaceful classical music for reading and deep concentration",
        "expected_genre": "classical",
        "expected_mood": "calm",
        "energy_min": 0.00,
        "energy_max": 0.40,
    },
    {
        "id": 10,
        "input": "confident hip-hop with swagger and attitude",
        "expected_genre": "hip-hop",
        "expected_mood": "confident",
        "energy_min": 0.50,
        "energy_max": 0.90,
    },
]

# ---------------------------------------------------------------------------
# Mock client factory (mock mode)
# ---------------------------------------------------------------------------

def _make_mock_client(profile_json: str, narrative_text: str) -> MagicMock:
    """Return a mock Anthropic client that returns preset responses."""
    mock_client = MagicMock()

    responses = iter([profile_json, narrative_text])

    def _create(*args, **kwargs):
        msg = MagicMock()
        msg.content = [MagicMock(text=next(responses))]
        return msg

    mock_client.messages.create.side_effect = _create
    return mock_client

# ---------------------------------------------------------------------------
# Groundedness check
# ---------------------------------------------------------------------------

def _check_groundedness(
    narrative: str,
    top_songs: list,
    all_titles: list[str],
) -> tuple[bool, list[str]]:
    """Return (is_grounded, list_of_hallucinated_titles).

    A title is considered hallucinated if it appears verbatim in the narrative
    but was NOT in the retrieved top-k songs.
    """
    retrieved_titles = {s[0].get("title", "").lower() for s in top_songs}
    hallucinated = [
        t for t in all_titles
        if t.lower() in narrative.lower() and t.lower() not in retrieved_titles
    ]
    return len(hallucinated) == 0, hallucinated

# ---------------------------------------------------------------------------
# Main evaluation loop
# ---------------------------------------------------------------------------

def run_evaluation(use_real_api: bool = False) -> None:
    songs = load_songs(str(_SONGS_CSV))
    all_titles = [s["title"] for s in songs]

    client = None
    if use_real_api:
        import anthropic
        from dotenv import load_dotenv
        load_dotenv()
        try:
            client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        except KeyError:
            print("Error: ANTHROPIC_API_KEY not set. Use mock mode or add .env file.")
            sys.exit(1)

    mode_label = "REAL API" if use_real_api else "MOCK MODE"
    print(f"\nVibeFinder 2.0 — Evaluation Harness  [{mode_label}]")
    print("=" * 74)
    print(f"{'#':>2}  {'Input (truncated)':<38}  Genre  Mood   Nrg  Gnd  Result")
    print("-" * 74)

    results = []

    for tc in TEST_CASES:
        t0 = time.monotonic()
        genre_ok = mood_ok = energy_ok = ground_ok = False
        error = None

        try:
            if use_real_api:
                profile = parse_user_input(tc["input"], client)
            else:
                # Mock: parser returns the expected profile so the pipeline runs end-to-end
                mid_energy = round((tc["energy_min"] + tc["energy_max"]) / 2, 2)
                profile_json = json.dumps({
                    "favorite_genre": tc["expected_genre"],
                    "favorite_mood": tc["expected_mood"],
                    "target_energy": mid_energy,
                })
                top_songs_preview = recommend_songs(
                    {"favorite_genre": tc["expected_genre"],
                     "favorite_mood": tc["expected_mood"],
                     "target_energy": mid_energy},
                    songs, k=5,
                )
                # Narrator mock references only the real top-1 song title (grounded)
                top_title = top_songs_preview[0][0].get("title", "") if top_songs_preview else ""
                narrative_mock = f"Your playlist is ready! {top_title} is a top pick for this vibe."
                mock_client = _make_mock_client(profile_json, narrative_mock)
                profile = parse_user_input(tc["input"], mock_client)

            genre_ok = profile.get("favorite_genre") == tc["expected_genre"]
            mood_ok  = profile.get("favorite_mood")  == tc["expected_mood"]
            energy   = float(profile.get("target_energy", -1))
            energy_ok = tc["energy_min"] <= energy <= tc["energy_max"]

            top_songs = recommend_songs(profile, songs, k=5)
            genre_context = retrieve_genre_guide(profile.get("favorite_genre", ""))

            if use_real_api:
                narrative = generate_playlist_narrative(
                    tc["input"], profile, top_songs, client,
                    genre_context=genre_context,
                )
            else:
                # Reuse the pre-built mock narrative (already constructed above)
                narrative = narrative_mock  # type: ignore[possibly-undefined]

            ground_ok, hallucinated = _check_groundedness(narrative, top_songs, all_titles)

        except Exception as exc:
            error = str(exc)
            ground_ok = False
            hallucinated = []

        latency = time.monotonic() - t0
        passed = genre_ok and mood_ok and energy_ok and ground_ok and error is None

        short_input = (tc["input"][:36] + "..") if len(tc["input"]) > 38 else tc["input"]
        g = "✓" if genre_ok else "✗"
        m = "✓" if mood_ok else "✗"
        e = "✓" if energy_ok else "✗"
        nd = "✓" if ground_ok else "✗"
        status = "PASS" if passed else "FAIL"

        print(
            f"{tc['id']:>2}  {short_input:<38}  "
            f"{g}{tc['expected_genre'][:4]:<5} {m}{tc['expected_mood'][:4]:<5} "
            f"{e:<4} {nd:<4} {status}"
        )

        results.append({
            "id": tc["id"],
            "passed": passed,
            "genre_ok": genre_ok,
            "mood_ok": mood_ok,
            "energy_ok": energy_ok,
            "ground_ok": ground_ok,
            "latency": latency,
            "error": error,
        })

    # Summary
    n = len(results)
    n_pass = sum(1 for r in results if r["passed"])
    g_pct  = sum(1 for r in results if r["genre_ok"])  / n * 100
    m_pct  = sum(1 for r in results if r["mood_ok"])   / n * 100
    e_pct  = sum(1 for r in results if r["energy_ok"]) / n * 100
    gd_pct = sum(1 for r in results if r["ground_ok"]) / n * 100
    avg_lat = sum(r["latency"] for r in results) / n

    print("=" * 74)
    print(f"Overall       {n_pass}/{n} passed  ({n_pass/n*100:.0f}%)")
    print(f"Parse         genre {g_pct:.0f}%   mood {m_pct:.0f}%   energy {e_pct:.0f}%"
          + ("  [mock: expected values used]" if not use_real_api else ""))
    print(f"Groundedness  {gd_pct:.0f}%")
    print(f"Avg latency   {avg_lat:.3f}s")
    print()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="VibeFinder 2.0 evaluation harness")
    ap.add_argument("--real", action="store_true", help="Use real Anthropic API calls")
    args = ap.parse_args()
    run_evaluation(use_real_api=args.real)
