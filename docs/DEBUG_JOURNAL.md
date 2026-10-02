# MediEase — Debug Journal

A running record of real bugs: what we saw, why it happened, how we fixed it, and what stops it
coming back. Search this file **before** debugging — the same failure may already be solved.

Rules:

- One entry per root cause, newest first.
- No patient data, real phone numbers or clinical content — use IDs and codes.
- Link the fixing commit and the test that now guards it.
- If the lesson is general, also update `DEBUGGING.md` §4 or `RUNBOOK.md`.

## Entry template

```markdown
### YYYY-MM-DD — <short title> (`ERROR_CODE` if any)

- **Milestone / area:** M3 / appointments
- **Symptom:** What was observed, where, by whom. Include request_id(s).
- **Impact:** Who was affected and how badly (local only / staging / pilot clinic).
- **Reproduction:** Minimal steps or the failing test name.
- **Investigation:** Evidence looked at, hypotheses tried and discarded.
- **Root cause:** The actual reason, one or two sentences.
- **Fix:** What changed. Commit: `<sha>` — PR: #<n>
- **Guard:** Test(s) added: `tests/...::test_...`
- **Prevention / follow-up:** Docs updated, alerts added, patterns to avoid.
- **Search keywords:** timezone, midnight, session, IST
```

---

## Entries

### 2026-10-01 — WSL terminal crashes during the M0-P2 dependency install

- **Milestone / area:** M0-P2 / developer environment (Windows 11 + WSL2 + Docker Desktop)
- **Symptom:** The WSL terminal window closed three times in a row while installing the API's
  Python dependencies; the install never finished.
- **Impact:** Local only. Blocked M0-P2.
- **Reproduction:** Docker Desktop running for a few hours, then a `pip install` in WSL.
- **Investigation:** Windows Event Log showed Resource-Exhaustion-Detector event 2004 ("low
  virtual memory") once per attempt, followed by `wslservice.exe` faulting (event 1000), "WSL
  Service terminated unexpectedly" (event 7034) and a `dwm.exe` crash. The top consumer listed in
  event 2004 was `com.docker.backend.exe` at ~30.8 GB of committed memory on a 15.7 GB machine
  (commit charge 40 of 41.8 GB). Not a dependency problem: pip used prebuilt wheels throughout.
- **Root cause:** The Docker Desktop backend process (a Windows process, not the WSL VM) grows
  its committed memory over time until Windows runs out of virtual memory, at which point the WSL
  service is killed. No `%USERPROFILE%\.wslconfig` existed, so the WSL VM was uncapped as well.
- **Fix:** Added `%USERPROFILE%\.wslconfig` with `memory=8GB`, `processors=4`, `swap=8GB`
  (`swapFile` under the user profile — the drive root is not writable by WSL). Stopped Docker
  Desktop during the install: commit charge fell from 40 GB to 11 GB and the install completed.
  Added `make install-api` so the venv is created reproducibly with `--prefer-binary`.
- **Guard:** None automated — host configuration. Check `free -h` in WSL shows the cap.
- **Prevention / follow-up:** Quit Docker Desktop when it is not needed (M0-P2 needs no
  containers). Before M0-P3, update Docker Desktop and restart it fresh; if
  `com.docker.backend.exe` grows past a few GB again, report it upstream. Python 3.14 (Ubuntu
  26.04 default) is not the project interpreter — use 3.12 (ADR-0002).
- **Search keywords:** WSL crash, terminal closes, low virtual memory, event 2004, wslservice,
  vmmem, com.docker.backend, wslconfig, pip install
