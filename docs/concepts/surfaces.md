---
title: "Concept: Surfaces"
layout: default
---

# Surfaces

A **surface** is any client that attaches to an SBP session via WebSocket. It
represents a physical device or rendering context: a phone, a watch, a browser,
a voice assistant, an IoT display.

The Surface capability (L4) lets surfaces declare their capabilities to the
gateway at attach time. The gateway MAY use this information to adapt its output.
No specific adaptation is mandated — the protocol defines the declaration
mechanism, not the rendering logic.

---

## SurfaceContext

When a surface sends `ATTACH_SESSION`, it includes a `surface_context` object:

```json
{
  "type": "ATTACH_SESSION",
  "session_id": "...",
  "session_token": "...",
  "surface_context": {
    "device_type":       "mobile",
    "max_output_tokens": 300,
    "ui_capabilities":   ["markdown", "streaming"],
    "locale":            "en-US",
    "surface_id":        "device-fingerprint-uuid",
    "mcp_tools":         ["camera", "gps"]
  }
}
```

All fields are OPTIONAL. Servers MUST tolerate absent or unknown values.

---

## Well-known device types

| `device_type` | Typical constraints |
|---|---|
| `"mobile"` | Medium screen, touch input, may have camera/GPS |
| `"desktop"` | Large screen, rich UI, keyboard/mouse |
| `"iot"` | Very small screen (e.g. watch), or no screen; severely limited output length |
| `"browser"` | Web browser on any device class |
| `"voice"` | No screen; output must be audio-friendly prose |
| `"unknown"` | No adaptation required; send default output |

Servers MUST accept any string value for forward-compatibility.

---

## UI capabilities

| Capability | What it means for the gateway |
|---|---|
| `"markdown"` | Safe to use `**bold**`, lists, headings |
| `"tables"` | Safe to render tabular data |
| `"images"` | Safe to include image URLs or base64 |
| `"audio"` | Prefer prose over structured data; avoid lists |
| `"streaming"` | Surface prefers `TURN_CHUNK` over complete `TETHER_TURN` |

---

## What the protocol specifies vs what implementations do

SBP specifies the **declaration mechanism** (the `SurfaceContext` schema and
the fields within it). It does **not** specify what the gateway does with that
information. Adaptation is implementation territory:

- Shortening a 4,000-token report to 2 sentences for a watch → implementation.
- Converting prose to audio for AirPods → implementation.
- Respecting `max_output_tokens` as an LLM generation limit → implementation.

This separation protects commercial differentiation. The protocol enables
interoperability; the implementation delivers quality. SilkBridge's Contextual
Translation Pipeline is one implementation of surface adaptation — others can
build their own.

---

## `surface_id` — stable device fingerprint

The `surface_id` is an optional stable identifier for the physical device. It
allows a gateway to:
- Recognize that the same device is reconnecting after a disconnect.
- Associate session history with a specific device.
- Enforce per-device access policies (implementation-defined).

The format is not specified — implementations may use UUIDs, device serial
numbers, or any stable string.

---

## Normative source

- **SPEC.md §9** — Surface Negotiation
- **SPEC.md §9.1** — SurfaceContext schema
- **SPEC.md §9.2** — Well-known device types
- **SPEC.md §9.3** — Well-known UI capabilities
- **SPEC.md §9.4** — Server adaptation guidance
- **spec/schemas/surface-context.schema.json**
- **spec/examples/07-l4-attach-with-surface.json**
