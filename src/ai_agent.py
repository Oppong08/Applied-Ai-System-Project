"""Agentic evaluation and refinement step for VibeFinder 2.0.

After the scoring engine retrieves top-k songs, the agent evaluates whether those
songs genuinely satisfy the user's intent. If the fit score is below 3/5, the agent
suggests a parameter adjustment and the pipeline re-retrieves with adjusted preferences.

Observable intermediate steps are recorded in the 'agent_steps' list returned by
run_pipeline() and logged to logs/queries.jsonl.
"""

import json
import anthropic

_EVAL_SYSTEM = """You are a music recommendation quality evaluator. Given a user's natural language request, their parsed preferences, and the top 5 retrieved songs, assess how well the recommendations match the user's actual intent.

Return ONLY a valid JSON object with exactly these keys:

  score       - integer 1 to 5 (1=poor fit, 3=acceptable, 5=excellent match)
  reasoning   - one sentence explaining the score (be specific about what fits or misses)
  adjustment  - null if score >= 3; otherwise suggest ONE of:
                  {"field": "target_energy", "delta": <float -0.3 to 0.3>}
                  {"field": "favorite_mood", "value": "<one of: happy, chill, intense, relaxed, focused, moody, confident, romantic, calm, nostalgic, uplifting, aggressive, joyful, sad, party>"}

Return ONLY the JSON. No explanation, no markdown fences."""


def evaluate_recommendations(
    user_text: str,
    user_prefs: dict,
    top_songs: list,
    client: anthropic.Anthropic,
) -> dict:
    """Score how well top_songs match the user's intent (1–5 scale).

    Returns dict with keys: score (int), reasoning (str), adjustment (dict or None).
    Raises ValueError on unparseable response. Raises anthropic.APIError on API failure.
    """
    context = {
        "user_request": user_text,
        "parsed_preferences": user_prefs,
        "top_songs": [
            {
                "title": s[0].get("title"),
                "genre": s[0].get("genre"),
                "mood": s[0].get("mood"),
                "energy": s[0].get("energy"),
                "score": round(s[1], 2),
            }
            for s in top_songs
        ],
    }
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=256,
        system=_EVAL_SYSTEM,
        messages=[{"role": "user", "content": json.dumps(context)}],
    )
    raw = response.content[0].text.strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Agent evaluator returned unparseable JSON: {raw!r}") from exc

    result["score"] = max(1, min(5, int(result.get("score", 3))))
    result.setdefault("reasoning", "")
    result.setdefault("adjustment", None)
    return result


def apply_adjustment(user_prefs: dict, adjustment: dict) -> dict:
    """Return a new user_prefs dict with the agent's suggested adjustment applied."""
    prefs = dict(user_prefs)
    field = adjustment.get("field")
    if field == "target_energy" and "delta" in adjustment:
        current = float(prefs.get("target_energy", 0.5))
        prefs["target_energy"] = round(max(0.0, min(1.0, current + float(adjustment["delta"]))), 2)
    elif field == "favorite_mood" and "value" in adjustment:
        prefs["favorite_mood"] = adjustment["value"]
    return prefs
