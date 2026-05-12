# Defender KQL Collection

A curated, auto-synced collection of KQL queries for Microsoft Defender and other platforms.

---

## Stats

| | |
|---|---|
| External queries (source files) | 724 |
| Custom queries | 1 |
| Sources | 4 |
| Last sync | 2026-05-12 10:24:35 UTC |

## Recently Added

See **[RECENT.md](RECENT.md)** for the latest 25 additions.

---

## Topics

Queries are organised by topic, regardless of source. Each topic folder contains subfolders per source (`bert-janp`, `slimkql`, etc.).

| Folder | Topic | Files |
|--------|-------|-------|
| `identity` | Identity & Authentication | 142 |
| `endpoint` | Endpoint & Device Security | 162 |
| `email` | Email & Office 365 | 36 |
| `cloud` | Cloud Infrastructure (Azure) | 23 |
| `vulnerabilities` | Vulnerabilities & Patch Management | 97 |
| `cloud-apps` | Cloud Apps & SaaS | 19 |
| `threat-hunting` | Threat Hunting | 59 |
| `detection` | Detection Rules | 50 |
| `dfir` | DFIR & Incident Response | 13 |
| `secops` | Security Operations | 17 |
| `xdr` | Defender XDR | 89 |
| `various` | Various & Learning | 17 |

---

## Sources

| Group | Repository | Platform | Format | Files | Description |
|-------|-----------|----------|--------|-------|-------------|
| **community** | [Bert-JanP Hunting Queries](https://github.com/Bert-JanP/Hunting-Queries-Detection-Rules) | MDE, Sentinel, DefenderXDR | `markdown` | 310 | Large collection of hunting queries and detection rules across Azure AD, MDE, Sentinel and XDR |
| **community** | [cyb3rmik3 KQL Threat Hunting](https://github.com/cyb3rmik3/KQL-threat-hunting-queries) | MDE, Sentinel, DefenderXDR, Azure | `markdown` | 86 | Threat hunting and detection queries organized by product: Azure, MDE, Sentinel, Office365, EASM, MDVM |
| **community** | [SlimKQL Hunting Queries](https://github.com/SlimKQL/Hunting-Queries-Detection-Rules) | Sentinel, DefenderXDR, Azure, ADX | `kql` | 320 | Standalone KQL files organized by product: Azure, DefenderXDR, Sentinel, ADX — includes IOC lists |
| **community** | [KQL Cafe – KustoCon](https://github.com/KQLCafe/kustocon) | Sentinel, MDE | `kql` | 8 | KQL Cafe conference queries and demos |

> To add a new source: edit [`sources.yaml`](sources.yaml) and run `python scripts/sync.py`.
> To adjust topic classification: edit [`taxonomy.yaml`](taxonomy.yaml).

---

## Structure

```
queries/
├── external/                   # Auto-synced, organised by topic
│   ├── identity/               # Identity & Authentication
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
