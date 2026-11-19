# Security policy

PhyRand is a student research prototype. It has not been audited and is not
intended to protect real secrets. Please read
[docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) before relying on it for anything.

## Reporting a vulnerability

Please do not open a public issue for a security problem.

* Preferred: GitHub **Security -> Report a vulnerability** (private advisory)
  on this repository.
* Alternatively, contact the maintainer through the profile at
  <https://github.com/Kavin-Re>.

Include the affected file or endpoint, a description of the impact and steps
to reproduce. This is a one-person project maintained on a best-effort basis;
you can expect an acknowledgement, but no response time is guaranteed.

## Supported versions

Only the `main` branch is maintained.

## Security model in brief

| Topic | Summary |
| :--- | :--- |
| Role of the server | Key escrow. It generates and stores every file key and **can decrypt** any file whose key it holds. It is not zero-knowledge. |
| Key generation | `HKDF-SHA256(health-tested device bytes || os.urandom)`. A failed or malicious device cannot make keys weaker than OS-generated keys. |
| Hardware failure | Fail closed by default: no healthy device, no key (HTTP 503). OS-only fallback is opt-in and labelled. |
| Health tests | Repetition Count and Adaptive Proportion tests in the style of NIST SP 800-90B 4.4, applied to debiased output. Not a compliant implementation. |
| Entropy claims | None beyond "at least as strong as the OS CSPRNG". The noise source is unvalidated. |
| File encryption | Fernet: AES-128-CBC + HMAC-SHA256, encrypt-then-MAC, on the client. |
| Authentication | One master bearer token (minimum 32 characters, enforced at start-up) and per-file release tokens. Constant-time comparison, failed-attempt rate limiting. |
| Transport | No built-in TLS. Loopback by default; use an HTTPS reverse proxy for anything else. |
| Storage | Keys are stored in plaintext JSON with owner-only permissions. Protect and back up the host accordingly. |

## Operating it safely

* Generate the master token with `phyrand token`; keep `.env` out of version
  control (it is git-ignored).
* Do not expose the API through a public tunnel or bind it to `0.0.0.0`
  without TLS in front.
* Give recipients a file ID and release token, never the master token.
* Run a single server process per vault file.
* Revoke keys you no longer need; revocation deletes the server's copy.

## If you used an earlier revision

Earlier revisions shipped a default master token of `password`, returned all
keys from `/vault/list`, and one script contained a public tunnel URL. If you
ran the server reachable from a network with those defaults, assume the keys
in that vault were exposed: revoke them, re-encrypt the files with new keys
and set a new master token.
