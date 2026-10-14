# Test fixtures

GlyphShift tests use small, open-licensed (or synthetically generated) fonts.

## Generated (by `tests/fixtures/build_fixtures.py`)

| File | Description |
|------|-------------|
| `latin_glyf.ttf` | Minimal Latin TrueType (glyf) font |
| `latin_cff.otf` | Minimal Latin CFF/OTF font |
| `persian_glyf.ttf` | Synthetic Persian/Arabic TTF with ZWNJ, Persian digits, and GSUB `arab` features |
| `variable_glyf.ttf` | Minimal variable TrueType with `fvar`/`gvar` |
| `collection.ttc` | Two-face TrueType collection |
| `وزیر-نمونه.ttf` | Copy of the Persian fixture under a Persian filename |

## Optional downloads

`build_fixtures.py` can also fetch a real OFL font (Vazirmatn) into `downloaded/` when network is available. CI relies on the synthetic fixtures so tests remain offline-friendly.

## Licenses

- Synthetic fixtures: generated for testing; no third-party copyright.
- Vazirmatn (if downloaded): SIL Open Font License 1.1 — https://github.com/rastikerdar/vazirmatn
