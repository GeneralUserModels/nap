#!/usr/bin/env python3
"""Score demo2 examples using powernap's LLM judge reward scorer.

Usage:
    GEMINI_API_KEY=... python scripts/score_demo2.py

Requires powernap on sys.path (e.g. pip install -e ../powernap).
Scores a subset of examples to save API calls; use the printed
rewards to manually update all 8 entries in examples.json.
"""

import asyncio
import json
import os
import sys

# Allow running from the repo root
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
EXAMPLES_PATH = os.path.join(REPO_ROOT, "public", "data", "demo2", "examples.json")

# Add powernap to path if needed
POWERNAP_SRC = os.path.join(os.path.dirname(REPO_ROOT), "powernap", "src")
if os.path.isdir(POWERNAP_SRC):
    sys.path.insert(0, POWERNAP_SRC)

from powernap.longnap.scorer import create_reward_scorer


def format_actions(actions: list[str]) -> str:
    """Wrap a list of action strings in <actions><action>...</action>...</actions> XML."""
    lines = "\n".join(f"    <action>{a}</action>" for a in actions)
    return f"<actions>\n{lines}\n</actions>"


async def main():
    with open(EXAMPLES_PATH) as f:
        examples = json.load(f)

    scorer = create_reward_scorer(
        reward_llm="gemini/gemini-3-flash-preview",
        accuracy_weight=0.5,
        formatting_weight=0.5,
        retry_on_failure=True,
    )

    # Score a subset (indices 0, 3, 6) to save API calls
    indices_to_score = [0, 3, 6]

    for idx in indices_to_score:
        ex = examples[idx]
        predicted_text = format_actions(ex["predicted_actions"])
        ground_truth_text = format_actions(ex["true_labels"])

        reward = await scorer(predicted_text, ground_truth_text)
        print(f"Example {idx}: reward = {reward:.4f}")
        print(f"  time_range: {ex.get('time_range', 'N/A')}")
        print(f"  old utility: {ex.get('utility', 'N/A')}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
