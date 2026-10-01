# Security policy

## Supported versions

pycuf is in its `0.x` series. Security fixes are made for the **latest released version** only;
please upgrade before reporting.

| Version          | Supported |
| ---------------- | --------- |
| latest `0.x`     | yes       |
| older releases   | no        |

## Reporting a vulnerability

**Please do not report security problems in public issues, discussions or pull requests.**

Report privately through either channel:

1. **GitHub private vulnerability reporting** (preferred):
   [Report a vulnerability](https://github.com/SpireflyHQ/pycuf/security/advisories/new)
   (repository → *Security* → *Advisories* → *Report a vulnerability*).
2. **E-mail** to [ben@spirefly.com](mailto:ben@spirefly.com) with the subject
   `pycuf security`.

Include the pycuf version, Python version and operating system, a description of the impact, and
a minimal reproducer. A reproducer must be a **synthetic** file or snippet. Never send a real
estimate, not even privately.

pycuf is maintained by one person in their spare time, so these are targets, not guarantees:

- acknowledgement within **5 working days**;
- an assessment and a plan within **14 days**;
- a fix released and a GitHub Security Advisory (with CVE where appropriate) published in
  coordination with you. You will be credited unless you prefer otherwise.

## Threat model and hardening

CUF files are untrusted input. pycuf refuses DTDs and entity declarations (no billion laughs, no
XXE), never opens network connections or files beyond the ones you pass, limits input size,
nesting depth and attribute size, and has no parser "recover" mode. The full threat model is in
the [security documentation](https://spireflyhq.github.io/pycuf/security/).

Problems in the contents of a file (wrong totals, missing elements, …) are data quality problems,
not security issues. Report them as normal issues, without real data.

## Supply chain

Releases are built in GitHub Actions and published to PyPI with Trusted Publishing; each
distribution carries a PEP 740 attestation linking it to the workflow run that built it. The
wheel and sdist attached to each GitHub release are also signed with Sigstore (`*.sigstore.json`);
verify one with

```bash
python -m pip install sigstore
python -m sigstore verify github pycuf-X.Y.Z-py3-none-any.whl --repository SpireflyHQ/pycuf
```

All workflow actions are pinned to full commit SHAs and checked with zizmor; CodeQL analyses the
Python code and the workflows.
