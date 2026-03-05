"""Compute embeddings, UMAP projection, and HDBSCAN clustering for scatter plot."""
import gzip
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "public" / "data" / "demo3"
SOURCE_BASE = BASE.parent / "powernap" / "logs-elbo-on-0205"
RETRIEVER_PATH = SOURCE_BASE / "retriever_step_001184.json.gz"
CACHE_DIR = BASE / "scripts" / ".cache"

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
BATCH_SIZE = 256
UMAP_N_NEIGHBORS = 15
UMAP_MIN_DIST = 0.1
HDBSCAN_MIN_CLUSTER_SIZE = 25
HDBSCAN_SUB_MIN_CLUSTER_SIZE = 25
OVERSIZED_CLUSTER_THRESHOLD = 1000
OUTLIER_STD_THRESHOLD = 5.0


def extract_rationale(text: str) -> str:
    """Extract cleaned rationale from <revise> tags."""
    match = re.search(r'<revise>(.*?)</revise>', text, re.DOTALL)
    if not match:
        return ""
    rationale = match.group(1).strip()
    rationale = re.sub(r'</?[a-zA-Z_][a-zA-Z0-9_]*>', '', rationale).strip()
    return rationale


def extract_hover_text(text: str) -> str:
    """First two sentences of rationale, up to 300 chars."""
    rationale = extract_rationale(text)
    if not rationale:
        return ""
    sentences = re.split(r'(?<=[.!?])\s+', rationale)
    result = " ".join(sentences[:2]).strip()
    return result[:300] + "..." if len(result) > 300 else result


STOPWORDS = {
    "the", "a", "an", "is", "was", "are", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "to", "of", "in",
    "for", "on", "with", "at", "by", "from", "as", "into", "through",
    "during", "before", "after", "above", "below", "between", "and",
    "but", "or", "nor", "not", "so", "yet", "both", "either", "neither",
    "each", "every", "all", "any", "few", "more", "most", "other", "some",
    "such", "no", "only", "same", "than", "too", "very", "just", "about",
    "up", "out", "if", "then", "also", "that", "this", "these", "those",
    "it", "its", "i", "me", "my", "we", "our", "you", "your", "he", "him",
    "his", "she", "her", "they", "them", "their", "what", "which", "who",
    "when", "where", "how", "there", "here", "while", "because", "since",
    "until", "although", "though", "even", "over", "under", "between",
}

HCI_STOPWORDS = {
    "clicked", "click", "mouse", "screen", "button", "window", "page",
    "text", "cursor", "scroll", "scrolled", "type", "typed", "typing",
    "opened", "open", "closed", "close", "selected", "select", "tab",
    "menu", "displayed", "display", "area", "panel", "bar", "user",
    "action", "actions", "left", "right", "top", "bottom", "next", "back", "new",
    "using", "used", "use", "within", "appears", "appeared", "appear",
    "showed", "show", "showing", "visible", "view", "viewed", "moved",
    "move", "pressed", "press", "entered", "enter", "navigated", "navigate",
    "containing", "contains", "contain", "section", "content", "item",
    "items", "list", "name", "icon", "link", "field", "input", "box",
    "label", "option", "options", "popup", "dialog", "dropdown",
    "switched", "switch", "switching", "titled", "title", "titled",
    "revise", "revising", "revised", "currently", "current", "previous",
    "located", "located", "position", "above", "below", "image",
    "browser", "desktop", "taskbar", "toolbar", "workspace",
    "full", "small", "large", "multiple", "various", "several",
}


