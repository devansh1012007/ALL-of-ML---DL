# Security policy

## Supported versions

Only the `main` branch is supported until the first release. After the first release, the latest
minor version is supported (see `docs/cicd/RELEASING.md`).

## Reporting a vulnerability

Please do not open a public issue for a security problem.

Report it privately through GitHub: the **Security** tab of this repository, then **Report a
vulnerability**. This is enabled by the repository owner (SPEC SET-7). If it is not enabled yet,
contact the repository owner through GitHub (`@devansh1012007`) without describing the problem in
public.

Include:

- what you found and where (file, endpoint, or workflow);
- the steps to reproduce it, with the version or commit;
- what an attacker could do with it.

There is no formal response time. The maintainer will acknowledge a report when they can, and will
say whether it is accepted.

## Secrets

If you find a credential in the repository or its history, report it the same way. Treat the
credential as compromised and rotate it; do not rely on removing it from the history.
