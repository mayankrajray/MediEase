# scripts

One-off operational scripts, each with a docstring stating purpose, inputs and safety checks. Planned: `seed_demo.py` (M1, synthetic data only), `inspect_link_token.py` (M4), `erase_patient.py` (M6, audited). Scripts never bypass use cases for tenant data.

`fixtures/patients-import-sample.csv` (M2-P4) is the ops patient-import template with synthetic
people and `+91 90000 0xxxx` numbers. It deliberately contains a family on one phone, a child
without a guardian, a bad number and two rows that are already registered (one matches `make
seed`'s Asha Rao, one repeats an earlier row), so a dry run against the seeded `sample-clinic`
shows every kind of report entry. A test keeps it importable (`test_patient_import_http.py`).
