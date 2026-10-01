# Contributing to pycuf

Thanks for helping. pycuf reads, checks and analyses CUF-XML, the Dutch exchange format for
construction cost estimates. Bug reports, file-compatibility reports, anonymised samples,
documentation and code are all welcome.

By taking part you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). Report security problems
privately as described in [SECURITY.md](SECURITY.md), not in public issues. For questions about
using pycuf, see [SUPPORT.md](SUPPORT.md).

**Looking for something to work on?** Issues labelled
[`good first issue`](https://github.com/SpireflyHQ/pycuf/labels/good%20first%20issue) are small and
self-contained; [`help wanted`](https://github.com/SpireflyHQ/pycuf/labels/help%20wanted) marks
larger ones where help is welcome. Comment on the issue before you start, so work is not done
twice. [ARCHITECTURE.md](ARCHITECTURE.md) is a map of the code.

## Never share real CUF files

> [!CAUTION]
> **Never attach, upload, paste or commit a real CUF file from a client or company.** This applies
> to issues, pull requests, discussions, gists and test fixtures. Estimates contain names and
> addresses of clients and sites, and prices that are commercially sensitive (they are often
> bids). Sharing them, also with AI tools and chat services, can break the GDPR (AVG) and
> confidentiality agreements.

Instead, share:

- the **pycuf version**, **Python version** and the **software that exported the file**
  (`SYSTEEMHUIS`, if present);
- the **finding codes** (`CUF<nnnn>`) and messages that pycuf reported;
- a **minimal, hand-made or anonymised snippet** that reproduces the problem (see
  [Contributing anonymised samples](#contributing-anonymised-samples)).

## Development setup

You need [uv](https://docs.astral.sh/uv/). uv installs the right Python for you.

```bash
git clone https://github.com/SpireflyHQ/pycuf.git
cd pycuf
uv sync --all-extras          # creates .venv with the package, all extras and the dev groups
uvx prek install              # git hooks (or: uvx pre-commit install)
uvx nox                       # the main CI checks: lint, type checks and tests
```

The core library has **no runtime dependencies**. Everything outside the standard library
(nanoarrow, polars, pandas, pyarrow, typer) is an optional extra and must only be imported
lazily, inside the function that needs it, via `pycuf._optional`. CI has a job that installs the
wheel with no third-party packages at all and runs the core test suite.

## Everyday commands

The common tasks are [nox](https://nox.thea.codes/) sessions; `uvx nox -l` lists them:

| Session | Does |
|---|---|
| `uvx nox -s lint` | all pre-commit hooks (ruff, typos, zizmor, uv-lock, validate-pyproject, …) |
| `uvx nox -s typing` | mypy (strict) and pyright's public-API completeness check |
| `uvx nox -s tests -- -x` | the tests with all extras; options after `--` go to pytest |
| `uvx nox -s tests-core` | the tests that need no extra, without any extra installed |
| `uvx nox -s generate` | regenerate the reference pages and the example files |
| `uvx nox -s docs` | build the documentation (`-- serve` for a live preview) |

The same work with plain `uv run`, in the development environment:

```bash
uv run pytest                          # tests (all extras installed by `uv sync --all-extras`)
uv run pytest --cov                    # with coverage
uv run pytest -m "not extras"          # only the tests that need no optional extras
uv run ruff check --fix                # lint
uv run ruff format                     # format
uv run mypy                            # type check (strict; blocking in CI)
uvx prek run --all-files               # all hooks
```

Test markers (see `[tool.pytest.ini_options]` in `pyproject.toml`):

- `extras`: the test needs an optional extra (`arrow`, `polars`, `pandas`, `parquet`, `cli`).
  Mark every such test, or the no-extras CI job fails.
- `corpus`: the test reads the private corpus of real files (below); skipped when it is absent.

Prefer **generated** test input (`tests/cufgen.py`) over fixture files. `cufgen` builds a random
but reproducible estimate, computes its expected totals independently, and writes it in the
dialects of real exporters (`standard`, `ibis`, `forum`, `dataviewers`, `bakkerspees`). A test for
a quirk should build the smallest document that shows it.

### The private corpus

To test against real files you are allowed to use, put them in `tests/corpus/` (git-ignored) or
point `PYCUF_CORPUS` at a directory, and run `uv run pytest -m corpus`. Never commit them.

## Generated files

`docs/reference/codes.md`, `tables.md` and `glossary.md` are generated from the code by
`scripts/gen_docs.py`, and `examples/*.xml` by `scripts/gen_examples.py`. Do not edit them by
hand; run `uvx nox -s generate` and commit the result together with the change that caused it. CI
fails when they are stale. See [scripts/README.md](scripts/README.md).

## Adding a finding code

Every problem pycuf reports is a `Finding` with a stable code `CUF<nnnn>`. Codes are part of the
public API: users filter and silence them.

1. Pick the next free number in the right range: `1xxx` input/encoding, `2xxx` XML/security,
   `3xxx` structure and values, `4xxx` sort codes, `5xxx` totals, `7xxx` data quality and lenient
   parsing.
2. Register it in `CODES` in `src/pycuf/findings.py` with its default `Severity` (`ERROR` = the
   file violates CUF-XML 4.003; `WARNING` = likely a data problem; `INFO` = notable) and a short
   English title.
3. Emit it with `FindingCollector.add("CUF….", message, line=…, path=…, value=…)`. Messages say
   what was found and where. For problems an exporter makes on every element, tally them so they
   are reported once with a count (see `_build.py`).
4. Add a test that triggers the finding, and check that a valid document does **not** produce it.
5. Run `uvx nox -s generate` and add an entry to `CHANGELOG.md`.

Never renumber a code, reuse a retired code or change its meaning.

## Adding a policy option

Interpretations of the calculation rules live in `pycuf.policy.Policy`. A new option needs a
`Literal` type, a default that keeps existing results unchanged, a field in `_PolicyChanges`, a
check in `__post_init__`, documentation in `docs/guide/calculation.md`, and a test. Never change
the meaning of an existing preset; add a new one instead.

## Contributing anonymised samples

The step-by-step procedure is in the
[anonymising guide](https://spireflyhq.github.io/pycuf/how-to/anonymise-a-sample/). In short:
real-world quirks (a vendor's odd namespace, a wrong encoding, a vendor attribute, totals that do
not add up, …) are the most valuable contributions, but they must arrive **without any real
data**:

- **Best:** describe the quirk and share a small **hand-written** snippet, or a new dialect in
  `tests/cufgen.py`, that reproduces it.
- **If you must start from a real file:** replace every name, address, project name and number,
  description and code with fictitious values. Change amounts as well, keeping only what the
  quirk needs. Remove everything not needed to show the problem. Keep the encoding, BOM, line
  endings and namespace exactly as they were, because those are often the bug.
- State the exporting software and version, and confirm in the pull request that the sample
  contains **no real data** and that you may publish it under the project's MIT license.

Samples that might contain real data are deleted without review.

## Pull requests

- Open an issue first for larger changes, so we can agree on the approach.
- Keep pull requests focused. Include tests and update the documentation and `CHANGELOG.md`
  (under `[Unreleased]`, in the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
  categories: Added, Changed, Deprecated, Removed, Fixed, Security).
- Changes to the public API follow the
  [versioning policy](https://spireflyhq.github.io/pycuf/versioning/): deprecate first with a
  `DeprecationWarning`, remove in a later minor release.
- CI must pass: ruff, mypy, tests on Linux/macOS/Windows, the no-extras job, the generated-files
  check and zizmor.
- Hard rules: numbers are `decimal.Decimal`, never `float`; keep raw text next to parsed values;
  never silently coerce; data problems never stop a file from loading; refuse DOCTYPE/ENTITY
  declarations and never use a parser "recover" mode.
- Do not copy text from the CUF-XML specification documents into the code or documentation; they
  are copyrighted. Describe the format in your own words and link to the source.

## Commit messages

Follow the usual git conventions (see git's
[SubmittingPatches](https://git-scm.com/docs/SubmittingPatches) and
[How to Write a Git Commit Message](https://cbea.ms/git-commit/)):

- a subject line of about 50 characters, in the imperative mood ("fix", not "fixed"), without a
  full stop, prefixed with the kind of change in lower case: `feat:`, `fix:`, `docs:`, `test:`,
  `ci:`, `refactor:`, `perf:` or `chore:` (as in [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/));
  mark breaking changes with `!`, e.g. `feat!: rename Totals.extended`;
- a blank line, then a body wrapped at 72 characters that explains what changed and why, when the
  subject alone does not;
- release commits are `Release X.Y.Z`.

```text
fix: count a factor of 0 as 1 for DOORREKEN_HOEVEELHEID

The usage rules say an empty or zero factor counts as 1, but the
bundle multiplier was read literally, so element estimates with a
zero multiplier came out as 0.
```

## Releasing (maintainers)

1. `uv version --bump patch|minor|major`. For a pre-release, bump a release component too:
   `uv version --bump minor --bump rc` (0.1.0 → 0.2.0rc1), then `uv version --bump rc`
   (→ 0.2.0rc2) and `uv version --bump stable` (→ 0.2.0). Also update `version` and
   `date-released` in `CITATION.cff` (a test checks the version).
2. Move the `[Unreleased]` entries in `CHANGELOG.md` under the new version and date.
3. Commit, then `git tag -a vX.Y.Z -m "pycuf X.Y.Z"` and `git push --follow-tags`.
4. The `Release` workflow checks that the tag matches the version, builds and checks the
   distributions, signs them with Sigstore, waits for approval in the `pypi` environment,
   publishes with Trusted Publishing (with attestations) and creates the GitHub release with the
   CHANGELOG section as its notes. Pre-release tags (`a`, `b`, `rc`, `.dev`) go to TestPyPI only.

### One-time repository setup

Settings that live on GitHub, not in files:

- **Labels** used by the issue forms (GitHub drops labels that do not exist):
  `gh label create triage --color FBCA04 --description "Needs maintainer review"` and
  `gh label create compatibility --color 1D76DB --description "A file from some software is read incorrectly"`,
  plus `dependencies`, `security` and `breaking`. The defaults (`bug`, `enhancement`,
  `documentation`, `question`, `good first issue`, `help wanted`) already exist.
- **Rulesets:** on `main`, block force pushes and deletions and require the `CI OK` check and a
  pull request (admins may bypass); on tags `v*`, restrict creation, update and deletion to admins.
- **Security:** enable private vulnerability reporting (SECURITY.md relies on it).
- **Environments:** `pypi` (required reviewer, tags `v*`) and `testpypi`, with matching trusted
  publishers on PyPI and TestPyPI.
- **Pages:** source = GitHub Actions. **Releases:** enable immutable releases.
- After the first release, register for the
  [OpenSSF Best Practices badge](https://www.bestpractices.dev/).
