# Defender KQL Collection

A curated, auto-synced collection of KQL queries for Microsoft Defender and other platforms.

---

## Stats

| | |
|---|---|
| External queries (source files) | 39 |
| Custom queries | 1 |
| Sources | 1 |
| Last sync | 2026-04-07 09:51:25 UTC |

## Recently Added

See **[RECENT.md](RECENT.md)** for the latest 25 additions.

---

## Sources

| Group | Repository | Platform | Format | Files | Description |
|-------|-----------|----------|--------|-------|-------------|
| **community** | [Bert-JanP Hunting Queries](https://github.com/Bert-JanP/Hunting-Queries-Detection-Rules) | MDE, Sentinel, DefenderXDR | `markdown` | 39 | Large collection of hunting queries and detection rules (MD format) |
| **community** | [KQL Cafe – KustoCon](https://github.com/KQLCafe/kustocon) | Sentinel, MDE | `kql` | 0 | KQL Cafe conference queries and demos |

> To add a new source: edit [`sources.yaml`](sources.yaml) and run `python scripts/sync.py`.

---

## Structure

```
queries/
├── external/          # Auto-synced from sources.yaml
│   ├── bert-janp/     #   mirrors source repo folder structure
│   └── kqlcafe/
└── custom/            # Your own queries (add .kql files here)
    ├── template.kql
    └── template.yaml  # optional metadata sidecar
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
  community:          # group name (free choice)
    - name: "My Source"
      repo: "owner/repo"
      slug: "my-source"          # local folder name under queries/external/
      platform: [MDE, Sentinel]
      file_type: kql             # kql (default) or markdown
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
