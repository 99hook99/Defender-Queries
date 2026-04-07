#!/usr/bin/env python3
"""
KQL Collection Sync
-------------------
Pulls KQL queries from sources defined in sources.yaml.

Supported file_type values per source:
  kql       — plain .kql files (default)
  markdown  — .md files with embedded ```KQL blocks; extracted per platform section

Tracks additions in manifest.json.
Regenerates RECENT.md and README.md after each sync.

Usage:
    python scripts/sync.py              # sync all sources
    python scripts/sync.py --dry-run   # show what would change
    python scripts/sync.py --readme    # regenerate docs only (no download)

Set GITHUB_TOKEN env var to avoid rate limits (60 → 5000 req/h).
"""

import argparse
import base64
import json
import os
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

BASE_DIR = Path(__file__).parent.parent
SOURCES_FILE = BASE_DIR / "sources.yaml"
TAXONOMY_FILE = BASE_DIR / "taxonomy.yaml"
MANIFEST_FILE = BASE_DIR / "manifest.json"
QUERIES_DIR = BASE_DIR / "queries"
RECENT_FILE = BASE_DIR / "RECENT.md"
README_FILE = BASE_DIR / "README.md"

GITHUB_API = "https://api.github.com"
RECENT_COUNT = 25


# ---------------------------------------------------------------------------
# Taxonomy / topic resolution
# ---------------------------------------------------------------------------

def load_taxonomy() -> dict:
    if TAXONOMY_FILE.exists():
        with open(TAXONOMY_FILE) as f:
            return yaml.safe_load(f)
    return {"topics": {}}


def resolve_topic(file_path: str, taxonomy: dict) -> str:
    """
    Determine the topic for a file based on its path.
    Checks folder_contains rules first, then filename_contains.
    Returns the topic key or 'various' if nothing matches.
    """
    path_str = file_path.replace("\\", "/")
    # Normalise: lower-case path components for folder matching
    parts = [p.lower() for p in Path(file_path).parts]
    filename = Path(file_path).name.lower()

    for topic, rules in taxonomy.get("topics", {}).items():
        # 1. Folder-based match: any path component contains the rule string
        for pattern in rules.get("folder_contains", []):
            pat_lower = pattern.lower()
            # Check if any folder component contains the pattern
            # Also support slash-separated sub-patterns like "Azure/Arc"
            if "/" in pat_lower:
                if pat_lower in path_str.lower():
                    return topic
            else:
                if any(pat_lower in part for part in parts[:-1]):  # exclude filename part
                    return topic

        # 2. Filename keyword match
        for keyword in rules.get("filename_contains", []):
            if re.search(keyword, filename, re.IGNORECASE):
                return topic

    return "various"


# ---------------------------------------------------------------------------
# GitHub helpers
# ---------------------------------------------------------------------------

