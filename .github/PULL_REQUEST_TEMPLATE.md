## What and why

<!-- What does this change, and why? Link the issue: "Fixes #123". -->

## How was it tested?

<!-- New/changed tests, manual checks, which exporting software or CUF dialect it concerns. -->

## Checklist

- [ ] **No real client or company data** is included anywhere: no real CUF files, names, addresses or
      prices in code, tests, fixtures, docs or this description.
- [ ] New sample files are generated or hand-made, state the dialect they imitate, and may be published
      under the MIT license.
- [ ] Tests added or updated; tests that need an optional extra are marked `@pytest.mark.extras`.
- [ ] No new runtime dependency in the core; optional libraries are imported lazily.
- [ ] Numbers stay `decimal.Decimal`; raw text is kept; nothing is coerced silently.
- [ ] New or changed finding codes are registered in `pycuf.findings.CODES` and documented.
- [ ] `CHANGELOG.md` updated under `[Unreleased]`.
- [ ] `uvx nox` passes locally.
