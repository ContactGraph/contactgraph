---
authors: "<shalom@shalomormsby.com>"
state: discussion
discussion:
labels: [ingestion, sovereignty]
---

# RFD 0003: Full-Signal Ingestion

## Background

The manifesto says *"your email and calendar already know who you actually talk to."* That undersells the project. For most people under 50, the conversations that matter most — with family, close friends, neighbors, co-founders, group chats — have left email entirely. They live in iMessage, WhatsApp, and Signal. A graph that only sees email reflects work life and misses everyone else.

The architectural move that keeps this honest with the manifesto: messaging ingestion runs **on the user's own device**. The raw chat history never leaves. A small local client extracts derived signal — people, edges, tie strength, last-genuine-contact, classifications — and sends only that to ContactGraph. Sovereignty becomes architectural rather than policy.

The audience extends well beyond the operators and founders the email-only graph reaches. It includes anyone whose real network lives off email (friends, family, neighborhoods, group chats, founders' circles), operators who do business in WhatsApp/Signal (international founders, journalists, investors with global LPs), and privacy-skeptical users for whom *"we never read your messages"* must be verifiable, not just promised.

Full-Signal can ship without the Vault (RFD-0002), but the messaging-derived nodes need to be groomable somewhere; cleaner to land Vault first.

## Proposal

After Gmail sync, the agent says: *"Want me to find the rest of your network? Install the ContactGraph Desktop client — it reads your messages on your Mac and only sends the derived graph to ContactGraph."*

The user installs the Mac client (Tauri with a Rust core, open-source, signed binary). On first run the client asks for access to:

- **iMessage** — local read of `~/Library/Messages/chat.db`
- **Chat exports** — drop-in folder for WhatsApp `.zip`, Signal `.json`, Telegram `.json`

The client processes everything locally: resolves message participants against the existing graph, extracts edges, tie strength, last-genuine-contact, relationship hints. It then surfaces a **"Here's what I learned"** preview the user reviews before any upload. User approves, and only the derived graph layer (nodes, edges, signals — no message content) uploads to ContactGraph.

The client runs in the background, refreshing the local graph as new messages arrive. A menu-bar UI shows last sync, disk usage, and a one-click *"burn local cache"*.

### Source roadmap

| Channel | Initial path | Where processing happens |
|---|---|---|
| **iMessage** | Local read of `chat.db` on the user's Mac | Local |
| **WhatsApp** | User-initiated chat export (`.zip`) dropped into the client | Local |
| **Signal** | Signal Desktop export (`.json`) | Local |
| **Telegram** | Telegram Desktop export (`.json`) | Local |
| **Slack DMs** | OAuth API per workspace | Cloud (already SaaS) |
| **Meeting transcripts** (Granola, Otter, Krisp) | OAuth API | Cloud (already SaaS) |
| **Android Messages / RCS** | Android client (later) | Local |
| **Voice memos** | Desktop import + on-device transcription (later) | Local |

### Proposed sovereignty primitives

- **Raw content never leaves the device** for any locally-ingested source
- **Pre-upload review** — user sees the derived signal before it leaves the device, every time
- **Open-source client** — the user (or a third party) can audit what the client extracts and sends
- **One-click burn** — wipes the local cache and re-pulls if the user wants to start fresh
- **Source isolation** — a user can revoke any one channel without affecting the rest
- **Reproducibility** — the derived signal upload is deterministic from the local data; the user can re-run extraction at any time

### What we're proposing to build first

A macOS Desktop client (Tauri, code-signed, auto-updating). An iMessage local reader. A generic chat-export importer for WhatsApp, Signal, and Telegram. Local LLM-assisted entity resolution and classification (small model on-device; fall back to a user-supplied OpenAI key for heavier work). A signed-upload protocol for derived graph deltas. The pre-upload review UI. Background refresh with a menu-bar status surface. The burn-local-data action.

### What we're explicitly punting

- iOS / Android clients — Android needs an SMS/RCS reader; iOS is sandboxed and hard
- Continuous WhatsApp/Signal sync (vs. user-triggered exports) — requires either WhatsApp Multi-Device protocol work or local-cache reading that risks ToS conflict
- Voice memo transcription
- Cross-device merge (your iMessage on Mac + your phone-only conversations)
- Cloud-side fallback for users without a Mac — explicitly **not** doing this; it would break the local-first promise

## Open questions

- **Platform ToS edges.** Reading `chat.db` from the user's own Mac is technically permitted but Apple has been known to harden access. WhatsApp's local cache is explicitly forbidden to read; we only support user-initiated export. Legal review per source.
- **Trust ask is higher than Gmail.** *"Read all my messages"* feels heavier than *"read email metadata."* Local-only architecture is the headline; pre-upload review is the proof; open-source client is the audit trail. Is that enough?
- **Desktop client is a new product surface.** It's the first thing CG ships that isn't a server. Operationally non-trivial: code signing, auto-update, crash reporting, support.
- **Battery / disk usage.** Continuous local watcher must be cheap. Default to nightly refresh with a manual *"sync now"*?
- **Phone-only users.** A growing percentage of users (especially internationally) don't have a Mac. Mobile clients are post-initial; leaving them temporarily unaddressed is a real cost.
- **Entity resolution across channels.** *Sarah* in iMessage, `sarah.chen@stripe.com` in Gmail, `+1-415-...` in WhatsApp must resolve to one person. The existing entity-resolution work has to handle phone numbers and chat handles, not just emails.
- **Group chat noise.** WhatsApp groups with 200 people mostly add noise, not signal. Down-weight or skip large groups by default?

## Decision

(Filled in when this RFD is merged.)