def classify_cluster(texts: list[str]) -> str:
    """Auto-classify a cluster by keyword frequency, then extract a topic descriptor."""
    blob = " ".join(texts).lower()
    categories = [
        ("VS Code Editing", ["vs code", "vscode", "editor", "typed in the editor", "code editor"]),
        ("Git Operations", ["git", "commit", "branch", "merge", "pull request", "push"]),
        ("Terminal Commands", ["terminal", "command line", "bash", "zsh", "ran the command", "pip", "npm"]),
        ("Slack Messaging", ["slack", "message box", "direct message", "channel", "slack workspace"]),
        ("Chrome Browsing", ["chrome", "browser tab", "url bar", "navigated to", "webpage"]),
        ("GitHub Issues", ["github", "issue", "pull request", "repository", "pr #"]),
        ("Code Review", ["review", "diff", "comment on", "approve", "request changes"]),
        ("Google Docs", ["google doc", "google slides", "google drawings", "google sheets"]),
        ("Overleaf / LaTeX", ["overleaf", "latex", "tex file", "compile", "bibliography"]),
        ("Zoom / Meetings", ["zoom", "meeting", "video call", "screen share"]),
        ("YouTube", ["youtube", "video thumbnail", "watch"]),
        ("File Management", ["finder", "file", "folder", "directory", "moved", "renamed", "deleted"]),
        ("Email", ["email", "gmail", "inbox", "compose", "reply"]),
        ("Web Search", ["search", "google search", "searched for", "results"]),
        ("Note Taking", ["notes", "notion", "obsidian", "markdown"]),
        ("Weights & Biases", ["weights & biases", "wandb", "w&b", "dashboard", "training metrics"]),
        ("Debugging", ["debug", "error", "traceback", "exception", "breakpoint"]),
        ("Documentation", ["documentation", "readme", "docs", "wiki"]),
        ("Screenshot / Image", ["screenshot", "image", "photo", "picture"]),
        ("Diagram Editing", ["diagram", "draw", "shape", "arrow", "canvas"]),
    ]

    scores = {}
    for name, kws in categories:
        score = sum(blob.count(kw) for kw in kws)
        scores[name] = score

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        category = "Desktop Activity"
    else:
        category = best

    # Extract a topic-specific descriptor from cluster content
    category_keywords = set()
    for name, kws in categories:
        if name == category:
            for kw in kws:
                category_keywords.update(kw.split())
            break

    # Tokenize and count content words
    words = re.findall(r'[a-z][a-z0-9_]+', blob)
    skip = STOPWORDS | HCI_STOPWORDS | category_keywords
    word_counts = Counter(w for w in words if w not in skip and len(w) > 2)

    if word_counts:
        top_word = word_counts.most_common(1)[0][0]
        return f"{category}: {top_word.title()}"
    return category


UMAP_CLUSTER_DIMS = 20  # intermediate UMAP dims for clustering (not visualization)