def _headers() -> dict:
    h = {"Accept": "application/vnd.github.v3+json"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        h["Authorization"] = f"token {token}"
    return h


def _get(url: str) -> dict:
    resp = requests.get(url, headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_repo_default_branch(repo: str) -> str:
    """Return the default branch name for a repo."""
    data = _get(f"{GITHUB_API}/repos/{repo}")
    return data.get("default_branch", "main")


_repo_branch_cache: dict[str, str] = {}


def get_repo_tree(repo: str) -> tuple[list[dict], str]:
    """Return (flat file tree, branch) for a GitHub repo."""
    if repo not in _repo_branch_cache:
        _repo_branch_cache[repo] = get_repo_default_branch(repo)
    branch = _repo_branch_cache[repo]
    data = _get(f"{GITHUB_API}/repos/{repo}/git/trees/{branch}?recursive=1")
    return data.get("tree", []), branch


def download_raw(repo: str, file_path: str) -> str:
    """Download file content via raw.githubusercontent.com (no API rate limit for content)."""
    if repo not in _repo_branch_cache:
        _repo_branch_cache[repo] = get_repo_default_branch(repo)
    branch = _repo_branch_cache[repo]
    encoded = urllib.parse.quote(file_path)
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/{encoded}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


# ---------------------------------------------------------------------------
# KQL extraction from Markdown
# ---------------------------------------------------------------------------

# Platform heading aliases  →  canonical name used in saved filename
_PLATFORM_ALIASES: dict[str, str] = {
    "defender xdr":          "DefenderXDR",
    "microsoft defender xdr": "DefenderXDR",
    "mde":                   "MDE",
    "defender for endpoint": "MDE",
    "microsoft defender for endpoint": "MDE",
    "sentinel":              "Sentinel",
    "microsoft sentinel":    "Sentinel",
    "defender for identity": "DefenderIdentity",
    "defender for cloud apps": "DefenderCloudApps",
    "defender for cloud":    "DefenderCloud",
    "graph api":             "GraphAPI",
    "log analytics":         "LogAnalytics",
}

_CODE_BLOCK_KQL_RE = re.compile(r"```(?:kql|KQL|kusto|Kusto)\s*\n(.*?)```", re.DOTALL)
_CODE_BLOCK_ANY_RE = re.compile(r"```\w*\s*\n(.*?)```", re.DOTALL)
_HEADING_RE = re.compile(r"^#{1,4}\s+(.+)$", re.MULTILINE)


def _platform_from_heading(heading: str) -> str:
    """Map a markdown heading to a canonical platform slug (or 'General')."""
    return _PLATFORM_ALIASES.get(heading.strip().lower(), "General")


def extract_kql_blocks(md_content: str, code_fence: str = "kql") -> list[tuple[str, str]]:
    """
    Parse a markdown file and return a list of (platform, kql_code) tuples.
    Each ```KQL block is attributed to the nearest preceding heading.
    """
    results: list[tuple[str, str]] = []
    block_re = _CODE_BLOCK_ANY_RE if code_fence == "any" else _CODE_BLOCK_KQL_RE

    # Split into segments between headings
    headings = list(_HEADING_RE.finditer(md_content))
    # Build (start, end, heading_text) slices
    slices: list[tuple[int, int, str]] = []
    for i, m in enumerate(headings):
        start = m.start()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(md_content)
        slices.append((start, end, m.group(1)))

    if not slices:
        # No headings — grab all KQL blocks as "General"
        for block in block_re.finditer(md_content):
            results.append(("General", block.group(1).strip()))
        return results

    for start, end, heading in slices:
        platform = _platform_from_heading(heading)
        segment = md_content[start:end]
        for block in block_re.finditer(segment):
            results.append((platform, block.group(1).strip()))

    return results


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def load_manifest() -> dict:
    if MANIFEST_FILE.exists():
        with open(MANIFEST_FILE) as f:
            return json.load(f)
    return {"files": {}, "last_sync": None}


def save_manifest(manifest: dict):
    with open(MANIFEST_FILE, "w") as f:
        json.dump(manifest, f, indent=2, default=str)
        f.write("\n")


# ---------------------------------------------------------------------------
# Sync a single source
# ---------------------------------------------------------------------------

def sync_source(source: dict, manifest: dict, dry_run: bool, taxonomy: dict) -> list[dict]:
    repo = source["repo"]
    slug = source.get("slug", repo.split("/")[1].lower())
    file_type = source.get("file_type", "kql")
    code_fence = source.get("code_fence", "kql")

    print(f"  [{source['name']}] fetching tree…")
    try:
        tree, _ = get_repo_tree(repo)
    except Exception as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        return []

    # Decide which files to process
    if file_type == "markdown":
        target_files = [f for f in tree if f["type"] == "blob" and f["path"].endswith(".md")
                        and not f["path"].lower().endswith("readme.md")]
    else:  # kql
        target_files = [f for f in tree if f["type"] == "blob" and f["path"].endswith(".kql")]

    print(f"  [{source['name']}] {len(target_files)} source files ({file_type})")

    new_files: list[dict] = []

    for file_info in target_files:
        file_path = file_info["path"]
        sha = file_info["sha"]
        key = f"{repo}/{file_path}"

        existing = manifest["files"].get(key, {})
        if existing.get("sha") == sha:
            continue  # unchanged

        topic = resolve_topic(file_path, taxonomy)
        # Files live at: queries/external/{topic}/{slug}/{filename}
        topic_dir = QUERIES_DIR / "external" / topic / slug

        if dry_run:
            status = "NEW" if not existing else "UPDATED"
            print(f"    [{topic}] {status}: {file_path}")
            continue

        try:
            raw_content = download_raw(repo, file_path)
        except Exception as e:
            print(f"  WARN: could not download {file_path}: {e}", file=sys.stderr)
            continue

        now = datetime.now(timezone.utc).isoformat()

        if file_type == "markdown":
            blocks = extract_kql_blocks(raw_content, code_fence=code_fence)
            if not blocks:
                continue

            stem = Path(file_path).stem

            for platform, kql_code in blocks:
                local_path = topic_dir / f"{stem}_{platform}.kql"
                local_path.parent.mkdir(parents=True, exist_ok=True)
                local_path.write_text(kql_code, encoding="utf-8")

            # Manifest entry: use first block's path as representative local_path
            rep_path = topic_dir / f"{stem}_{blocks[0][0]}.kql"
            manifest["files"][key] = {
                "sha": sha,
                "local_path": str(rep_path.relative_to(BASE_DIR)),
                "source": source["name"],
                "slug": slug,
                "topic": topic,
                "platform": source.get("platform", []),
                "file_type": "markdown",
                "kql_blocks": len(blocks),
                "added_at": existing.get("added_at") or now,
                "updated_at": now,
            }
            if not existing:
                new_files.append(manifest["files"][key])

        else:  # plain kql
            filename = Path(file_path).name
            local_path = topic_dir / filename
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_text(raw_content, encoding="utf-8")

            manifest["files"][key] = {
                "sha": sha,
                "local_path": str(local_path.relative_to(BASE_DIR)),
                "source": source["name"],
                "slug": slug,
                "topic": topic,
                "platform": source.get("platform", []),
                "file_type": "kql",
                "added_at": existing.get("added_at") or now,
                "updated_at": now,
            }
            if not existing:
                new_files.append(manifest["files"][key])

    return new_files


# ---------------------------------------------------------------------------
# RECENT.md
# ---------------------------------------------------------------------------

def generate_recent(manifest: dict):
    files = sorted(
        manifest["files"].values(),
        key=lambda x: x.get("added_at", ""),
        reverse=True,
    )[:RECENT_COUNT]

    lines = [
        "# Recently Added KQL Queries",
        "",
        f"_Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        f"Showing the last {RECENT_COUNT} additions (auto-generated by `scripts/sync.py`).",
        "",
        "| Query | Topic | Source | Added |",
        "|-------|-------|--------|-------|",
    ]

    for f in files:
        name = Path(f["local_path"]).stem
        path = f["local_path"]
        source = f["source"]
        topic = f.get("topic", "various")
        added = f.get("added_at", "")[:10]
        lines.append(f"| [{name}]({path}) | {topic} | {source} | {added} |")

    lines.append("")
    RECENT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"  RECENT.md updated ({len(files)} entries shown)")


# ---------------------------------------------------------------------------
# README.md
# ---------------------------------------------------------------------------

def generate_readme(manifest: dict, config: dict, taxonomy: dict = None):
    total = len(manifest["files"])
    last_sync_raw = manifest.get("last_sync") or ""
    last_sync = (last_sync_raw[:19].replace("T", " ") + " UTC") if last_sync_raw else "never"

    # Per-topic counts
    by_topic: dict[str, int] = {}
    for info in manifest["files"].values():
        t = info.get("topic", "various")
        by_topic[t] = by_topic.get(t, 0) + 1

    # Per-source counts
    by_source: dict[str, int] = {}
    for info in manifest["files"].values():
        src = info["source"]
        by_source[src] = by_source.get(src, 0) + 1

    # Build topics table
    topic_rows: list[str] = []
    topics_cfg = (taxonomy or {}).get("topics", {}) if taxonomy else {}
    for topic_key, topic_def in topics_cfg.items():
        count = by_topic.get(topic_key, 0)
        label = topic_def.get("label", topic_key) if isinstance(topic_def, dict) else topic_key
        topic_rows.append(f"| `{topic_key}` | {label} | {count} |")
    # Add "various" if not in taxonomy but has files
    if "various" not in topics_cfg and by_topic.get("various", 0):
        topic_rows.append(f"| `various` | Various & Learning | {by_topic['various']} |")

    topics_table = "\n".join(topic_rows) if topic_rows else "| | | |"

    # Build sources table
    source_rows: list[str] = []
    for group, sources in config.get("sources", {}).items():
        for s in sources:
            count = by_source.get(s["name"], 0)
            platforms = ", ".join(s.get("platform", []))
            desc = s.get("description", "")
            file_type = s.get("file_type", "kql")
            source_rows.append(
                f"| **{group}** | [{s['name']}](https://github.com/{s['repo']}) "
                f"| {platforms} | `{file_type}` | {count} | {desc} |"
            )

    sources_table = "\n".join(source_rows) if source_rows else "| | | | | | |"

    custom_files = list((QUERIES_DIR / "custom").rglob("*.kql"))
    custom_count = len(custom_files)

    readme = f"""# Defender KQL Collection

A curated, auto-synced collection of KQL queries for Microsoft Defender and other platforms.

---

## Stats

| | |
|---|---|
| External queries (source files) | {total} |
| Custom queries | {custom_count} |
| Sources | {len(by_source)} |
| Last sync | {last_sync} |

## Recently Added

See **[RECENT.md](RECENT.md)** for the latest {RECENT_COUNT} additions.

---

## Topics

Queries are organised by topic, regardless of source. Each topic folder contains subfolders per source (`bert-janp`, `slimkql`, etc.).

| Folder | Topic | Files |
|--------|-------|-------|
{topics_table}

---

## Sources

| Group | Repository | Platform | Format | Files | Description |
|-------|-----------|----------|--------|-------|-------------|
{sources_table}

> To add a new source: edit [`sources.yaml`](sources.yaml) and run `python scripts/sync.py`.
> To adjust topic classification: edit [`taxonomy.yaml`](taxonomy.yaml).

---

## Structure

```
queries/
├── external/                   # Auto-synced, organised by topic
│   ├── identity/               # Identity & Authentication
│   │   ├── bert-janp/
│   │   └── slimkql/
│   ├── endpoint/               # Endpoint & Device Security
│   ├── vulnerabilities/        # CVEs & Patch Management
│   ├── email/                  # Email & Office 365
│   ├── cloud/                  # Azure Cloud Infrastructure
│   ├── detection/              # Detection Rules
│   ├── threat-hunting/         # Threat Hunting
│   ├── dfir/                   # DFIR & Incident Response
│   ├── secops/                 # Security Operations
│   ├── cloud-apps/             # Cloud Apps & SaaS
│   ├── xdr/                    # Defender XDR
│   └── various/                # Learning, utilities
└── custom/                     # Your own queries
    ├── template.kql
    └── template.yaml
```

---

## Adding Your Own Queries

1. Create a `.kql` file anywhere under `queries/custom/`
2. Optionally add a `.yaml` sidecar (same name) with metadata — see [`queries/custom/template.yaml`](queries/custom/template.yaml)
3. Commit and push

---

## Adding a New External Source

Edit `sources.yaml`:

```yaml
sources:
  community:
    - name: "My Source"
      repo: "owner/repo"
      slug: "my-source"
      platform: [MDE, Sentinel]
      file_type: kql             # kql (default) or markdown
      code_fence: kql            # kql (default) or any (for plain ``` blocks)
      description: "..."
```

Then run:

```bash
python scripts/sync.py
```

---

## Running the Sync

```bash
pip install -r scripts/requirements.txt

# Full sync
python scripts/sync.py

# Preview changes without downloading
python scripts/sync.py --dry-run

# Regenerate README + RECENT only
python scripts/sync.py --readme
```

With GitHub token (5000 req/h instead of 60):

```bash
GITHUB_TOKEN=ghp_xxx python scripts/sync.py
```

---

## Automated Sync

GitHub Actions runs sync every **Monday at 06:00 UTC** and commits any new files back to the repo.
Manual trigger: Actions → *Sync KQL Sources* → Run workflow.
"""

    README_FILE.write_text(readme, encoding="utf-8")
    print("  README.md updated")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Sync KQL sources")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--readme", action="store_true", help="Regenerate docs only")
    args = parser.parse_args()

    with open(SOURCES_FILE) as f:
        config = yaml.safe_load(f)

    taxonomy = load_taxonomy()
    manifest = load_manifest()

    if not args.readme:
        print("Syncing sources…\n")
        total_new: list[dict] = []
        for group, sources in config.get("sources", {}).items():
            print(f"[{group}]")
            for source in sources:
                new = sync_source(source, manifest, dry_run=args.dry_run, taxonomy=taxonomy)
                total_new.extend(new)
            print()

        if not args.dry_run:
            manifest["last_sync"] = datetime.now(timezone.utc).isoformat()
            save_manifest(manifest)
            print(f"{len(total_new)} new source files added.\n")

    if not args.dry_run:
        print("Generating docs…")
        generate_recent(manifest)
        generate_readme(manifest, config, taxonomy)

    print("\nDone.")


if __name__ == "__main__":
    main()
