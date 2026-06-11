"""
Seed demo memories into the real AI_Friend table: friend_memories_v2.

Use this only after truncating friend_memories_v2 from Supabase SQL Editor:

    truncate table public.friend_memories_v2 restart identity;

Then run:

    python Agent/seed_friend_memories_v2_demo.py

After seeding, run Backend/sql/friend_memories_v2_demo_reset.sql in Supabase
SQL Editor to capture that clean state as the reset baseline.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from supabase import create_client

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

load_dotenv()

SUPABASE_URL = str(os.getenv("SUPABASE_URL", ""))
SUPABASE_KEY = str(os.getenv("SUPABASE_KEY", ""))
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_KEY in .env")

MEMORY_TABLE = "friend_memories_v2"
EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

DEMO_SEEDS: list[dict] = [
    {
        "type": "chat",
        "description": "User struggled with systems of equations homework after feeling like they understood it in class.",
        "poignancy": 5,
    },
    {
        "type": "chat",
        "description": "User decided to close Discord to focus on homework, but still felt stuck afterward.",
        "poignancy": 4,
    },
    {
        "type": "chat",
        "description": "User's mom got disappointed because gaming kept cutting into homework time.",
        "poignancy": 5,
    },
    {
        "type": "chat",
        "description": "User complained that Jules did not contribute to a group project and wanted to stop trying.",
        "poignancy": 5,
    },
    {
        "type": "chat",
        "description": "User is considering asking Nina directly whether something is wrong between them.",
        "poignancy": 4,
    },
    {
        "type": "chat",
        "description": "User often says they do not care about Nina, but the deflection usually means they do care.",
        "poignancy": 5,
    },
    {
        "type": "chat",
        "description": "User vented about parents fighting at night and said the house felt impossible to relax in.",
        "poignancy": 5,
    },
    {
        "type": "thought",
        "description": "User deflects with jokes when emotionally vulnerable; direct counselor-style sympathy makes them shut down.",
        "poignancy": 5,
    },
    {
        "type": "thought",
        "description": "User responds better to blunt honesty and a concrete next move than to reassurance like it will be okay.",
        "poignancy": 5,
    },
    {
        "type": "thought",
        "description": "When user blames other people while stressed, Jiho should call out the part user can control without lecturing.",
        "poignancy": 5,
    },
    {
        "type": "thought",
        "description": "Small math wins matter for user, but over-praise sounds fake; plain acknowledgment works better.",
        "poignancy": 4,
    },
    {
        "type": "experience",
        "description": "Jiho remembers lying in bed in 1st grade hearing his parents scream downstairs and putting a pillow over his head.",
        "poignancy": 5,
    },
    {
        "type": "experience",
        "description": "The day Jiho's dad moved out, Jiho came home from school and noticed his dad's shoes were gone from the hallway.",
        "poignancy": 5,
    },
    {
        "type": "experience",
        "description": "Jiho's sister once sat beside him quietly during a bad night at home, which helped more than advice.",
        "poignancy": 5,
    },
    {
        "type": "experience",
        "description": "Jiho first got serious about drums after a music teacher let him stay after class to mess around on a drum set.",
        "poignancy": 4,
    },
]


def main() -> None:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print(f"[Seed] loading embedding model: {EMBED_MODEL_NAME}")
    model = SentenceTransformer(EMBED_MODEL_NAME)

    existing = supabase.table(MEMORY_TABLE).select("description").execute()
    existing_descs = {row["description"] for row in (existing.data or [])}

    inserted = 0
    skipped = 0
    for seed in DEMO_SEEDS:
        description = seed["description"]
        if description in existing_descs:
            print(f"[Seed] skip existing: {description[:72]}...")
            skipped += 1
            continue

        embedding = model.encode(description).tolist()
        supabase.table(MEMORY_TABLE).insert({
            "type": seed["type"],
            "description": description,
            "embedding_vector": embedding,
            "poignancy": seed["poignancy"],
            "filling": None,
            "emotion": None,
        }).execute()
        print(f"[Seed] inserted {seed['type']} p={seed['poignancy']}: {description[:72]}...")
        inserted += 1

    print(f"[Seed] done: inserted={inserted}, skipped={skipped}, table={MEMORY_TABLE}")


if __name__ == "__main__":
    main()
