# Gateway Federation — The Independent Cities Model

## The Silk Road analogy

The Silk Road was never centralized. There was no routing server. No single merchant made every journey. No single city held every trade secret.

Instead, there were **independent cities** — Samarkand, Kashgar, Constantinople — each a hub in its own right. Merchants carried **portable letters of credit** from city to city. Any city that recognised the letter could honour the trade. You didn't need to return to the origin; you simply arrived at the next city with your letter, and the journey continued.

SBP federation works the same way.

---

## The Problem with a Single Gateway

A single central gateway is a single point of failure for AI agent state. It creates:

- **Geographic latency** — all sessions must route through one region
- **Vendor lock-in** — you can't move your agents to a cheaper or faster provider
- **Availability risk** — gateway downtime means agent downtime
- **Trust concentration** — one entity holds all session state

SBP's answer is not to eliminate gateways — it's to make them **interoperable and independent**.

---

## How Federation Works

Each SBP L6 gateway:

1. **Publishes a well-known manifest** at `GET /.well-known/sbp` — advertising its identity, public key, and supported endpoints
2. **Stores bundles by CID** — every session export is indexed by its content address (`bundle_cid = sha256(bundle_json)`)
3. **Resolves foreign bundles** — if a surface connects and the session isn't local, the gateway queries its peer list for `GET /v1/sbp/bundles/{bundle_cid}` and imports it transparently
4. **Verifies integrity** — the bundle CID is verified before import; a tampered bundle will always fail

From the surface's perspective, it's invisible. The surface connects to the nearest gateway. The session appears. The journey continues.

---

## The Three-Gateway Architecture

```
┌──────────────────────┐     ┌──────────────────────┐     ┌──────────────────────┐
│   Gateway A (NYC)    │     │   Gateway B (FRA)     │     │   Gateway C (SIN)    │
│                      │     │                      │     │                      │
│  Session X           │     │  (no session X)      │     │  (no session X)      │
│  bundle_cid: abc123  │     │                      │     │                      │
└──────────────────────┘     └──────────────────────┘     └──────────────────────┘
          │                            │
          │  User flies to Frankfurt   │
          │  connects to Gateway B     │
          │                            │
          │                  Surface → ATTACH_SESSION
          │                  Gateway B: no session X locally
          │                  Gateway B: GET /v1/sbp/bundles/abc123 → Gateway A
          │                  Gateway A: returns bundle
          │                  Gateway B: verify bundle_cid, import
          │                  Gateway B → SESSION_ATTACHED
          │                            │
                             Session continues on Gateway B
                             with full context, no data loss
```

---

## Content Addressing: Why bundle_cid Matters

The `bundle_cid` is the SHA-256 of the bundle's deterministic JSON serialisation. This means:

- **Any two gateways that store the same bundle will compute the same CID** — no central registry needed
- **The CID is the identity** — you can refer to a session by its bundle CID across any gateway
- **Integrity is implicit** — if the bytes don't match the CID, the bundle is rejected. Tampering is detectable without a certificate authority.

This is the same property that makes IPFS, Git content addresses, and Docker layer digests trustworthy without centralised coordination.

---

## Peer Discovery Options

Gateways discover peers by any of the following methods (implementation choice):

### 1. Static peer list

```yaml
# sbp-server.yaml
federation:
  peers:
    - https://sbp.example-nyc.com
    - https://sbp.example-fra.com
    - https://sbp.example-sin.com
```

Simple. Works for private networks and enterprise deployments.

### 2. DNS SRV

```
_sbp._tcp.example.com IN SRV 10 10 443 sbp-nyc.example.com
_sbp._tcp.example.com IN SRV 10 10 443 sbp-fra.example.com
```

Standard DNS infrastructure. No config changes when peers are added; just update DNS.

### 3. Tracker query

A **Tracker** is a lightweight node that does not host any sessions. It maintains a directory of `{ bundle_cid → list of Gateway URLs }` records that Gateways submit when they export a bundle. A Tracker answers "who has this bundle?" — and nothing else.

Trackers exist for scale. In a network with hundreds of independent Gateways, a static peer list becomes impractical. A Tracker is the indexing primitive that solves this without introducing a central authority over session content. A Tracker never sees session bytes; it only stores references and signatures.

Anyone can run a Tracker. Trackers can themselves be federated (Tracker A queries Tracker B if it doesn't know a CID). A Tracker is the closest SBP gets to a "central server" — but it holds no power over session content, can be replaced trivially, and is optional even at L6.

SBP deliberately uses signed manifests at well-known HTTP endpoints rather than a DHT for discovery. DHTs (Kademlia, libp2p, etc.) are technically elegant but bring bootstrap, NAT-traversal, and eclipse-attack complexity that hurts adoption. A Tracker is boring infrastructure: an HTTP service with an index. That is the right tradeoff for v1.2.

---

## Security in Federation

Federation does NOT require trusting peers blindly:

- **Bundle CID verification**: every import verifies the content matches the CID. A malicious peer cannot inject content without detection.
- **Federation tokens**: bundle resolution (`GET /v1/sbp/bundles/{cid}`) requires a signed federation JWT. Unknown requesters are rejected.
- **Mutual TLS** (optional): gateways MAY use mTLS for peer-to-peer bundle resolution instead of JWT.
- **Session ownership**: importing a bundle creates a new session on the importing gateway. The original session on the exporting gateway is not transferred — it can be suspended or retained per policy.

---

## The Commercial Model Under Federation

Federation makes the **protocol** decentralised. It does not eliminate the **service** value of SilkBridge Cloud:

| What federation gives you | What SilkBridge Cloud adds |
|--------------------------|---------------------------|
| Open protocol, any gateway | Zero-ops managed gateways |
| Self-hostable reference server | Temporal-backed 30-day Tether |
| L5 compliance with SQLite | Translation Pipeline, HITL, Observability |
| Bundle portability | SLA-backed availability |
| Community trust (open spec) | Enterprise SSO, audit logs, Sovereign VPC |

You can run your own L6 gateway and still use SilkBridge Cloud for the sessions where you need enterprise durability. They interoperate.

---

## Getting Started with Federation

Federation is an optional L6 capability. Most deployments start at L5 (full surface negotiation and MCP bridge) without federation.

To enable federation in the reference server:

```bash
sbp-server start --federation --peers https://peer1.example.com,https://peer2.example.com
```

Or via config:

```yaml
federation:
  enabled: true
  gateway_id: "my-gateway-nyc"
  peers: [...]
  public_key_path: /etc/sbp/public.pem
  private_key_path: /etc/sbp/private.pem
```

*Normative source: SPEC.md §13*

---

*SBP Federation Concepts — v1.2 — © 2026 Silkbridge, Inc. — Apache-2.0*
