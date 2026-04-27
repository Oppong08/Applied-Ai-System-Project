import json
import anthropic

# --- Tone-specific system prompts (Fine-Tuning / Specialization) ---

_TONE_PROMPTS: dict[str, str] = {
    "curator": (
        "You are VibeFinder's playlist curator. You explain music recommendations in a warm, "
        "enthusiastic, and honest way. You always base your explanations on the specific song "
        "attributes you are given — never invent details about songs that aren't in the list. "
        "Keep your response under 300 words."
    ),
    "critic": (
        "You are a professional music critic writing a brief analytical playlist review. "
        "Reference specific song attributes precisely — mention energy levels, BPM where "
        "relevant, and genre characteristics. Use technical vocabulary (timbre, dynamics, "
        "valence, danceability) when it adds clarity. Be objective and insightful, not "
        "promotional. Never invent details about songs not in the list provided. "
        "Keep your response under 300 words."
    ),
    "hype": (
        "You are an enthusiastic DJ hyping up a friend's perfect playlist. Be energetic and "
        "informal — use phrases like 'this one GOES HARD', 'absolute banger', 'you need this "
        "in your life right now'. Make the listener feel excited. Never invent songs not in "
        "the list provided. Keep your response under 300 words."
    ),
}

VALID_TONES = set(_TONE_PROMPTS.keys())


def _build_narrative_prompt(
    user_text: str,
    user_prefs: dict,
    top_songs: list[tuple],
    genre_context: str | None = None,
) -> str:
    formatted = [
        {
            "title": s[0].get("title", "Unknown"),
            "artist": s[0].get("artist", "Unknown"),
            "genre": s[0].get("genre", ""),
            "mood": s[0].get("mood", ""),
            "energy": s[0].get("energy", ""),
            "score": round(s[1], 2),
        }
        for s in top_songs
    ]

    # RAG Enhancement: inject the retrieved genre guide as additional context
    genre_section = ""
    if genre_context:
        genre_section = (
            f"\nGenre context (use this to enrich your explanation):\n{genre_context}\n"
        )

    return (
        f'The user asked: "{user_text}"\n\n'
        f"Their preferences were parsed as:\n"
        f"  Genre: {user_prefs.get('favorite_genre')}\n"
        f"  Mood: {user_prefs.get('favorite_mood')}\n"
        f"  Energy level: {user_prefs.get('target_energy')}\n"
        f"{genre_section}\n"
        f"The scoring engine retrieved these top songs (ranked by match score):\n\n"
        f"{json.dumps(formatted, indent=2)}\n\n"
        "Write a short playlist introduction (2 sentences), then for each song write one "
        "sentence explaining why it fits this listener. Be specific about genre, mood, or "
        "energy when relevant."
    )


def generate_playlist_narrative(
    user_text: str,
    user_prefs: dict,
    top_songs: list[tuple],
    client: anthropic.Anthropic,
    tone: str = "curator",
    genre_context: str | None = None,
) -> str:
    """Generate a playlist narrative grounded in top_songs.

    tone: one of 'curator' (default), 'critic', or 'hype'.
    genre_context: optional genre guide text retrieved from data/genre_guides.json.
    Raises anthropic.APIError on API failure (re-raised to caller).
    """
    system_prompt = _TONE_PROMPTS.get(tone, _TONE_PROMPTS["curator"])
    user_prompt = _build_narrative_prompt(user_text, user_prefs, top_songs, genre_context)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text.strip()
