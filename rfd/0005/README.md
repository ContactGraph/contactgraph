---
authors: "<shalom@shalomormsby.com>"
state: discussion
discussion:
labels: [protocol, interop]
---

# RFD 0005: The Handshake Protocol

## Background

Phase 2 of the agent-native-graph requirements explicitly calls for consented cross-user queries. The path of least resistance is to build that as an internal CG feature — a privileged API between two CG users. We should resist that and ship it as a **protocol** from the start: a published spec, signed messages, and a wire format that any future personal-graph product could implement.

Three forces make now the right moment:

1. **The infrastructure is finally close.** The Vault (RFD-0002) gives the storage; the Steward (RFD-0004) gives the inbound mediator; MCP gives the agent-to-tool layer. Handshake is the missing piece — the agent-to-agent layer for interpersonal questions.
2. **LinkedIn's structural moat is rotting.** Cold outreach via LinkedIn now has worse signal-to-noise than email. The open warm-intro layer that replaces it has to be a protocol, not a product.
3. **MCP set the precedent.** A clean, well-specified protocol that solved the tool-to-agent connection problem went from "interesting idea" to "industry default" in 18 months. The same shape of opportunity exists at the interpersonal layer.

The audience starts with ContactGraph users who share overlapping graphs (colleagues at the same company, founders in the same cohort, friends of friends), then extends to operators looking for warm paths, recruiters and BD ops doing intro requests at scale (and the gatekeepers fielding them), and — eventually — any product hosting a personal graph that wants interop with CG: personal CRMs, communities, alumni networks.

## Proposal

The user never sees the protocol. They see the agent conversation.

**Requester side:**

> *"Who do I know who could introduce me to Charlie Patel at Stripe?"*
>
> Agent (via Handshake): *"Three people in your graph have Charlie in theirs. The strongest tie is Maria Lopez. Want me to ask Maria's agent if she'd make an intro?"*

The agent issues a signed `request_introduction` to Maria's CG. Maria's Steward triages it against her standing rules and surfaces it in her digest, or immediately if she has standing-allow set for the requester.

**Responder side:**

> Steward digest: *"Alex Chen's agent asked if you'd introduce them to Charlie Patel. Alex says: 'climate-fintech founder, raising seed.' Decline / Hold / Accept / Reply."*

Maria's decision (and her optional note) is signed by her CG, returned to Alex's CG, and logged in both Vaults.

### Canonical operations

| Operation | Semantics | Disclosure tier |
|---|---|---|
| `existence_query` | *"Is X in your graph?"* | Existence-only — yes/no, nothing else |
| `attribute_query` | *"Does anyone in your graph match {filter}?"* | Counts and existence; no names |
| `identity_query` | *"Tell me about X in your graph."* | Name + role + tie-strength bucket |
| `intro_request` | *"Would you introduce me to X?"* | Triggers a draft, gated by approval |
| `claim_verification` | *"Can you confirm Y worked at Z 2014–2017?"* | Boolean + optional signed counter-claim |

Each operation carries: requester identity, principal identity, target, requested disclosure tier, optional context, and an audit ID. Each response carries: action, optional note, signature, audit ID.

### Disclosure tiers

Every response specifies the tier at which it's answered:

1. **Existence** — yes/no, no metadata
2. **Attribute** — categories or buckets, no names
3. **Identity** — name + current role + tie-strength bucket
4. **Introduction** — a drafted intro message routed via the responder
5. **Contact-share** — actual email/phone, requires explicit approval

The responder always answers at *or below* the requested tier. Standing rules let the responder pre-authorize specific tiers for specific requesters or categories.

### Wire format

- JSON-LD message with a public JSON Schema
- Signed with the sender's CG identity key (JWS)
- Transported over HTTPS to the receiver's CG endpoint (`/handshake/inbox`)
- Delivered to the receiver's Steward for triage

A reference implementation in TypeScript and Python ships with the spec.

### Proposed sovereignty primitives

- **Every exchange is signed** by both parties' CG identity keys
- **Both parties get a copy** logged in their respective Vaults — no hidden queries
- **Steward mediates every inbound handshake** against the receiver's standing rules
- **Consent at every tier** — the responder chooses the tier at which to answer (or to ignore)
- **Per-requester budgets** to prevent probing / inference attacks
- **Public spec** — the protocol is published; CG operates one implementation, not the only one

### What we're proposing to build first

A versioned protocol spec (Markdown + JSON Schema + reference messages). A reference implementation in CG — server-side message routing, signing, and verification. The five canonical operations and the five disclosure tiers. Steward integration on the inbound side. Vault logging on both sides. Standing-rule support (e.g., *"always answer existence_query from my company colleagues"*). Per-requester rate limits with probing detection. A first end-user UX for cross-graph queries between two CG users. Reference SDKs in TypeScript and Python.

### What we're explicitly punting

- **Third-party implementations.** Ship CG-to-CG only initially; the spec is published but we don't yet certify other implementations.
- **Federation between providers.** Once the spec is stable and at least one external implementation has shipped.
- **Anonymous or pseudonymous queries.** Initially both parties' CG identity is required. Anonymous-with-receipts is much later.
- **W3C Verifiable Credentials integration.** Initially uses CG-issued identity keys; VC interop later.
- **Group/team handshake.** A team account fielding handshakes on behalf of members.
- **Monetary attachments** (paid intros, bounties). Out of scope entirely; deserves its own RFD.

## Open questions

- **Probing / inference attacks.** A bad actor makes many existence queries to triangulate someone's graph. Defenses: per-requester budgets, anomaly detection, per-target rate limits, the responder's right to add the requester to a permanent block list (signed and replicated). Is that enough?
- **Consent fatigue.** If every query needs explicit consent, no one will respond. Standing rules + the Steward digest are the answer, but the calibration is unclear — how aggressively can defaults presume *"answer existence-only to first-degree connections"* without breaking the consent story?
- **Identity binding.** How does Bob's CG verify that the request claiming to come from Alice's CG is really hers? Initially: CG-issued identity keys, rooted in CG's PKI. Later: external DIDs and verifiable credentials so identity is portable off CG.
- **Spam.** Bad actors will try to overwhelm. Defenses: graph-distance gating (must be within N hops to even attempt a handshake), per-requester budgets, and the responder's mute list. Calibration TBD.
- **Liability of false intro claims.** *"Sure, I know Charlie"* could be used to manufacture social proof. Signing helps but isn't enough; responses should be readable as personal opinion, not verified fact, except for explicit `claim_verification` operations.
- **Convincing anyone else to implement it.** Protocols only matter if multiple parties ship them. Strategy: ship CG-to-CG first, prove the value, publish a clean spec with reference implementations, then court partners (personal CRMs, alumni networks, founder communities). Not try to standardize before there's demand.
- **Backwards compatibility.** The initial version will get the format wrong. A clear versioning story and migration path is required from day one.

## Decision

(Filled in when this RFD is merged.)
