# Security

CUF files are **untrusted input**. They arrive from subcontractors, clients and third-party
software, and pycuf is often run on servers that process files from many sources. pycuf is
designed to read a hostile file safely: it must not read local files, open network connections,
or exhaust memory or CPU because of what a file contains.

To report a vulnerability, follow the [security policy](https://github.com/SpireflyHQ/pycuf/blob/main/SECURITY.md):
privately, never in a public issue.

## Threat model

| Threat | Mitigation |
|---|---|
| Entity expansion ("billion laughs", quadratic blow-up) | DOCTYPE and ENTITY declarations are refused before any expansion happens |
| External entities (XXE): reading local files, server-side requests | refused with the DOCTYPE; Expat never opens files or network connections; parameter-entity parsing is disabled |
| Deeply nested elements | `max_depth` (default 64; AFAS documents imports of up to 15 bundle levels) |
| Huge attribute values | `max_attribute_size` (default 1 Mi characters) |
| Huge files | `max_size` (default 256 MiB; real CUF files are rarely larger than a few MB) |
| Millions of findings | `max_findings_per_code` and `max_findings` |
| Silent data corruption | no parser "recover" mode; malformed XML is an error with a position; repairs are opt-in and reported |

pycuf only reads the paths and streams you pass in, never opens network connections, and never
writes anything except the export files you request.

Python can be linked against a system Expat. Expat versions before 2.7.2 have known
denial-of-service weaknesses (see the
[Python XML security notes](https://docs.python.org/3/library/xml.html#xml-security)); keep your
Python and Expat up to date. pycuf's refusal of DTDs does not depend on the Expat version.

## DOCTYPE and ENTITY declarations are refused

CUF-XML never uses a DTD. pycuf's parser, built on the standard library's `pyexpat`, raises
`ForbiddenConstructError` as soon as it meets a DOCTYPE, ENTITY, unparsed-entity or notation
declaration, or an external entity reference:

```python
>>> pycuf.read(b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x "y">]><CUF/>')
Traceback (most recent call last):
  ...
pycuf.errors.ForbiddenConstructError: DOCTYPE/ENTITY declarations are not allowed in CUF-XML (refused for security)
```

`pycuf.validate()` reports the same as finding `CUF2002` instead of raising.

## Optional extras

The Arrow, polars, pandas and Parquet extras only receive data pycuf has already parsed and
validated; they never see the XML. Keep them up to date like any other dependency.

## Personal and confidential data

Estimates contain client names and addresses and commercially sensitive prices. Never attach a
real CUF file to an issue or pull request; see
[CONTRIBUTING.md](https://github.com/SpireflyHQ/pycuf/blob/main/CONTRIBUTING.md#contributing-anonymised-samples).