def hierarchical_cluster(coords_2d: np.ndarray, embeddings: np.ndarray) -> np.ndarray:
    """Run HDBSCAN with hierarchical re-clustering of oversized clusters."""
    import hdbscan
    import umap

    # Reduce to intermediate dimensions for clustering (384D too high for density-based)
    umap_cluster_cache = CACHE_DIR / "umap_rationale_cluster.npy"
    if umap_cluster_cache.exists():
        print(f"Loading cached {UMAP_CLUSTER_DIMS}D UMAP for clustering...")
        coords_cluster = np.load(umap_cluster_cache)
        # Reapply if length doesn't match (e.g. after outlier removal changed count)
        if len(coords_cluster) != len(embeddings):
            print(f"  Cache size mismatch ({len(coords_cluster)} vs {len(embeddings)}), recomputing...")
            coords_cluster = None
        else:
            coords_cluster = coords_cluster
    else:
        coords_cluster = None

    if coords_cluster is None:
        print(f"Running UMAP to {UMAP_CLUSTER_DIMS}D for clustering...")
        reducer = umap.UMAP(
            n_components=UMAP_CLUSTER_DIMS,
            n_neighbors=UMAP_N_NEIGHBORS,
            min_dist=0.0,  # tighter for clustering
            metric="cosine",
            random_state=42,
        )
        coords_cluster = reducer.fit_transform(embeddings)
        np.save(umap_cluster_cache, coords_cluster)
        print(f"  Cached to {umap_cluster_cache}")

    print("Running initial HDBSCAN...")
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=HDBSCAN_MIN_CLUSTER_SIZE,
        metric="euclidean",
    )
    cluster_labels = clusterer.fit_predict(coords_cluster)

    counts = Counter(int(c) for c in cluster_labels if c >= 0)
    print(f"  Initial: {len(counts)} clusters")
    for cid, count in counts.most_common(5):
        print(f"    Cluster {cid}: {count} points")

    # Identify oversized clusters
    oversized = [cid for cid, count in counts.items() if count > OVERSIZED_CLUSTER_THRESHOLD]
    if not oversized:
        print("  No oversized clusters found")
        return cluster_labels

    print(f"  Oversized clusters to split: {oversized}")

    next_cluster_id = max(counts.keys()) + 1

    for cid in oversized:
        mask = cluster_labels == cid
        sub_coords = coords_cluster[mask]
        print(f"\n  Re-clustering cluster {cid} ({mask.sum()} points)...")

        sub_clusterer = hdbscan.HDBSCAN(
            min_cluster_size=HDBSCAN_SUB_MIN_CLUSTER_SIZE,
            metric="euclidean",
        )
        sub_labels = sub_clusterer.fit_predict(sub_coords)

        sub_counts = Counter(int(c) for c in sub_labels if c >= 0)
        n_sub = len(sub_counts)
        print(f"    Split into {n_sub} sub-clusters")

        # Map sub-cluster IDs to new global IDs
        sub_id_map = {}
        for sub_id in sorted(sub_counts.keys()):
            sub_id_map[sub_id] = next_cluster_id
            next_cluster_id += 1

        # Update the global labels
        indices = np.where(mask)[0]
        for i, idx in enumerate(indices):
            sub_id = int(sub_labels[i])
            if sub_id >= 0 and sub_id in sub_id_map:
                cluster_labels[idx] = sub_id_map[sub_id]
            else:
                cluster_labels[idx] = -1  # noise from sub-clustering

    return cluster_labels


