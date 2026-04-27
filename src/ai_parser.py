import json
import anthropic

_GENRES = "pop, lofi, rock, ambient, jazz, synthwave, indie pop, hip-hop, r&b, classical, country, edm, metal, afrobeats, folk"
_MOODS = "happy, chill, intense, relaxed, focused, moody, confident, romantic, calm, nostalgic, uplifting, aggressive, joyful, sad, party"

# Fine-Tuning / Specialization: few-shot examples handle tricky cases —
# vague/informal language, non-English input, and contradictory signals.
_SYSTEM_PROMPT = f"""You are a music preference parser. The user will describe what kind of music they want in plain language.
Extract their preferences and return ONLY a valid JSON object with exactly these keys:

  favorite_genre  - one of: {_GENRES}  (pick the closest match)
  favorite_mood   - one of: {_MOODS}  (pick the closest match)
  target_energy   - a float between 0.0 (very calm) and 1.0 (very intense)

Return ONLY the JSON. No explanation, no markdown fences, no extra text.

Examples:

User: something to zone out while coding late at night
Assistant: {{"favorite_genre": "lofi", "favorite_mood": "focused", "target_energy": 0.35}}

User: I need a hype track to crush it at the gym
Assistant: {{"favorite_genre": "pop", "favorite_mood": "intense", "target_energy": 0.90}}

User: música tranquila para el atardecer
Assistant: {{"favorite_genre": "ambient", "favorite_mood": "calm", "target_energy": 0.25}}

User: something sad but I still want to feel the beat
Assistant: {{"favorite_genre": "r&b", "favorite_mood": "sad", "target_energy": 0.55}}"""


def _validate_parsed_profile(data: dict) -> dict:
    """Check required keys exist and clamp target_energy to [0.0, 1.0]."""
    required = {"favorite_genre", "favorite_mood", "target_energy"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"Claude response is missing required keys: {missing}")
    try:
        data["target_energy"] = float(data["target_energy"])
    except (TypeError, ValueError):
        raise ValueError(f"target_energy must be a number, got: {data['target_energy']!r}")
    data["target_energy"] = max(0.0, min(1.0, data["target_energy"]))
    return data


def parse_user_input(raw_text: str, client: anthropic.Anthropic) -> dict:
    """Convert a natural language music request into a user_prefs dict.

    Raises ValueError if the response cannot be parsed or is missing required keys.
    Raises anthropic.APIError on API failure (re-raised to caller).
    """
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=256,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": raw_text}],
    )
    raw_json = response.content[0].text.strip()
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Claude returned unparseable JSON: {raw_json!r}") from exc
    return _validate_parsed_profile(data)
