# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| v1.2 (current) | Yes — security fixes backported |
| v1.1 (internal pre-release) | No |

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Email: **security@silkbridge.io**

You will receive an acknowledgement within 48 hours. We aim to release a fix
or mitigation within 14 days for critical issues and 90 days for others.

If you require encrypted communication, request our PGP public key via the
email above.

## Scope

This policy covers:

- The SBP wire protocol as described in [`spec/SPEC.md`](spec/SPEC.md).
- The reference Python server in [`reference/server-python/`](reference/server-python/).
- The reference TypeScript client in [`reference/client-typescript/`](reference/client-typescript/).
- The conformance test suite in [`conformance/`](conformance/).

Third-party implementations of SBP are not in scope. Contact their respective
maintainers directly.

## Known security considerations

The following are documented in `spec/SPEC.md §12` (Security Considerations):

- **Roaming Token storage**: tokens are compact JWTs signed with HS256. Keep
  the signing secret (`jwt_secret`) out of your codebase and rotate it
  periodically.
- **Snapshot encryption at rest**: the spec does not mandate encryption, but
  implementations that store personal data in snapshots SHOULD encrypt them at
  rest. The reference server stores snapshots in plaintext (appropriate for
  development; not production).
- **Replay attacks**: roaming tokens are single-use by default
  (`allow_reuse: false`). Implementers MUST track consumed tokens.
- **Surface impersonation**: the `session_token` in the `ATTACH_SESSION` frame
  is the only surface authentication mechanism in v1.2. Implementations
  operating in adversarial environments SHOULD add additional binding (e.g. TLS
  client certificates or mTLS between the surface and the gateway).
- **Surface-tool authorization**: in v1.2 a surface may declare any tool name
  in `mcp_tools`. Implementations SHOULD validate declared tools against an
  allowlist before invoking them.

## Responsible disclosure

We follow coordinated disclosure. We will credit the reporter in the patch
release notes unless they request anonymity.
