# Maintenance scripts

These scripts are for maintainers and contributors; they are not part of the package. Run them
through nox (`uvx nox -s generate`) or directly with `uv run`.

| Script | Purpose |
|---|---|
| `gen_docs.py` | Generates `docs/reference/codes.md`, `tables.md` and `glossary.md` from the code. `--check` fails when they are out of date. |
| `gen_examples.py` | Generates the synthetic sample files in `examples/` (used by the README quickstart) from `tests/cufgen.py`. |
| `griffe_rst.py` | A griffe extension used by the docs build to render the reST roles in docstrings (`:class:`…) as Markdown. |

The generated files are committed. CI regenerates them and fails if the result differs.
