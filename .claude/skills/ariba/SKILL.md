---
name: ariba
description: Project memory system for texas-isd-finances. The agent has NO memory between sessions — this skill is how it catches up and how it saves state. Use it whenever the user types /ariba, asks to "catch up", "save notes", "update the log", "what's the current state", "where did we leave off", or at the START of any session before substantial work, and at the END of any session where anything changed. Also use before answering questions about project history, past decisions, credentials setup, or deployment state — the answers live in the log, not in memory.
---

# Ariba — Project Memory for Texas ISD Finances

You are an amnesiac engineer with a perfect notebook. Every session starts
from zero; the ONLY durable memory is what's committed to this repository.
This skill defines how to restore context and how to persist it. Treat the
notebook as sacred: an unlogged decision is a decision the next session will
re-litigate, and an unlogged gotcha is a bug the next session will re-ship.

## Modes

Pick the mode from the user's words. Bare `/ariba` at the start of a session
means catch-up; after work has happened it usually means save. When unsure,
do catch-up first — it's read-only and cheap.

### Mode 1 — Catch up (start of session, or "where were we?")

Read, in order:
1. `CLAUDE.md` (repo root) — the boot sector: identity, live URLs, invariants,
   current status block.
2. `docs/ENGINEERING_LOG.md` — read the LAST 2-3 entries fully; skim older
   entry headlines. Newest entries are at the TOP.
3. `git log --oneline -10` and `git status` — what actually changed lately;
   trust git over the log if they disagree (then fix the log).
4. Live health, because documents can lie but production can't:
   ```bash
   curl -s -m 20 https://texas-isd-finances.vercel.app/health
   curl -s -m 20 https://texas-isd-finances.vercel.app/stats
   ```
   `{"status":"healthy"}` + real stats = all systems go. `degraded` or a
   timeout = investigate before anything else (first suspect: Supabase free
   tier pauses after ~7 days idle — wake it in the dashboard).

Then brief the user in a few sentences: current state, anything broken, and
the open items list from CLAUDE.md. Do not start other work until this
picture is established.

### Mode 2 — Save (end of session, after milestones, or "update the notes")

1. Append a new entry at the TOP of `docs/ENGINEERING_LOG.md` (below the
   header), using the entry template in that file. Write it for a stranger
   with zero context — that stranger is you, tomorrow. Capture:
   - **What changed** (facts: files, deployments, data)
   - **Why** (the reasoning — this is the part git can't record)
   - **Gotchas discovered** (anything that cost >10 minutes to figure out)
   - **Open items** (carried forward + new)
2. Update the `## Current Status` block in `CLAUDE.md` — keep it a snapshot,
   not a history; the log holds history.
3. If any invariant changed (URL, project ref, dependency pin, deploy
   procedure), update the relevant CLAUDE.md section too.
4. Commit and push:
   ```bash
   git add CLAUDE.md docs/ENGINEERING_LOG.md
   git commit -m "ariba: session log — <one-line summary>"
   git push -u origin <current-branch>
   ```
   Unpushed memory is no memory — the container is ephemeral. Never end a
   session with the log dirty.

### Mode 3 — Quick note (`/ariba note <text>`)

Append the note under the current (topmost) log entry's **Notes** section
with a timestamp, commit, push. No ceremony.

## Rules that keep the memory trustworthy

- **Never log secrets.** Log WHERE credentials live (e.g., "Vercel env
  vars"), never values. The log is committed to a repo that may go public.
- **Log decisions with their why.** "Chose transaction pooler (6543) because
  serverless + asyncpg needs statement_cache_size=0" is memory. "Updated DB
  config" is noise.
- **Correct, don't rewrite.** If an old entry proves wrong, add a dated
  correction to the new entry; append-only history is what makes the log
  auditable.
- **Verify before you brief.** The catch-up health checks exist because a
  stale "all green" note is worse than no note.
- **Keep CLAUDE.md lean.** It loads into every session's context. Facts that
  rarely change + current status only; push everything else into the log.
