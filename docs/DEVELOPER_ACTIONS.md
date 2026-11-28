# DEVELOPER_ACTIONS.md — what the developer does by hand

Steps the agent cannot do: on the VM, in the Google Cloud Console, or with real accounts. Each
phase adds its own section when it is built; tick a box when it is done and tell the agent the
result (it records the evidence in the M9 design). Open items stay here until ticked.

The VM runs the code of one branch. **Step 0 of each section** puts that code on the VM.

---

## M9-P1 — Go live (left open on 14 Nov 2026)

- [ ] Add the mentor's Gmail as a test user of the Google OAuth consent screen (Console → APIs &
      Services → OAuth consent screen → Test users).
- [ ] Confirm the nightly backup ran by itself (03:00 IST):
      `journalctl -u mediease-backup.service -n 5` ends with `backup: done`.

## M9-P2 — Alerts (built 27 Nov 2026; RUNBOOK §41)

- [ ] **0. Put the code on the VM** (in `/opt/mediease`). Until PR #87 is merged:
      `git fetch && git checkout m9/86-alerting-security && git pull && make up`.
      After the merge: `git checkout main && git pull && make up`.
- [ ] **1. The address.** `nano .env`, add `OPS_ALERT_EMAIL=<your address>` (one plain address).
      Then `make config-check` shows `alerts OPS_ALERT_EMAIL` masked, and `make alert-test`
      prints `ops-alert: sent to …`. Check the inbox **and the spam folder**.
- [ ] **2. The timer.**
      ```bash
      sudo cp infra/gcp/mediease-watch.service infra/gcp/mediease-watch.timer /etc/systemd/system/
      sudo systemctl daemon-reload && sudo systemctl enable --now mediease-watch.timer
      sudo systemctl start mediease-watch.service && journalctl -u mediease-watch.service -n 10
      ```
      The journal ends with `watch: all clear`.
- [ ] **3. The uptime check** in the Console: Monitoring → Uptime checks → Create, as written in
      RUNBOOK §41 (HTTPS, `mediease.duckdns.org`, path `/ready`, 5 minutes, content contains
      `"database":"ok"`, an email alert policy).
- [ ] **4. Test both, between 08:00 and 22:00 IST.** `docker compose stop api`; within about 10
      minutes you get "[MediEase alert] 1 new" (`[critical] api is not running`) and Google's
      incident email. Then `docker compose start api`; you get "1 resolved" and Google's
      recovery email.

## M9-P3 — Security review (review done 27 Nov 2026; RUNBOOK §15, §42, §43)

- [ ] **0. Put the code on the VM**, as in P2 step 0. `make up` also recreates the database
      container with the terse log settings (the data volume is kept; the old log is dropped).
- [ ] **1. Leave `SIGN_INS_PER_MINUTE` out of the VM's `.env`** (the default, 30, is the
      production value). Check: `grep SIGN_INS .env` prints nothing or `SIGN_INS_PER_MINUTE=30`.
- [ ] **2. The log review on the VM.** A day after step 0: `bash scripts/log-review.sh`. Expected:
      `log-review: nothing phone-, email- or Aadhaar-like in the last 168h` (before step 0 the
      database log may still show old lines; that is what step 0 fixes). Tell the agent the
      output (it holds counts only).
- [ ] **3. Try the patient-data commands once on the demo clinic** (RUNBOOK §43), so you know
      them before a real request arrives:
      ```bash
      make patient-data ARGS="export kesar-bagh-family-clinic KBFC-0002"
      ls -l .exports/                      # the .zip and nothing else
      ```
      Open the zip on your computer with 7-Zip (Windows' own Explorer cannot open AES zips),
      using the password the command printed once, then delete it on the VM:
      `rm .exports/kesar-bagh-family-clinic-kbfc-0002-*.zip`. Do **not** try `erase` on the demo
      clinic unless you are happy to lose that patient's details for the video.
- [ ] **4. Counsel (L-04):** confirm the breach clocks in RUNBOOK §15 and that anonymising (not
      deleting) clinical records on erasure meets the clinics' retention duty.

## M9-P5 — Onboarding rehearsal (prepared 28 Nov 2026; RUNBOOK §44)

The rehearsal is yours: the agent prepared the steps and the clock. About 70 minutes in all.

- [ ] **0. Put the code on the VM**, as in P2 step 0 (`make onboarding-report` comes with it).
- [ ] **1. Prepare** (not timed): the invented clinic, doctors and phones, and your Gmail plus
      addresses (`you+rh-owner@gmail.com` and so on), as listed in RUNBOOK §44.
- [ ] **2. Run it** (timed): the seven steps in RUNBOOK §44, from **Create clinic** to the first
      issued prescription. Note anything that slowed you down.
- [ ] **3. Read the clock:** `make onboarding-report SLUG=rehearsal-clinic-<yyyymmdd>` on the VM.
      Expected last line: `total N minutes; target under 60 (G4) MET`.
- [ ] **4. Suspend the test clinic** (ops → Clinics → *Suspend…*, reason *Other*, note
      "onboarding rehearsal").
- [ ] **5. Tell the agent** the report's output and your notes; it records them in the M9 design
      §13 and opens an issue for each real slowdown.
