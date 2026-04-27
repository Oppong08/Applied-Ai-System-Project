"""VibeFinder 2.0 — primary entrypoint for the RAG pipeline.

Run with:
    python -m src.app                        # curator tone (default)
    python -m src.app --tone critic          # analytical music-critic tone
    python -m src.app --tone hype            # energetic DJ tone
    python -m src.app --no-agent             # skip agentic evaluation step
"""

import argparse
import os
import sys
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from src.recommender import load_songs, recommend_songs
from src.ai_parser import parse_user_input
from src.ai_narrator import generate_playlist_narrative, VALID_TONES
from src.ai_agent import evaluate_recommendations, apply_adjustment
from src.retriever import retrieve_genre_guide
from src.logger import validate_raw_input, log_query

_SONGS_CSV = Path(__file__).parent.parent / "data" / "songs.csv"


def run_pipeline(
    raw_text: str,
    songs: list[dict],
    client: anthropic.Anthropic,
    top_k: int = 5,
    tone: str = "curator",
    enable_agent: bool = True,
) -> dict:
    """Run the full RAG pipeline (with optional agentic evaluation) for one query.

    Always returns a dict — never raises. Errors are caught, logged, and returned.

    Returns keys: parsed_profile, top_songs, narrative, latency_seconds, error,
                  agent_steps (list of intermediate agentic step dicts).
    """
    start = time.monotonic()
    parsed_profile = None
    top_songs = None
    narrative = None
    error_msg = None
    agent_steps: list[dict] = []

    try:
        # Stage 1 — guardrail + NL → structured preferences
        cleaned = validate_raw_input(raw_text)
        parsed_profile = parse_user_input(cleaned, client)

        # Stage 2 — retrieve top-k songs using the existing scoring engine
        top_songs = recommend_songs(parsed_profile, songs, k=top_k)

        # Stage 2b — Agentic Workflow: evaluate fit, optionally refine
        if enable_agent:
            eval_result = evaluate_recommendations(cleaned, parsed_profile, top_songs, client)
            agent_steps.append({"step": "evaluation", **eval_result})

            if eval_result["score"] < 3 and eval_result.get("adjustment"):
                refined_prefs = apply_adjustment(parsed_profile, eval_result["adjustment"])
                refined_songs = recommend_songs(refined_prefs, songs, k=top_k)
                agent_steps.append({
                    "step": "refinement",
                    "adjustment_applied": eval_result["adjustment"],
                    "new_top_songs": [
                        {"title": s[0].get("title"), "score": round(s[1], 2)}
                        for s in refined_songs
                    ],
                })
                top_songs = refined_songs
                parsed_profile = refined_prefs

        # Stage 2c — RAG Enhancement: retrieve genre guide as second context source
        genre_context = retrieve_genre_guide(parsed_profile.get("favorite_genre", ""))

        # Stage 3 — generate narrative grounded in retrieved songs + genre context
        narrative = generate_playlist_narrative(
            cleaned, parsed_profile, top_songs, client,
            tone=tone,
            genre_context=genre_context,
        )

    except ValueError as exc:
        error_msg = f"ValueError: {exc}"
        print(f"\n[VibeFinder] {exc}\n")
    except anthropic.APIConnectionError as exc:
        error_msg = f"APIConnectionError: {exc}"
        print("\n[VibeFinder] Could not reach the Anthropic API. Check your network connection.\n")
    except anthropic.RateLimitError as exc:
        error_msg = f"RateLimitError: {exc}"
        print("\n[VibeFinder] Rate limit reached. Please wait a moment and try again.\n")
    except anthropic.APIStatusError as exc:
        error_msg = f"APIStatusError {exc.status_code}: {exc.message}"
        print(f"\n[VibeFinder] API error (status {exc.status_code}). Check your API key.\n")

    latency = time.monotonic() - start

    # Stage 4 — log every run (success or failure)
    top_songs_log = (
        [{"title": s[0].get("title"), "score": round(s[1], 2)} for s in top_songs]
        if top_songs else None
    )
    log_query(
        raw_text, parsed_profile, top_songs_log, narrative, latency,
        error_msg, agent_steps or None,
    )

    return {
        "parsed_profile": parsed_profile,
        "top_songs": top_songs,
        "narrative": narrative,
        "latency_seconds": round(latency, 3),
        "error": error_msg,
        "agent_steps": agent_steps,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="VibeFinder 2.0 — AI music recommender")
    parser.add_argument(
        "--tone",
        choices=sorted(VALID_TONES),
        default="curator",
        help="Narrator tone: curator (default), critic, or hype",
    )
    parser.add_argument(
        "--no-agent",
        action="store_true",
        help="Skip the agentic evaluation/refinement step",
    )
    args = parser.parse_args()

    load_dotenv()
    try:
        api_key = os.environ["ANTHROPIC_API_KEY"]
    except KeyError:
        print(
            "\n[VibeFinder] ANTHROPIC_API_KEY not set.\n"
            "Setup:\n"
            "  1. Copy .env.example to .env\n"
            "  2. Paste your Anthropic API key into .env\n"
            "  3. Run again\n"
        )
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    songs = load_songs(str(_SONGS_CSV))

    if not sys.stdin.isatty():
        raw_text = sys.stdin.read().strip()
    else:
        tone_label = f"[tone: {args.tone}]"
        print(f"VibeFinder 2.0 — Tell me what music you're in the mood for.  {tone_label}")
        print("(type your request and press Enter)\n")
        raw_text = input("> ").strip()

    result = run_pipeline(
        raw_text, songs, client,
        tone=args.tone,
        enable_agent=not args.no_agent,
    )

    # Show observable agentic steps
    for step in result["agent_steps"]:
        if step["step"] == "evaluation":
            print(f"\n[Agent] Fit score: {step['score']}/5 — {step['reasoning']}")
            if step.get("adjustment"):
                print(f"[Agent] Adjusting: {step['adjustment']}")
        elif step["step"] == "refinement":
            print(f"[Agent] Re-retrieved with adjusted preferences.")

    if result["narrative"]:
        print("\n" + "=" * 60)
        print(result["narrative"])
        print("=" * 60)
        print(f"\n[logged | latency: {result['latency_seconds']}s | tone: {args.tone}]")


if __name__ == "__main__":
    main()
