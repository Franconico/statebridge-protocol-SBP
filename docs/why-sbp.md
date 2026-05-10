---
title: Why SBP — The Northbound Protocol
layout: default
---

# Why SBP — The Northbound Protocol for AI Agents

> *MCP gives the agent hands. SBP gives the agent a soul that persists across
> space and time.*

---

## The statelessness problem

Every major AI system today has the same architectural flaw: the agent dies
when the connection dies.

OpenAI's API is stateless. Anthropic's API is stateless. Google's API is
stateless. Every call receives a full context window and returns a response —
then everything is forgotten. This is perfectly appropriate for request-response
workloads like answering a search query.

It is catastrophically wrong for the way humans actually use AI agents.

A user asks their agent to research and book a 10-day trip to Japan. The
research takes 40 minutes. The user's phone goes into their bag. The WebSocket
closes. The agent's work is gone. The user opens their laptop. The agent has no
memory of what it was doing. Every agent platform today scrambles to work around
this — and every one invents a private, incompatible, non-portable solution.

**SBP is the open standard that solves this, once, for everyone.**

---

## Two protocols, two directions

To understand why SBP fills a gap that MCP cannot, you need to understand the
architecture of an AI agent system as two separate data flows.

### Southbound: MCP

MCP (Model Context Protocol) handles the flow from agent *down* to the machine
world — how the agent talks to databases, APIs, file systems, web search.

MCP is lightweight and stateless by design. An MCP server is often 50 lines of
code. It defines a standardized JSON-RPC format for tool calls. It works
beautifully for its purpose.

### Northbound: SBP

SBP handles the flow from agent *up* to the human world — how the agent
communicates its output to whatever device the user is currently holding, and
how it keeps working when that device goes offline.

SBP is inherently stateful. It must maintain a queue of turns across
disconnections (the **Tether**). It must serialize full session state into a
portable token (the **Roaming Token**). It must translate agent output to match
the capabilities of the receiving device (the **Surface**). None of this can be
done statelessly.

```
                  ┌───────────────────────────────────────┐
                  │  Apple Watch · iPhone · Browser · AirPods │
                  └────────────────────┬──────────────────┘
                                       │
                           ⇅  SBP (Northbound)
                           Tether · Roaming · Surfaces
                                       │
                  ┌────────────────────┴──────────────────┐
                  │           Agent Gateway               │
                  │   (LLM-agnostic · Server-agnostic)    │
                  └────────────────────┬──────────────────┘
                                       │
                           ⇅  MCP (Southbound)
                           Tools · Databases · APIs
                                       │
                  ┌────────────────────┴──────────────────┐
                  │  Databases · File Systems · Web · APIs │
                  └───────────────────────────────────────┘
```

MCP gives agents hands to touch the machine world.
SBP gives agents a soul that persists across space and time.

---

## Model-agnostic and server-agnostic — by design

This is the most important architectural decision in SBP and it is worth stating
plainly:

**SBP places zero constraints on which LLM you use and zero constraints on
which infrastructure you run.**

### LLM-agnostic

The only LLM-related field in the entire SBP protocol is the `model` string in
the request envelope — and it accepts any OpenAI-compatible model identifier.

```json
{
  "model": "gpt-4o",
  "sbp": { "checkpoint_every": 1 }
}
```

Change `"gpt-4o"` to `"claude-opus-4-7"`, `"llama-4-scout"`, `"deepseek-v3"`,
or `"my-fine-tuned-model"`. The SBP session survives the change. The surface
sees no difference. The user notices no interruption.

This matters strategically: if Anthropic were to build a state-roaming protocol,
there is a very high risk they would design it to lock users into the Claude
ecosystem. SBP is model-agnostic. A developer can use SBP to roam an agent
powered by an open-source DeepSeek model, a local Llama 4, or OpenAI — and
none of these require any relationship with Anthropic's backend.

### Server-agnostic

SBP defines backend requirements as abstract interfaces:

```
SessionStore     — create, get, update, delete sessions
TetherQueue      — enqueue, drain, clear buffered turns
SnapshotStore    — write, retrieve state snapshots
RoamingTokenStore — record, consume, inspect roaming tokens
```

These are contracts, not implementations. You may fulfill them with:

- PostgreSQL or DynamoDB or SQLite
- Redis or Kafka or Temporal or an in-memory queue
- Any HMAC library for token signing

An air-gapped hospital running SBP on a local server with a SQLite backend and
a Llama 3 model is a first-class, fully-conformant SBP deployment. No calls to
any third-party service are required.

---

## Why MCP won't absorb SBP

MCP's creators have been asked whether MCP will eventually handle agent state.
The answer is no — and the architectural reason is clear.

MCP was intentionally designed to be stateless and lightweight. You can run an
MCP server in 50 lines of Python, with no database and no heavy infrastructure.
The moment MCP had to manage WebSocket reconnect queues, device screen sizes,
and long-running memory state, it would become a completely different protocol.
MCP's value is in its simplicity and ubiquity.

SBP requires heavy infrastructure: a durable execution engine (or durable queue),
a database for sessions and snapshots, and pub/sub semantics for WebSocket
routing across replicas. Anthropic does not want to build or host a Temporal-like
state-management infrastructure for every developer in the world. They want to
sell LLM tokens.

The separation is clean:
- **MCP**: standard format for tool calls. Zero state. Zero infrastructure.
- **SBP**: standard format for agent persistence. Stateful. Infrastructure required.

---

## The "Bring Your Own Model" moat

The open-source AI community will naturally gravitate toward SBP because it
guarantees they are not locked into Anthropic's backend to keep their agents
alive.

The enterprise AI community will gravitate toward SBP because it gives them
vendor diversity: they can switch LLMs, switch clouds, or switch agent
frameworks without losing session continuity.

The complementary positioning — explicitly praising MCP, showing the two
protocols in the same diagram, making SBP MCP-native in the MCP Bridge
capability — turns potential competitors into evangelists. If SBP is the
best way to transport MCP payloads to edge devices, the MCP community will
promote SBP.

---

## SBP vs MCP — at a glance

|                   | **MCP** (Southbound)                | **SBP** (Northbound)                       |
|-------------------|-------------------------------------|--------------------------------------------|
| Connects agent to | Tools, databases, APIs              | Humans, devices, surfaces                  |
| Stateful?         | No (per-call)                       | Yes — sessions survive disconnects         |
| Scope             | "Give the agent hands"              | "Give the agent a soul that persists"      |
| Typical transport | stdio, HTTP+SSE                     | HTTP + WebSocket                           |
| Runtime weight    | Lightweight, ~50 LoC               | Stateful, durable backend required         |
| LLM-agnostic?     | Yes                                 | Yes — any OpenAI-compatible model          |
| Server-agnostic?  | Yes                                 | Yes — swap backend implementations freely  |
| Created by        | Anthropic                           | The State Bridge community (open standard) |

---

## The vision: every agent has a persistent identity

The long-arc vision for SBP is simple:

Every AI agent should have a persistent identity that transcends the device it's
running on, the LLM that powers it, and the infrastructure that hosts it. Just
as your phone number follows you when you switch carriers, your agent's context
should follow you when you switch devices, models, or providers.

SBP is the protocol that makes that possible — and it belongs to the community,
not to any single company.

[Read the spec →](../spec/SPEC.md) · [Get started in 5 minutes →](getting-started.md)
