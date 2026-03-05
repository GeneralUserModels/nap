"""Prepare prediction quality demo data."""
import gzip
import json
import os
import re
from pathlib import Path
from PIL import Image

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "public" / "data" / "demo2"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
SOURCE_BASE = BASE.parent / "powernap" / "logs-elbo-on-0205"
RETRIEVER_PATH = SOURCE_BASE / "retriever_step_001184.json.gz"

TARGET_WIDTH = 960
JPEG_QUALITY = 80
NUM_EXAMPLES = 8
MIN_UTILITY = 0.5


def load_all_labels() -> dict[float, dict]:
    """Load labels from all sessions, indexed by first event timestamp."""
    labels_by_ts = {}
    for session_dir in sorted(SOURCE_BASE.iterdir()):
        labels_file = session_dir / "labels.jsonl"
        if not labels_file.exists():
            continue
        with open(labels_file) as f:
            for line in f:
                if not line.strip():
                    continue
                label = json.loads(line)
                raw_events = label.get("raw_events", [])
                if raw_events:
                    ts = raw_events[0].get("timestamp")
                    if ts:
                        labels_by_ts[ts] = label
                        label["_session_dir"] = str(session_dir)
    return labels_by_ts


def parse_actions(text: str) -> list[str]:
    """Extract <action> content from doc text."""
    actions = re.findall(r'<action>(.*?)</action>', text, re.DOTALL)
    return [a.strip() for a in actions if a.strip()]


def parse_revise(text: str) -> str:
    """Extract <revise> content from doc text, stripping XML tags."""
    match = re.search(r'<revise>(.*?)</revise>', text, re.DOTALL)
    if match:
        content = match.group(1).strip()
    else:
        # Fallback: strip all <revise> tags and use remaining text
        content = text
    # Strip any nested <revise>/<tool_call> etc. XML-like tags
    content = re.sub(r'</?[a-zA-Z_][a-zA-Z0-9_]*>', '', content).strip()
    # Collapse multiple newlines
    content = re.sub(r'\n{3,}', '\n\n', content)
    return content


def find_matching_labels(labels_by_ts: dict, event_ts: float, end_ts: float) -> list[dict]:
    """Find labels whose timestamp falls within the doc's time range."""
    matched = []
    for ts, label in labels_by_ts.items():
        if event_ts and end_ts and event_ts <= ts <= end_ts:
            matched.append(label)
    # Sort by timestamp
    matched.sort(key=lambda l: l.get("raw_events", [{}])[0].get("timestamp", 0))
    return matched[:8]  # Cap at 8 labels


def process_screenshot(src_path: Path, dst_path: Path):
    img = Image.open(src_path)
    ratio = TARGET_WIDTH / img.width
    new_h = int(img.height * ratio)
    img = img.resize((TARGET_WIDTH, new_h), Image.LANCZOS)
    img = img.convert("RGB")
    img.save(dst_path, "JPEG", quality=JPEG_QUALITY)


def format_timestamp(ts: float) -> str:
    """Format unix timestamp to readable string."""
    from datetime import datetime
    dt = datetime.fromtimestamp(ts)
    return dt.strftime("%Y-%m-%d %H:%M")


def main():
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading labels from all sessions...")
    labels_by_ts = load_all_labels()
    print(f"  Indexed {len(labels_by_ts)} labels by timestamp")

    print("Loading retriever docs...")
    with gzip.open(RETRIEVER_PATH) as f:
        retriever_data = json.loads(f.read())
    docs = retriever_data["docs"]
    print(f"  Loaded {len(docs)} docs")

    # Sort by utility descending
    docs_sorted = sorted(docs, key=lambda d: d["meta"]["utility"], reverse=True)

    # Filter to high-utility docs with valid timestamps
    candidates = []
    for doc in docs_sorted:
        utility = doc["meta"]["utility"]
        if utility < MIN_UTILITY:
            break
        event_ts = doc.get("event_ts")
        end_ts = doc["meta"].get("end_ts")
        if not event_ts or not end_ts:
            continue

        actions = parse_actions(doc["text"])
        revise = parse_revise(doc["text"])
        if len(actions) < 3:
            continue

        # Find matching true labels
        matched_labels = find_matching_labels(labels_by_ts, event_ts, end_ts)
        if len(matched_labels) < 2:
            continue

        candidates.append({
            "doc": doc,
            "actions": actions,
            "revise": revise,
            "matched_labels": matched_labels,
            "event_ts": event_ts,
            "end_ts": end_ts,
            "utility": utility,
        })

    print(f"  Found {len(candidates)} candidates with utility >= {MIN_UTILITY}")

    # Cherry-pick diverse examples
    selected = []
    seen_actions_prefix = set()
    for c in candidates:
        prefix = c["actions"][0][:30] if c["actions"] else ""
        if prefix in seen_actions_prefix:
            continue
        seen_actions_prefix.add(prefix)
        selected.append(c)
        if len(selected) >= NUM_EXAMPLES:
            break

    print(f"  Selected {len(selected)} diverse examples")

    examples = []
    for i, sel in enumerate(selected):
        # Find a screenshot from the matched labels
        screenshots = []
        for label in sel["matched_labels"][:1]:
            screenshot_rel = label.get("screenshot_path", "")
            src_path = SOURCE_BASE.parent / screenshot_rel
            if not src_path.exists():
                session_dir = Path(label["_session_dir"])
                start_time = label.get("start_time", "")
                src_path = session_dir / "labeled_screenshots" / f"{start_time}.png"

            if src_path.exists():
                dst_name = f"{i:03d}.jpg"
                dst_path = SCREENSHOTS_DIR / dst_name
                process_screenshot(src_path, dst_path)
                screenshots.append(f"/data/demo2/screenshots/{dst_name}")

        examples.append({
            "utility": sel["utility"],
            "predicted_actions": sel["actions"][:8],
            "revise_reasoning": sel["revise"][:500] if sel["revise"] else "",
            "true_labels": [l["text"] for l in sel["matched_labels"][:8]],
            "screenshots": screenshots,
            "time_range": f"{format_timestamp(sel['event_ts'])} — {format_timestamp(sel['end_ts'])}",
        })
        print(f"  [{i+1}] utility={sel['utility']:.2f}, {len(sel['actions'])} predicted, {len(sel['matched_labels'])} true")

    examples_path = DATA_DIR / "examples.json"
    with open(examples_path, "w") as f:
        json.dump(examples, f, indent=2)

    print(f"\nWrote {len(examples)} examples to {examples_path}")


if __name__ == "__main__":
    main()
