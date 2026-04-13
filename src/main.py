"""
Command line runner for the Music Recommender Simulation.

This file helps you quickly run and test your recommender.

You will implement the functions in recommender.py:
- load_songs
- score_song
- recommend_songs
"""

try:
    from recommender import load_songs, recommend_songs
except ModuleNotFoundError:
    from src.recommender import load_songs, recommend_songs


def main() -> None:
    songs = load_songs("data/songs.csv") 

    # Step 2: user taste profile for scoring comparisons
    user_prefs = {
        "favorite_genre": "rock",
        "favorite_mood": "intense",
        "target_energy": 0.88,
        "target_tempo_bpm": 145,
        "target_valence": 0.45,
        "target_danceability": 0.62,
        "target_acousticness": 0.12,
        # Backward-compatible keys for simple starter scoring logic
        "genre": "rock",
        "mood": "intense",
        "energy": 0.88,
    }

    recommendations = recommend_songs(user_prefs, songs, k=5)

    print("\n" + "=" * 70)
    print("TOP RECOMMENDATIONS")
    print("=" * 70)

    for index, rec in enumerate(recommendations, start=1):
        song, score, explanation = rec
        reasons = [reason.strip() for reason in explanation.split(";") if reason.strip()]

        print(f"\n{index}. {song['title']}")
        print(f"   Final Score: {score:.2f}")
        print("   Reasons:")
        for reason in reasons:
            print(f"   - {reason}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
