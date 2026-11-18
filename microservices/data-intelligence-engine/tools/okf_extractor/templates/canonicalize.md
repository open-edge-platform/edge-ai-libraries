You are consolidating an OKF concept graph. Below are concepts of type "{TYPE}", each
with an integer row id, its title, and a few fields:

- `title`   — the surface name as extracted.
- `roles`   — one or more short descriptions of what this concept did / was across documents.
- `sources` — how many documents mention it.

Your job: find the rows that refer to the **SAME real-world {TYPE}** and should be merged
into one canonical concept (aliases, abbreviations, nicknames, typos, minor variants).

# Merge stance (when to merge vs. keep separate)

{MERGE_STANCE}

# Output

Output JSON only — no explanation, no markdown fences. List only the groups that contain
**two or more** rows to merge; omit singletons entirely.

{
  "groups": [
    {"members": [<row id>, <row id>, ...], "reason": "<why these are the same real thing>"}
  ]
}

Concepts:
{ENTITIES}
