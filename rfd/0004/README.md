---
authors: "<shalom@shalomormsby.com>"
state: discussion
discussion:
labels: [inbound, agent]
---

# RFD 0004: The Steward

## Background

Inbound volume is at a generational high and rising. Cold outreach is increasingly agent-generated, which means the defense has to be agent-shaped too. ContactGraph is uniquely positioned because it already knows *who actually matters* to the user — strong ties, weak ties, dormant ties, never-mets. No spam filter has that context; we do.

The Vault (RFD-0002) gives the user a place to write standing rules. The Steward is what makes those rules act in the world — the agent that stands at the front door of their relational life and triages inbound against the user's own preferences.

The audience is anyone whose inbox has stopped serving them: founders, execs, journalists, recruiters, BD leaders drowning in cold outreach; privacy-protective users who hate unsolicited contact; job seekers who need to surface real opportunities from recruiter noise; anyone with hundreds of unread messages they've rationalized away.

Initially the Steward covers Gmail only. The full vision spans every channel, but cross-channel mediation depends on Full-Signal Ingestion (RFD-0003) and inbound from other CG users depends on the Handshake Protocol (RFD-0005).

## Proposal

The user connects ContactGraph and grants `gmail.modify` scope (label-only; no send initially). The Steward watches new inbound mail and labels it against the user's graph + standing rules:

- `cg:strong-tie` — top 50 people, surfaces immediately
- `cg:owed-reply` — you opened the last thread and never wrote back
- `cg:reactivation` — old close tie reaching out after long silence
- `cg:cold` — sender not in your graph; held for digest
- `cg:recruiter`, `cg:vendor-pitch`, `cg:newsletter` — category-tagged from graph + content
- `cg:muted` — sender or pattern matches a standing mute rule

Each labeled message carries a one-line **explanation** the user can read on hover: *"Surfaced because: top-20 tie, no contact in 14 months."*

The agent delivers a **daily/weekly Steward digest**: *"3 strong-tie inbounds, 1 reactivation, 12 cold pings held, 4 recruiters auto-muted per your rules."*

From any message or person the user can issue a one-shot rule to the agent — *"mute this sender forever"*, *"always surface anyone from Anthropic"*, *"hold all recruiter mail unless the role mentions climate"* — and the rule is written to the Vault.

### Rule model

Rules live in the Vault as a small, human-readable structure:

```yaml
- when: sender_in_graph(tie_strength >= 8)
  then: surface_immediately
- when: sender_category == "recruiter" and not role.mentions("climate")
  then: hold_for_digest
- when: sender == "spammer@example.com"
  then: mute_forever
```

The agent can read, write, and explain rules. Conflicts are resolved by specificity, then by user-set priority.

### Proposed sovereignty primitives

- **All rules live in the Vault** — user-owned, exportable, editable, deletable
- **Every action is explained** — every label includes its reasoning; no black-box triage
- **Fully reversible** — any label can be undone; rules have an undo history
- **No outbound writes initially** — reads and labels only; sending requires explicit per-message user approval
- **Audit log** — every Steward decision is recorded and viewable in the Vault

### What we're proposing to build first

`gmail.modify` integration with label management and a daily watch job. A triage classifier (graph context + LLM) producing the core label set. The standing rules engine with rules stored in the Vault. The Steward digest delivered via the agent. One-shot rule creation from inside a conversation with the agent. Explanations on every label, an audit log, and full undo.

### What we're explicitly punting

- Auto-reply / auto-decline (drafts, never sends) — deferred until the labeling discipline is proven
- Cross-channel triage (SMS, WhatsApp, Signal, LinkedIn DMs) — depends on RFD-0003
- Agent-to-agent inbound — depends on RFD-0005
- A canonical `you@contactgraph.ai` forwarding address — much later
- Group / team Steward (shared rules for a company inbox)

## Open questions

- **`gmail.modify` is a much bigger trust ask than `gmail.readonly`.** A wrongly labeled VC intro is a deal lost. Conservative defaults, clear undo, and an "explain this decision" affordance on every label aren't enough on their own. Should we ship with a 7-day shadow mode where labels are computed but not applied?
- **The "missed dream job" problem.** Muting recruiters can hide a perfect role. Rules need `unless` clauses; the harder question is how to surface the muted bucket to the user so they can still see what's been hidden without losing the value of the mute.
- **Rule sprawl.** Users will not write 50 rules. Should the Steward *propose* rules from observed behavior — *"You've ignored 8 messages from this domain — want to mute it?"* And how aggressive should those proposals be?
- **Adversarial inbound.** Sophisticated senders will A/B their way past category labels. Graph-context features (sender's distance from the user) are harder to spoof than content. Are they enough?
- **Latency.** Labels need to apply within ~30 seconds of receipt to feel useful. Job architecture must support near-realtime, not batched-hourly.
- **Scope of "Steward."** Initially Gmail-only; the full vision spans every channel. Worth being honest in the UI that this is the first door, not the only one.

## Decision

(Filled in when this RFD is merged.)