def remap_cluster_ids(cluster_labels: np.ndarray) -> np.ndarray:
    """Remap cluster IDs to consecutive integers starting from 0."""
    unique_ids = sorted(set(int(c) for c in cluster_labels if c >= 0))
    id_map = {old: new for new, old in enumerate(unique_ids)}
    remapped = np.array([id_map.get(int(c), -1) for c in cluster_labels])
    return remapped


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading retriever docs...")
    with gzip.open(RETRIEVER_PATH) as f:
        retriever_data = json.loads(f.read())
    docs = retriever_data["docs"]
    print(f"  Loaded {len(docs)} docs")

    raw_texts = [d["text"] for d in docs]
    rationales = [extract_rationale(t) for t in raw_texts]
    # Keep only docs that have a real rationale (skip empty + boilerplate)
    SKIP_PREFIXES = [
        "There are no revision periods added in this hit",
    ]
    keep = [i for i, r in enumerate(rationales)
            if r and not any(r.startswith(p) for p in SKIP_PREFIXES)]
    rationales = [rationales[i] for i in keep]
    raw_texts = [raw_texts[i] for i in keep]
    print(f"  {len(keep)} docs with rationale (of {len(docs)} total)")

    # Check for cached embeddings
    embeddings_cache = CACHE_DIR / "embeddings_rationale.npy"
    if embeddings_cache.exists():
        print("Loading cached embeddings...")
        embeddings = np.load(embeddings_cache)
        print(f"  Shape: {embeddings.shape}")
    else:
        print(f"Computing embeddings with {EMBEDDING_MODEL}...")
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(EMBEDDING_MODEL)
        embeddings = model.encode(rationales, batch_size=BATCH_SIZE, show_progress_bar=True)
        embeddings = np.array(embeddings)
        np.save(embeddings_cache, embeddings)
        print(f"  Cached to {embeddings_cache}, shape: {embeddings.shape}")

    # UMAP
    umap_cache = CACHE_DIR / "umap_rationale_2d.npy"
    if umap_cache.exists():
        print("Loading cached UMAP projection...")
        coords_2d = np.load(umap_cache)
    else:
        print("Running UMAP...")
        import umap
        reducer = umap.UMAP(
            n_neighbors=UMAP_N_NEIGHBORS,
            min_dist=UMAP_MIN_DIST,
            metric="cosine",
            random_state=42,
        )
        coords_2d = reducer.fit_transform(embeddings)
        np.save(umap_cache, coords_2d)
        print(f"  Cached to {umap_cache}")

    # Remove UMAP outliers (points > N std devs from mean on either axis)
    mean = coords_2d.mean(axis=0)
    std = coords_2d.std(axis=0)
    inlier_mask = np.all(np.abs(coords_2d - mean) <= OUTLIER_STD_THRESHOLD * std, axis=1)
    n_outliers = (~inlier_mask).sum()
    print(f"Removing {n_outliers} UMAP outliers (>{OUTLIER_STD_THRESHOLD} std devs)")

    coords_2d = coords_2d[inlier_mask]
    embeddings = embeddings[inlier_mask]
    rationales = [r for r, keep in zip(rationales, inlier_mask) if keep]
    raw_texts = [t for t, keep in zip(raw_texts, inlier_mask) if keep]

    # HDBSCAN with hierarchical re-clustering (always re-run, no cache)
    print("Running hierarchical HDBSCAN clustering...")
    cluster_labels = hierarchical_cluster(coords_2d, embeddings)

    # Remap to consecutive IDs
    cluster_labels = remap_cluster_ids(cluster_labels)

    # Build output
    print("\nBuilding output JSON...")
    n_clusters = len(set(cluster_labels)) - (1 if -1 in cluster_labels else 0)
    print(f"  {n_clusters} clusters found")

    # Auto-name clusters by inspecting their texts
    cluster_names = {}
    for cid in sorted(set(int(c) for c in cluster_labels if c >= 0)):
        mask = cluster_labels == cid
        cluster_rationales = [rationales[i] for i in range(len(rationales)) if mask[i]]
        # Sample up to 50 texts for classification
        sample = cluster_rationales[:50]
        name = classify_cluster(sample)
        # Deduplicate if somehow two clusters get the same descriptor
        if name in cluster_names.values():
            counter = 2
            while f"{name} {counter}" in cluster_names.values():
                counter += 1
            name = f"{name} {counter}"
        cluster_names[cid] = name
        print(f"    Cluster {cid}: {mask.sum()} points -> {name}")

    points = []
    for i in range(len(raw_texts)):
        points.append({
            "x": round(float(coords_2d[i, 0]), 4),
            "y": round(float(coords_2d[i, 1]), 4),
            "cluster": int(cluster_labels[i]),
            "hover": extract_hover_text(raw_texts[i]),
        })

    # Cluster summary
    cluster_counts = Counter(int(c) for c in cluster_labels)
    clusters = []
    for cid, count in sorted(cluster_counts.items()):
        entry = {"id": cid, "color": "", "count": count}
        if cid >= 0 and cid in cluster_names:
            entry["name"] = cluster_names[cid]
        clusters.append(entry)

    output = {"points": points, "clusters": clusters}

    output_path = DATA_DIR / "embeddings.json"
    with open(output_path, "w") as f:
        json.dump(output, f)

    size_mb = output_path.stat().st_size / 1024 / 1024
    print(f"\nWrote {len(points)} points to {output_path} ({size_mb:.1f} MB)")

    # Print cluster size distribution
    print("\nCluster size distribution:")
    for cid, count in sorted(cluster_counts.items(), key=lambda x: -x[1]):
        pct = count / len(points) * 100
        name = cluster_names.get(cid, "Noise" if cid == -1 else f"Cluster {cid}")
        print(f"  {name}: {count} ({pct:.1f}%)")


if __name__ == "__main__":
    main()
