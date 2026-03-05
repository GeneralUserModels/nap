"""Prepare Demo 1: generate MP4 video clips from consecutive labeled screenshots."""
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "public" / "data" / "demo1"
VIDEOS_DIR = DATA_DIR / "videos"
SOURCE_BASE = BASE.parent / "powernap" / "logs-elbo-on-0205"

SESSIONS = [
    "session_20260212_114126",
    "session_20260211_180308",
]

TARGET_WIDTH = 960
FPS = 1  # each frame shown for 1s (use playbackRate=0.5 in JS for 2s per frame)
MIN_SEGMENT_LEN = 20
MAX_SEGMENT_LEN = 40


def load_labels(session_dir: Path) -> list[dict]:
    labels_file = session_dir / "labels.jsonl"
    labels = []
    with open(labels_file) as f:
        for line in f:
            if line.strip():
                label = json.loads(line)
                label["_session_dir"] = str(session_dir)
                labels.append(label)
    return labels


def resolve_screenshot(label: dict) -> Path | None:
    """Find the screenshot file for a label."""
    screenshot_rel = label.get("screenshot_path", "")
    src_path = SOURCE_BASE.parent / screenshot_rel
    if src_path.exists():
        return src_path

    session_dir = Path(label["_session_dir"])
    start_time = label.get("start_time", "")
    src_path = session_dir / "labeled_screenshots" / f"{start_time}.png"
    if src_path.exists():
        return src_path

    return None


def format_timestamp(ts_str: str) -> str:
    """'2026-02-12_11-42-47-730086' -> '2026-02-12 11:42:47'"""
    parts = ts_str.split("_")
    if len(parts) >= 2:
        time_parts = parts[1].split("-")
        return f"{parts[0]} {':'.join(time_parts[:3])}"
    return ts_str


def classify_segment(labels: list[dict]) -> str:
    """Classify a segment by the dominant application/activity."""
    text_blob = " ".join(l["text"].lower() for l in labels)

    keywords = [
        ("VS Code", ["vs code", "vscode", "editor", ".py", ".js", ".ts", "code"]),
        ("Slack Messaging", ["slack", "message box", "direct message", "channel"]),
        ("Chrome Browsing", ["chrome", "browser", "tab", "url", "webpage", "google"]),
        ("Terminal", ["terminal", "command", "bash", "zsh", "cmd", "pip", "python", "npm"]),
        ("Overleaf / LaTeX", ["overleaf", "latex", "tex", "document", "paper"]),
        ("Zoom / Video", ["zoom", "video", "call", "meeting"]),
        ("YouTube", ["youtube", "video thumbnail"]),
        ("Google Docs", ["google doc", "google slides", "google drawings", "google sheets"]),
    ]

    scores = {}
    for name, kws in keywords:
        score = sum(text_blob.count(kw) for kw in kws)
        scores[name] = score

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "Desktop Activity"
    return best


def find_segments(all_labels: list[dict]) -> list[dict]:
    """Find 5-8 contiguous segments of consecutive labels with screenshots."""
    # First, filter to labels that have valid screenshots
    valid = []
    for label in all_labels:
        screenshot = resolve_screenshot(label)
        if screenshot:
            valid.append((label, screenshot))

    if not valid:
        return []

    # Find contiguous runs (same session, consecutive indices)
    segments = []
    current_run = [valid[0]]
    for i in range(1, len(valid)):
        prev_label, _ = valid[i - 1]
        curr_label, _ = valid[i]
        # Same session and close in time
        if prev_label["_session_dir"] == curr_label["_session_dir"]:
            current_run.append(valid[i])
        else:
            if len(current_run) >= MIN_SEGMENT_LEN:
                segments.append(current_run)
            current_run = [valid[i]]

    if len(current_run) >= MIN_SEGMENT_LEN:
        segments.append(current_run)

    # Split long runs into MAX_SEGMENT_LEN chunks
    final_segments = []
    for run in segments:
        for start in range(0, len(run), MAX_SEGMENT_LEN):
            chunk = run[start : start + MAX_SEGMENT_LEN]
            if len(chunk) >= MIN_SEGMENT_LEN:
                final_segments.append(chunk)

    # Pick up to 8 diverse segments
    if len(final_segments) > 8:
        # Evenly sample
        step = len(final_segments) / 8
        final_segments = [final_segments[int(i * step)] for i in range(8)]

    return final_segments


def create_video(segment: list[tuple[dict, Path]], video_path: Path) -> list[dict]:
    """Stitch PNGs into MP4 at FPS, return timestamp->label mappings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        labels_timeline = []
        for i, (label, screenshot) in enumerate(segment):
            # Resize to TARGET_WIDTH
            img = Image.open(screenshot)
            ratio = TARGET_WIDTH / img.width
            new_h = int(img.height * ratio)
            # Ensure even dimensions for video encoding
            new_h = new_h if new_h % 2 == 0 else new_h + 1
            img = img.resize((TARGET_WIDTH, new_h), Image.LANCZOS)
            img = img.convert("RGB")
            frame_path = Path(tmpdir) / f"frame_{i:04d}.png"
            img.save(frame_path, "PNG")

            time_sec = i / FPS
            ts_str = label.get("start_time", "")
            labels_timeline.append({
                "time": round(time_sec, 2),
                "text": label["text"],
                "timestamp": format_timestamp(ts_str) if ts_str else "",
            })

        # Use ffmpeg to stitch frames into video
        input_pattern = str(Path(tmpdir) / "frame_%04d.png")
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(FPS),
            "-i", input_pattern,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "medium",
            "-crf", "23",
            str(video_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)

    return labels_timeline


def main():
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading labels from sessions...")
    all_labels = []
    for session_name in SESSIONS:
        session_dir = SOURCE_BASE / session_name
        labels = load_labels(session_dir)
        all_labels.extend(labels)
    print(f"  Loaded {len(all_labels)} total labels")

    print("Finding contiguous segments...")
    segments = find_segments(all_labels)
    print(f"  Found {len(segments)} segments")

    # Remove the 5th segment (index 4, "Chrome Browsing") if it exists
    if len(segments) > 4:
        removed = segments.pop(4)
        removed_labels = [s[0] for s in removed]
        removed_title = classify_segment(removed_labels)
        print(f"  Removed segment 4 ({removed_title}, {len(removed)} frames)")

    manifest = []
    for idx, segment in enumerate(segments):
        labels_in_seg = [s[0] for s in segment]
        title = classify_segment(labels_in_seg)
        video_name = f"segment_{idx}.mp4"
        video_path = VIDEOS_DIR / video_name

        print(f"\n  Segment {idx}: {title} ({len(segment)} frames)")
        labels_timeline = create_video(segment, video_path)

        manifest.append({
            "video": f"/data/demo1/videos/{video_name}",
            "title": title,
            "labels": labels_timeline,
        })
        print(f"    -> {video_path} ({video_path.stat().st_size / 1024:.0f} KB)")

    manifest_path = DATA_DIR / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nWrote {len(manifest)} segments to {manifest_path}")


if __name__ == "__main__":
    main()
