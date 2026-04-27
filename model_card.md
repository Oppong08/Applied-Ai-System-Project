# Model Card — VibeFinder 2.0

---

## 1. Model Name and Version

**VibeFinder 2.0** — extends VibeFinder 1.1 (rule-based scoring only) with a Retrieval-Augmented Generation (RAG) pipeline powered by the Anthropic Claude API.

---

## 2. Goal and Task

Accept a natural language music request and return a ranked playlist with a grounded explanation. The system translates free-text intent (e.g., "I want something chill for studying") into a structured preference profile, retrieves the best-matching songs using a rule-based scoring engine, and asks a language model to explain why those songs fit — grounded exclusively in the retrieved results.

---

## 3. Components and Models Used

| Stage | Component | Model / Tool |
|---|---|---|
| Input validation | `logger.validate_raw_input` | Python stdlib (no AI) |
| Preference parsing | `ai_parser.parse_user_input` | Claude Haiku (`claude-haiku-4-5`) |
| Song retrieval | `recommender.recommend_songs` | Rule-based scoring (no AI) |
| Narrative generation | `ai_narrator.generate_playlist_narrative` | Claude Sonnet (`claude-sonnet-4-6`) |
| Logging | `logger.log_query` | Python stdlib (no AI) |

---

## 4. Data

- **Song catalog:** 18 songs in `data/songs.csv` with genre, mood, energy (0–1), tempo, valence, danceability, and acousticness fields.
- **Coverage:** 15 genres, most appearing once. Mood vocabulary has 15 fixed values.
- **No user data is persisted.** The log stores the raw query string and system outputs only — no personal identifying information.

---

## 5. Algorithm Summary

**Scoring formula (unchanged from v1.1):**

```
score = genre_match(+1.0) + mood_match(+1.0) + 2.0 × (1 - |song_energy - target_energy|)
```

The top-5 ranked songs are injected as a JSON block into the narrator prompt. Claude Sonnet is explicitly instructed not to reference any songs outside that list.

**Why RAG:** Asking Claude to generate recommendations directly would produce hallucinated song titles and artists. Running retrieval first and constraining generation to the retrieved context eliminates that failure mode.

---

## 6. Observed Behavior and Biases

**Filter-bubble tendency.** The energy weight (×2) dominates when no genre or mood match exists. Users with preferences in under-represented genres (classical, jazz, afrobeats) often receive results ordered primarily by energy proximity, not musical similarity.

**Vocabulary flattening.** The parser prompt constrains Claude to the exact genre and mood strings in `songs.csv`. Nuanced requests are silently collapsed: "indie folk" → `folk`, "drill rap" → `hip-hop`, "heartbroken but want to feel something" → `sad`. The user is not told this mapping occurred.

**Artist repetition.** No deduplication by artist. LoRoom appears in both "Midnight Coding" and "Focus Flow"; both can appear in the same top-5 for lofi profiles.

**Hostile-input defaults.** "I hate all music" produces `lofi / chill / 0.50` rather than an error or a clarifying question. Claude defaults to neutral values when intent is unclear.

**Cross-language generalization.** Claude Haiku parsed Spanish-language requests correctly in testing without any multilingual instructions. This behavior is emergent and not guaranteed.

---

## 7. Evaluation

**Automated tests (9 total):**
- 2 tests from VibeFinder 1.1: scoring sort order, explanation strings
- 7 new tests: parser happy path, parser bad-JSON error, narrator output, guardrail bounds, pipeline error logging, full pipeline integration
- All 7 new tests mock the Claude API. Run time: ~0.76 seconds. No API key required.

**Manual reliability experiment (10 prompts):**

| Metric | Result |
|---|---|
| Parse accuracy | 9/10 (1 ambiguous "music for rain" — `calm` vs `chill` mood) |
| Narrative groundedness | 10/10 (narrator never cited a song outside the retrieved top-5) |
| End-to-end latency | 2.1–4.8 seconds per query |
| Input guardrail rejection rate | 1/10 prompts rejected (too short: "just something" = 12 chars, actually passes; "hi" = 2 chars fails) |

---

## 8. Limitations and Risks

| Limitation | Impact | Mitigation in v2.0 |
|---|---|---|
| 18-song catalog | Poor variety for edge-case profiles | Acknowledged; system is a demo |
| Energy weight (×2) dominance | Results driven by energy when genre/mood absent | Documented; users can inspect scores |
| Vocabulary lock-in | Nuanced preferences silently flattened | Parser prompt lists valid values; output is inspectable |
| No discovery | Only confirms stated preferences | Acknowledged; out of scope for this version |
| No artist diversity rule | Same artist can appear multiple times | Acknowledged; future work |
| Silent defaults on ambiguous input | User preference invented rather than clarified | Logged; future version should prompt for clarification |

---

## 9. Intended and Non-Intended Use

**Intended:** Educational demonstration of RAG architecture, prompt engineering, and AI system design. Portfolio project for applied AI coursework.

**Not intended for:** Production deployment, real-world music discovery, any decision-making affecting people's access to content or services. The catalog is too small, the scoring is too simple, and the system has no feedback mechanism to improve over time.

---

## 10. Ideas for Improvement

- **Expand the catalog** to at least 200 songs with balanced genre and mood distribution.
- **Add a clarification step** when the parser confidence is low (e.g., ask "Did you mean chill or focused?").
- **Artist diversity rule** — cap at one song per artist in any top-k result.
- **Score more features** — tempo, valence, danceability, and acousticness are present in the data but ignored by the scoring formula.
- **Stream the narrative** using the Anthropic streaming API so output appears progressively rather than after a full round-trip.
- **Add a feedback loop** — let users rate recommendations; use ratings to adjust weights over time.

---

## 11. Personal Reflection

The most important lesson from VibeFinder 2.0 was about the relationship between retrieval and generation. My first instinct was to ask Claude to generate recommendations directly. Claude's response to that framing — pointing out that it would hallucinate song names and suggesting RAG instead — was the pivotal design decision. It illustrates a general principle: language models are good at reasoning about information you give them, and unreliable at recalling specific facts from training data. Any system that requires factual precision should retrieve first.

The second lesson was about prompt constraints. A system prompt that says "only discuss songs from this list" is far more enforceable than one that says "try to be accurate." Explicit constraints on output scope produce more predictable behavior than general accuracy instructions.

The third lesson was about the gap between "works" and "works well." The pipeline runs without errors in all tested cases, but it silently invents user preferences when input is ambiguous rather than surfacing the ambiguity. A system that never crashes is not the same as a system that is honest about what it does not know.
