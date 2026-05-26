---
authors: "<shalom@shalomormsby.com>"
state: discussion
discussion:
labels: [meta, process]
---

# RFD 0001: The ContactGraph RFD System

## Background

ContactGraph is moving from a small set of foundational documents (manifesto, requirements docs) into a phase where contested, cross-cutting decisions arrive faster than the foundation can absorb them. Examples already on the table: where the user's graph lives (the Vault), how inbound contact is mediated (the Steward), how networks federate (the Handshake Protocol), what counts as a complete picture of someone's relational life (Full-Signal Ingestion). Each reshapes the product, the manifesto's promises, or both.

We need a way to draft and discuss these decisions in the open — with their assumptions visible, their open questions named, and their state legible — before they ossify into code. We also need a record that survives the conversation: not just *what did we decide* but *what alternatives did we weigh, and why*.

We're borrowing the **Request For Discussion (RFD)** pattern from [Oxide Computer's RFD-1](https://rfd.shared.oxide.computer/rfd/0001), which itself adapts IETF RFCs and Joyent's earlier RFD process. The pattern: numbered, lightly-structured documents that move through a published lifecycle, with discussion happening in pull requests and the resolution living inside the document itself.

We are consciously **not** adopting Oxide's full apparatus. No AsciiDoc, no CSV API file, no chatbot, no rendering service, no branch-per-RFD discipline. The minimum that pays its keep for a small product team is: numbering, frontmatter, lifecycle states, PR-based discussion, and a dynamic index. The rest can land later if scale demands it.

The foundational documents — `manifesto.md`, `agent_native_graph_requirements.md`, `newco_mvp_technical_requirements.md` — stay where they are. They are the charter. RFDs propose changes to or extensions of the charter.

## Proposal

### File layout

Each RFD lives at `/rfd/NNNN/README.md` in the repo root. The folder-per-RFD shape (rather than one flat file per RFD) reserves room for attachments — diagrams, schemas, supporting documents — without forcing a refactor later.

```
/rfd/
  README.md                # Index (dynamic; see below)
  0001/
    README.md              # This document
  0002/
    README.md              # The Vault
  ...
```

### Format

Markdown, with YAML frontmatter at the top:

```yaml
---
authors: "<shalom@shalomormsby.com>"
state: discussion
discussion: https://github.com/ContactGraph/contactgraph/pull/N
labels: [topic, tags]
---
```

- `authors` (required): one or more author identifiers.
- `state` (required): one of the lifecycle states below.
- `discussion`: URL of the PR where this RFD is being discussed. Filled in when the PR opens.
- `labels`: free-form topical tags for filtering.

A starter template lives at [`/rfd/_template.md`](../_template.md). Copy it to `rfd/NNNN/README.md` where `NNNN` is the next available number, then fill it in.

### Numbering

Four-digit zero-padded integers, allocated sequentially. Numbers are not reused even when an RFD is abandoned. This document is RFD-0001.

### Lifecycle states

| State | Meaning |
|---|---|
| `prediscussion` | Draft exists, not yet shared for review |
| `ideation` | Topic placeholder; no full draft yet |
| `discussion` | Open PR; actively being reviewed |
| `published` | PR merged; the project's current direction |
| `committed` | Implementation has shipped to users |
| `abandoned` | Explicitly rejected or superseded |

Authors update the `state:` field manually as the RFD moves through its lifecycle. There is no formal gatekeeper, but an RFD should not be merged in `discussion` state without meaningful review from at least one other person.

### Discussion mechanism

Every RFD goes through a GitHub pull request. The PR is the discussion. When the RFD is ready to publish, the PR is merged; the document's state moves from `discussion` to `published` and the PR link is retained in `discussion:` as the historical thread.

Discussion can continue on a published RFD via subsequent PRs — to amend, supersede, or annotate. Published RFDs are not immutable, but changes should be visible (a new PR, with clear rationale) rather than silent.

### The index (dynamic)

`/rfd/README.md` is the entry point: a markdown table of all RFDs with title, state, discussion link, comment count, and labels. **The index must update dynamically.** A static, manually-maintained table goes stale immediately and undermines the legibility the whole system depends on.

The dynamic-update mechanism — a GitHub Action that walks `/rfd/NNNN/README.md`, reads each frontmatter, hits the GitHub API for PR state and comment counts, and commits the regenerated index back to `main` — is specified in a separate RFD (target: RFD-0006). Until that ships, the initial `/rfd/README.md` is hand-written as a starting state and updated by hand on each new RFD.

### When to write an RFD

Write an RFD for:

- New product surfaces (a major feature, a new client, a new protocol)
- Anything that bends or extends the manifesto's promises
- Anything cross-cutting that affects more than one workstream
- Hard architectural choices with multiple reasonable answers

Do not write an RFD for:

- Bug fixes
- Refactors within a single component
- Small UX changes that don't alter the contract with users
- Anything that's obviously the right thing

When in doubt, write the RFD. The cost of writing one is small; the cost of relitigating an ambiguous decision later is large.

## Open questions

- **When does an RFD become "published"?** Proposal: on PR merge. Alternative: on explicit lifecycle bump after merge. Going with PR-merge for now unless a case argues otherwise.
- **Who can author RFDs?** Anyone with repo access. May revisit if outside collaborators want to propose RFDs without a contributor role.
- **Should RFDs ever be deleted?** No. Abandoned RFDs stay in the record; the state machine includes `abandoned` for exactly this reason.
- **Do we want a `committed`-state automation later?** Probably yes — a small bot that bumps `published` → `committed` when the relevant code lands. Defer until there are several `published` RFDs awaiting implementation.
- **Format drift.** If RFDs start growing diagrams or significant supporting material, do we add structure (e.g., `/rfd/NNNN/diagrams/`) or stay loose? Defer to first occurrence.

## Decision

(Filled in when this RFD is merged.)
