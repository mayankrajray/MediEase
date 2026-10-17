# Vendored prescription assets

Fonts for the in-house PDF renderer (ADR-0012, M4-P4). They are in the repository so a render
never fetches anything and the image builds the same way every time. A test
(`tests/unit/adapters/test_pdf_renderer.py`) checks the hashes below.

| File | SHA-256 | Source |
|---|---|---|
| `NotoSans-Regular.ttf` (2.015) | `478c558ea716033cd60c03438f628dfa75694dcf6b5f6d505a2f05fd2b4f3823` | notofonts/notofonts.github.io, `fonts/NotoSans/hinted/ttf/` |
| `NotoSans-Bold.ttf` (2.015) | `1df075a380fc7cb898acf64c1f7b3b4dd780de3caa860178bf929de35817a913` | as above |
| `NotoSansDevanagari-Regular.ttf` (2.007) | `4e3c66638958c3e2ab5d37f47a8deb89fffeb7be9985c665a519bbc7ba762313` | notofonts/notofonts.github.io, `fonts/NotoSansDevanagari/hinted/ttf/` |
| `NotoSansDevanagari-Bold.ttf` (2.007) | `6a09c8d797cfc803d32cdc731e809424d74cbaff59f503de34ade421a08e5bc2` | as above |
| `OFL.txt` | `a216f6f8d85c7228093e0ee5e258d9d377e6671f68acb4db1930b29583d0f331` | notofonts/devanagari |

Licence: SIL Open Font License 1.1 (`OFL.txt`), Copyright 2022 The Noto Project Authors. The
fonts are embedded (subset) in each PDF, which the OFL permits; they are not sold on their own.

To update a font: replace the file, update its row here and the hash in the test, and check a
rendered Hindi prescription by eye.
