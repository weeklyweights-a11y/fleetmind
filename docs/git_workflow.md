# Git workflow — commit per step

Fleetmind tracks progress **one git commit per completed plan step** (not one commit per entire phase).

## Initialize (once)

```bash
cd d:\Fleetmind
git init
```

## After each plan step

```bash
git add <files for this step only>
git commit -m "phase-N: <step-id> — <what was completed and why>"
```

## Phase 3 step labels

| Step | Commit message prefix |
|------|------------------------|
| foundation | `phase-3: foundation` |
| compliance-core | `phase-3: compliance-core` |
| truck-postgres-agents | `phase-3: truck-postgres-agents` |
| graph-alignment | `phase-3: graph-alignment` |
| fleet-agents | `phase-3: fleet-agents` |
| driver-vendor-stubs | `phase-3: driver-vendor-stubs` |
| api-routes | `phase-3: api-routes` |
| document-api | `phase-3: document-api` |
| verify-phase3 | `phase-3: verify-phase3` |

## Tags (optional, at phase completion)

```bash
git tag phase-2-complete
git tag phase-3-complete
```

## Ignored paths

See `.gitignore` — never commit `.env`, `document_storage/`, or `data/`.
