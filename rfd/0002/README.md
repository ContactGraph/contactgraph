---
authors: "<shalom@shalomormsby.com>"
state: discussion
discussion:
labels: [vault, sovereignty]
---

# RFD 0002: The Vault

## Background

Today, after OAuth + sync, the user's graph is invisible — a row in our Postgres they cannot point at. This breaks the manifesto's central promise. *"You own your graph"* is theoretical until the user can hold it, browse it, annotate it, and leave with it.

The highest-leverage early adopters are power users who want to groom and annotate (founders, recruiters, BD), privacy-skeptical users who need see-to-believe before granting Gmail scope, and future portability users who will move their graph between CG-compatible providers. The Vault is what makes sovereignty concrete for all of them.

The Vault is foundational for several other RFDs: the Steward's standing rules (RFD-0004) need somewhere to live; the Handshake Protocol (RFD-0005) needs a place to log both sides of every exchange; Full-Signal Ingestion (RFD-0003) benefits from the visible *"here is what I learned about you"* surface that the Vault provides.

## Proposal

After first sync, the agent says: *"Your graph is ready. You can browse it at vault.contactgraph.ai."*

The Vault web app shows:

- A force-directed map of people, orgs, and clusters — walkable, zoomable
- A list view filterable by category, tie strength, last contact, org
- A detail page per person/org: history, edges, attributes, raw evidence, annotations
- A time slider (2008 → today) to watch the graph evolve

From any node the user can: add a note, merge with another node, split a misjoined entity, mark `private` / `never_share`, set rules (`alert me on inbound`, `mute forever`), retag a relationship.

**Export anywhere.** One click writes the full graph in open `.cgraph` format (JSON-LD with a published schema) to download, iCloud Drive, Google Drive, GitHub, or S3.

### The `.cgraph` format

- Open spec, versioned, JSON-LD with a public JSON Schema
- Nodes (Person, Org) + edges (employment, correspondence, co-occurrence) + annotations
- Each record stamped with the owner's CG identity (sets up later verifiable-claims work)
- Re-importable by any future CG-compatible service — sovereignty by interoperability

### Proposed sovereignty primitives

- **Encrypted at rest** with per-user keys (CG-held initially, user-held on the roadmap)
- **Open format** with a published schema
- **Full export** — one click, no rate limit, no premium gate
- **Hard delete** — *"burn my graph"* wipes everything within 24h, confirmed by email
- **Annotation layer** — user notes, merges, and rules live in the Vault and feed the agent

### What we're proposing to build first

A web UI for browse, search, annotate, merge/split, and time-travel. `.cgraph` export to local download and the major cloud-drive destinations. Encryption-at-rest with per-user keys. Standing rules surfaced to the agent (`mute`, `alert`, `never-share`). One-click hard delete.

### What we're explicitly punting

- Self-hosted Vaults (point at your own S3 / local file) — depends on the format being stable in production
- Cryptographic signing + verifiable claims — depends on a separate identity workstream
- Cross-Vault federation — depends on RFD-0005 and the Steward
- Mobile app — desktop-first initially
- Inheritance / estate features — quietly profound, but post-initial

## Open questions

- **Key management UX.** User-held keys break recovery; CG-held keys weaken the promise. Likely start CG-held with user-held on the roadmap, but the cutover path is unclear.
- **User edits vs. system signal.** Annotations can mislead the agent (the user marks someone as a VC who isn't one). Need a clear convention for *user-asserted* vs. *system-inferred*, with the agent surfacing both rather than overwriting.
- **Render performance.** Force-directed graphs at 5k+ nodes need WebGL and aggregation. Default to org-level view and expand on demand, or render the full graph and rely on browser capability?
- **Mobile.** Acceptable to be desktop-only at launch?
- **Naming.** *"Vault"* implies locked-away; the Vault is meant to be walked into. Alternatives: *Home*, *Atlas*, *Garden*. Security framing is strong but worth revisiting before launch.

## Decision

(Filled in when this RFD is merged.)
