# NewCo MVP: Technical Requirements

*Companion doc to `agent_native_graph_requirements.md`. This one is about how the MVP actually works end-to-end.*

The MVP proves one user journey: an agent discovers NewCo on behalf of a user, the user OAuths their Gmail, the system imports and resolves contacts, and within minutes the user can ask their agent "who do I know at X?" and get a real answer. Plus one optional viral step: invite colleagues or friends to opt in to a shared view.

Everything outside that path is out of scope for the MVP.

---

## 1. End-to-End User Journey (Happy Path)

This is the only journey the MVP needs to support. Every component below exists to serve it.

1. **User asks their agent a graph-shaped question.** "Who do I know at Stripe?" / "Who can introduce me to a recruiter at Anthropic?" / "Which of my friends has moved to Berlin?"
2. **The agent does not have the data.** It searches the web (or its MCP directory) for "find people in my network" or similar. NewCo's listing appears, with a clear skill description.
3. **The agent surfaces NewCo to the user.** "I can help with this if I have access to your contact graph. NewCo is a free service that builds it from your Gmail. Want me to set it up?" The user says yes.
4. **The agent reads the skill.md.** It contains the MCP server URL, the OAuth scope explanation, the user-facing pitch, and the exact tool definitions.
5. **The agent initiates OAuth.** The user is redirected to a NewCo-hosted OAuth page that authenticates them via Google (no NewCo account creation step) and requests Gmail read scope.
6. **The user grants Gmail access.** They are returned to the agent with a session token.
7. **NewCo begins background email import.** The first 200 contacts (by recency) are resolved and available in under 30 seconds. The full graph populates within minutes to hours depending on inbox size, with progressive availability.
8. **The agent can immediately answer the user's original question.** Even if only the top-200 contacts are loaded, that is usually enough for the first query.
9. **After the user gets their first answer, the agent prompts the Trust List step.** "Want to add a few trusted colleagues or friends to your Trust List? When you do, your agent can search across their networks too — they stay in control of every disclosure. Up to 20 people." User can name people or skip.
10. **Done.** No NewCo website was visited. No account was created. No profile was filled out. The user got an answer to a real question and was offered a viral expansion step. Total time from question to answer: 60 seconds for partial graph, full functionality within minutes.

---

## 2. Components

### 2.1 The Skill (skill.md)

A single markdown file hosted at a stable URL (`https://newco.example/skill.md` or similar) that any agent can read to understand:

- What NewCo is and why a user might want it
- The MCP server URL
- The OAuth flow URL
- The tool definitions (what the agent can ask NewCo to do)
- A short, agent-readable pitch the agent can use when explaining NewCo to the user

This is the single source of truth for agents. If we update the skill, all agents pick up the new behavior on next read.

The skill should be discoverable by:
- Being listed in the official Anthropic MCP registry, Smithery, Glama, PulseMCP
- Being indexed by Google for queries like "find people I know MCP server" / "build network graph from Gmail"
- Being known to the foundation-model providers' connector directories (Claude Connectors, ChatGPT Apps, Gemini Tools)

### 2.2 The MCP Server

A single hosted MCP server endpoint that exposes a small set of tools to the agent. MVP tool surface:

**Setup and status**
- **`connect_gmail(user_token)`** — initiates or completes the OAuth flow for Gmail. Returns a session ID.
- **`get_import_status(session_id)`** — returns current state: `pending | importing | partial | complete`, with counts (contacts found, contacts resolved, contacts pending).

**Querying**
- **`query_network(question, session_id)`** — the main query interface. Accepts natural-language questions. Returns a structured list of Person and/or Org results. By default, queries include both first-degree (own graph) and second-degree (Trust List) results, with second-degree results showing only existence-level disclosure unless higher levels are already approved.

**Trust List management**
- **`invite_to_trust_list(emails[], session_id)`** — sends invitations to add people to the user's Trust List. Returns invite IDs. Enforces the 20-person cap.
- **`get_trust_list(session_id)`** — returns the user's current Trust List membership.
- **`remove_from_trust_list(membership_id, session_id)`** — removes a member.

**Disclosure**
- **`request_disclosure(target_request, session_id)`** — initiates a disclosure request to a Trust List member. `target_request` includes the holder, the target person (by ID from a prior query), the requested level (existence/identity/intro/contact-share), and the requester's context.
- **`list_pending_requests(session_id)`** — returns disclosure requests waiting for this user's approval (where this user is the holder).
- **`respond_to_request(request_id, action, note, session_id)`** — approve/decline/ignore an incoming request, with optional note.
- **`get_request_status(request_id, session_id)`** — for the requester to check the state of their outbound request.

**Privacy controls**
- **`set_contact_privacy(person_id, label, session_id)`** — marks a contact as public/standard/private.
- **`set_standing_approval(rule, session_id)`** — creates a standing approval rule for power users.

Tools should be designed to be agent-friendly: predictable inputs, structured outputs, clear error states. The agent should never need to scrape HTML or parse free text from NewCo.

### 2.3 OAuth Flow

The OAuth flow is intentionally minimal:

1. Agent invokes `connect_gmail` tool. NewCo returns a one-time URL.
2. User opens that URL in a browser. Page shows the NewCo pitch in 2-3 sentences, the data-handling promises ("we never sell your data," "you can delete everything anytime"), and a single "Connect Gmail" button.
3. User clicks. Standard Google OAuth flow. NewCo requests `gmail.readonly` and `profile` scopes only. No write scope, no contacts scope (we derive contacts from email metadata).
4. Google returns the user to NewCo with a token.
5. NewCo creates the account *implicitly* using the email address from the Google profile. No separate signup form. The user's email is their identity.
6. User sees a single confirmation page ("You're connected. Return to your agent.") and a button that closes the browser tab / returns to the agent UI.

No NewCo password. No NewCo signup form. No email verification step (the OAuth flow already proves ownership of the address). No phone number. No profile photo. No name field. We get everything we need from the Google profile.

### 2.4 Email Import Pipeline

After OAuth completes, the import pipeline runs in the background. It must:

1. **Start with the most recent N=200 contacts (by recency of email).** These should be resolved and queryable within 30 seconds of OAuth completion. This is the "first answer fast" requirement.
2. **Continue in reverse chronological order through the inbox.** Process emails in batches, extracting sender/recipient/cc/bcc as candidate contacts.
3. **Run entity resolution on each candidate.** Use an LLM to dedupe variants (same person across multiple email addresses, name spelling variants, signature-vs-header mismatches). Resolution should produce a single Person node per real human.
4. **Extract relationship signals.** Per-edge data: count of emails exchanged, recency, direction (who initiated), thread depth, presence in calendar events. Also extract the *relationship type* (neighbor, friend, colleague, vendor, prospect, customer, investor, etc.) using an LLM classifier over a sample of the thread content.
5. **Track last-genuine-contact.** Distinguish between "I'm on a mailing list with this person" and "we actually had a back-and-forth conversation." The system computes a `last_genuine_interaction_at` timestamp from threads where both parties exchanged at least one substantive message (not auto-replies, not list traffic). This is what the user actually means when they say "when did I last talk to her?"
6. **Preserve representative interaction excerpts.** For each Person and Org edge, store 3-10 short, representative excerpts from the user's emails with that contact, plus vector embeddings of recent thread content. These power semantic queries ("who did I talk to about hiring last month?") and disambiguate relationship classification. We do NOT store full email bodies long-term; we extract excerpts and embeddings within the 24-hour processing window and discard raw content.
7. **Aggressive public-data enrichment.** Email signature parsing (title, employer, phone, address) plus aggressive web enrichment via Exa, Tavily, or similar. For each new contact and each new Org, run web searches to populate: current employer, role, location, recent news, social profiles, company stage/size/funding, industry, technology stack. Re-enrich on a schedule (weekly for active contacts, monthly for dormant ones) to catch job changes and other updates. Enrichment is cheap and high-leverage; we should err on the side of more.
8. **LLM-assisted classification.** For each contact: inferred categories (VC, founder, engineer, journalist, neighbor, etc.) and relationship type tags. For each Org: inferred categories (VC firm, SaaS startup, law firm, restaurant, government agency, etc.).
9. **Write to the user's personal graph.** Each user gets their own isolated graph in the central database.
10. **Report progress.** The `get_import_status` tool should return real-time progress so the agent can tell the user "still importing, ask me again in a minute" if needed.

Reasonable defaults: process ~1000 emails per minute per user, prioritize the most recent year, deprioritize emails older than 5 years (they are mostly noise for current-network queries).

### 2.5 The Query Engine

The `query_network` tool needs to translate natural-language questions into graph queries.

Approach: an LLM-backed query layer that knows the graph schema and can construct queries against the underlying graph database (Postgres + pgvector for embeddings, with graph-style joins). The query layer can combine structured filters (current employer, location, relationship type) with vector search over interaction excerpts.

Common query shapes the MVP must handle well:

- **Filter by current attribute.** "Who do I know at Stripe?" / "Who is a VC?" / "Who lives in Berlin?"
- **Filter by relationship type.** "Who are my neighbors?" / "Who's an old colleague from Adap.tv?" / "Who have I sold to or pitched?" / "Which contacts are personal friends vs. work?"
- **Filter by recency of genuine contact.** "Who have I genuinely talked to in the last month?" (not list traffic) / "When did I last actually talk to David?" / "Who haven't I had a real conversation with in over a year but used to be close to?"
- **Filter by change.** "Who changed jobs recently?" / "Who moved to a new city?" / "Which companies in my network just raised?"
- **Semantic / topical.** "Who have I talked to about hiring engineers?" / "Who did I discuss pricing with last quarter?" — powered by vector search over preserved excerpts.
- **Combined filters.** "VCs I haven't genuinely talked to in 6 months" / "Engineers in my network who used to work at Google" / "Friends in Berlin I haven't seen this year"
- **Org-as-subject queries.** "What companies in my network are hiring?" / "Which startups have I been pitched by?" / "What restaurants have friends recommended?"
- **Path queries (post-invite, if shared graphs exist).** "Who in my company knows someone at Acme?"

Output is structured: a list of Person and/or Org records with relevant attributes, tie strength, last-genuine-contact date, relationship type, and a brief explanation of why each match was relevant. The agent then presents this to the user in whatever form is appropriate to the conversation.

### 2.6 The Invite Flow

After the user gets their first answer, the agent prompts: "Want to invite a few trusted people to your network? When you do, your agent can search across their contacts too (with their permission for each disclosure)."

If the user names people (e.g., "yes, my co-founders Alice and Bob and my friend Sarah"):

1. Agent calls `invite_to_trust_list(["alice@acme.com", "bob@acme.com", "sarah@gmail.com"])`.
2. NewCo sends each a short email: subject "Teg wants to add you to his trust list on NewCo," body explains the model in 3 sentences ("Teg has shared his network with you. If you accept, you'll share yours back, and you can each ask the other for warm intros — you stay in control of every disclosure."), links to OAuth flow with a referral parameter.
3. When the invitee completes OAuth, they are added to a mutual Trust-List relationship with the inviter.
4. Each user retains full control. See Section 2.7 for the disclosure model that governs what is actually visible across the relationship.

The invite step is optional. The user can skip it without losing the basic single-player experience.

### 2.7 The Trust List and Permissioned Disclosure

The Trust List is the mechanism that makes network sharing safe enough to say yes to. Instead of pooling networks (the LinkedIn / Swarm model), each user shares with a small set of trusted people, and every cross-user disclosure is permissioned per-query.

#### The 20-person cap

Each user can have up to 20 people in their outbound Trust List. The cap is intentional and important:

- **It forces curation.** If sharing is unlimited, people share carelessly. If it's bounded, they pick the people they actually trust.
- **It matches how networks actually work.** Roughly Dunbar-adjacent. The "people I'd ask for a favor" list is rarely bigger than this.
- **It bounds the blast radius.** The sharer is making a real promise to a small group, not opening their address book to the world.
- **It creates social meaning.** Being in someone's 20 is a relationship marker, similar to being a Close Friend on Instagram. We lean into this.

The cap is **asymmetric**: a user can be *in* an unlimited number of other people's Trust Lists (the friction is on them, not on you), but can only have 20 in their own outbound list. To add a 21st, they must remove someone first.

Adding someone to your Trust List requires them to OAuth and reciprocally add you. Mutual or nothing. This is enforced at the data layer.

#### The per-query disclosure flow

When User A asks their agent "who do I know at Acme?":

1. **A's agent queries A's first-degree graph.** Returns direct contacts at Acme with full attributes (name, email, role, etc.). No permission needed; this is A's own data.
2. **A's agent queries A's second-degree graph** (people in A's Trust List). For each match, returns *the trusted person's name and the existence of a contact at Acme*, but not the contact's identity or attributes by default. Example: "Cynthia in your Trust List knows someone at Acme."
3. **A's agent surfaces options to A.** "Cynthia knows someone at Acme. Want me to: (a) ask Cynthia who it is, (b) ask Cynthia to introduce you, (c) ask Cynthia to share their email?" These map to three discrete disclosure levels.
4. **A picks an option.** A's agent sends a request to Cynthia's agent through NewCo's messaging layer.
5. **Cynthia's agent surfaces the request to her.** "Teg is asking about your contact at Acme. He wants [identity reveal / intro / contact share]. Approve, decline, or ignore?" Cynthia can include a note or modify what she's willing to share.
6. **On approval, the disclosure happens.** A's agent receives the requested information. The interaction is logged so both parties can see what's been shared.

#### Disclosure levels

Three discrete levels, requested separately:

| Level | What is revealed | Typical use case |
|---|---|---|
| **Existence** | "Cynthia knows someone at Acme" | Pre-disclosure default. A learns a path exists. |
| **Identity** | "Cynthia knows Ashu Garg at Acme" | A wants to evaluate the path before asking for help. |
| **Intro** | Cynthia sends a double-opt-in intro between A and Ashu | A wants to actually connect. |
| **Contact share** | Cynthia shares Ashu's email/info directly with A | A wants to reach out themselves. |

Each level requires separate approval. Approving "identity" does not automatically approve "intro." This makes Cynthia feel safe saying yes because each yes is bounded.

#### Standing approvals

For users who want to reduce friction, optional standing rules:

- "Anyone in my Trust List can see the existence of my contacts at any company" (existence-level pre-approved)
- "Anyone in my Trust List can see identity for contacts I've labeled 'public' (e.g., people whose roles are listed on their company website anyway)"
- "Auto-approve intro requests for VCs to founders, with a notification"
- "Never share contacts I've labeled 'private'"

Most users will not configure these; the per-query approval flow is the default. Power users (founders, recruiters, investors who get a lot of intro requests) will use standing rules to manage volume.

#### Rate limits and decline-as-feature

- A user can be asked at most N times per week by any single requester (default N=3).
- A user can set a global "intro request" rate limit ("max 5 active requests at a time").
- Declining without explanation is normal and expected. The asker is told "Cynthia chose not to share this time" without further detail. No social pressure built into the product.
- "Mute" for a Trust List member without removing them, for cases where someone wants a break without ending the relationship.

#### Contact privacy controls (on the contact side)

A user can mark individual contacts in their own graph as:
- **Public** (in their Trust List): existence and identity auto-approved for Trust List requests; intro/share still requires approval.
- **Standard** (default): all disclosures require approval.
- **Private**: never disclosed to anyone, even existence. Effectively invisible to Trust List queries.

This handles cases like "my therapist is in my email but I never want anyone to know I see one" or "my ex's email is still in my contacts."

#### The viral loop

The Trust List model is structurally viral in a specific way. Every disclosure request that flows from A's agent to Cynthia's agent is, by definition, a use of NewCo. Cynthia sees the request, decides to participate or not, and either way has been shown what the product is for. When she eventually wants to ask her own intro request, NewCo is the obvious tool.

Compare to The Swarm: their model requires Cynthia to upload her LinkedIn or Gmail data to a SaaS product she may never use, motivated only by helping her company's sales team. Most people never do this. NewCo's model gets Cynthia in because she wants to receive intros, not because anyone asked her to.

---

## 3. Data Model (MVP-minimal)

The full data model will get richer over time. The MVP needs:

### 3.1 User
- `user_id` (UUID)
- `email` (from Google OAuth, used as identity)
- `oauth_tokens` (encrypted at rest)
- `created_at`
- `import_status`
- `data_handling_consent_version`

### 3.2 Person (contact node, per user)
- `person_id` (UUID, scoped to the user's graph)
- `canonical_name` (LLM-resolved)
- `email_addresses[]` (all addresses we've seen)
- `phone_numbers[]` (from signatures)
- `current_org_id` (FK to Org)
- `current_role`
- `previous_employments[]` (list of Org/role/dates from enrichment)
- `location`
- `inferred_categories[]` (VC, founder, engineer, journalist, neighbor, etc.)
- `social_profiles` (LinkedIn URL, Twitter/X, GitHub, etc., from enrichment)
- `bio_summary` (LLM-synthesized from enrichment sources)
- `last_enriched_at`
- `last_seen_in_email`
- `created_at`
- `confidence_score` (how sure we are this is a single real person)

### 3.3 Org (organization node, shared across users)
Orgs are first-class. Users have relationships with companies (vendors, employers, prospects, customers, investors) just like with people. Shared across all users in the central DB to avoid duplicate enrichment work; only edges are per-user.
- `org_id` (UUID, global)
- `canonical_name`
- `domain` (primary, used as a dedupe key)
- `aliases[]` (other names/domains)
- `categories[]` (VC firm, SaaS startup, restaurant, government agency, neighborhood association, etc.)
- `location` (HQ + offices)
- `size` (employee count band)
- `industry`
- `stage` (private/seed/series A-Z/public/etc., where applicable)
- `funding_history[]` (rounds, dates, amounts, lead investors)
- `tech_stack[]` (for tech companies)
- `description` (LLM-synthesized)
- `website`
- `last_enriched_at`
- `created_at`

### 3.4 Person-Edge (user's relationship with a person)
- `user_id` (graph owner)
- `person_id`
- `relationship_types[]` (neighbor, friend, colleague, former-colleague, prospect, customer, investor, vendor, family, classmate, etc.). A single edge can carry multiple types.
- `relationship_confidence` (LLM-assigned confidence per type)
- `email_count`
- `outbound_count`
- `inbound_count`
- `thread_count`
- `last_email_at`
- `last_genuine_interaction_at` (last actual back-and-forth; excludes mailing lists, auto-replies)
- `first_contact_date`
- `tie_strength_score` (computed from frequency, recency, mutuality, thread depth)
- `notes` (LLM-generated summary of the relationship, e.g., "Former co-worker at Adap.tv, now at Stripe; last substantive thread was about hiring in March")

### 3.5 Org-Edge (user's relationship with an organization)
Sometimes the relationship is with a company more than a single person. Examples: a vendor the user buys from, an investor firm, a competitor, an alma mater.
- `user_id` (graph owner)
- `org_id`
- `relationship_types[]` (employer, former-employer, vendor, customer, investor, portfolio-company, prospect, partner, etc.)
- `associated_person_ids[]` (the contacts at this Org the user has talked to)
- `total_email_count` (across all people at this Org)
- `last_genuine_interaction_at` (most recent across any person at the Org)
- `tie_strength_score`
- `notes`

### 3.6 Interaction Excerpt (per user, per edge)
Preserved excerpts and embeddings from observed email threads. Powers semantic queries and grounds relationship classification.
- `excerpt_id`
- `user_id`
- `person_id` or `org_id` (which edge this excerpt is associated with)
- `excerpt_text` (a short, representative snippet, not the full email — typically 1-3 sentences)
- `embedding` (pgvector, for semantic search)
- `thread_subject_hint` (decontextualized topic, e.g., "discussion of Q2 pricing" not the literal subject line)
- `direction` (sent | received | exchanged)
- `occurred_at`
- `created_at`

Excerpts are LLM-generated at ingest time: we read a thread, extract a 1-3 sentence representative summary, embed it, and discard the original. There are 3-10 excerpts per active edge; older excerpts may be summarized further or pruned over time.

### 3.7 Trust List Membership (mutual)
The 20-person cap is enforced at this layer. Membership is mutual: both rows exist or neither does.
- `membership_id`
- `user_a_id`
- `user_b_id`
- `established_at`
- `status` (active | muted-by-a | muted-by-b | revoked)
- Constraint: each user can have at most 20 active outbound memberships at a time.

### 3.8 Standing Approval (per user)
Optional pre-approval rules a user sets to reduce per-query friction. Most users will have zero of these.
- `rule_id`
- `user_id`
- `applies_to` (any-trust-list-member | specific-user-ids)
- `disclosure_level` (existence | identity | intro | contact-share)
- `match_predicate` (e.g., "contact has category=VC", "contact marked as public", "contact's current_org has category=startup")
- `created_at`

### 3.9 Disclosure Request (per query)
Every cross-user disclosure starts as a request and ends in approve/decline/expire. Logged for both parties' audit.
- `request_id`
- `requester_user_id` (who's asking)
- `holder_user_id` (whose contact is being asked about)
- `target_person_id` (the contact in question, scoped to holder's graph)
- `level_requested` (existence | identity | intro | contact-share)
- `requester_context` (LLM-generated short reason: "Teg is trying to break into Acme for sales")
- `status` (pending | approved | declined | expired | auto-approved)
- `responded_at`
- `responder_note` (optional)
- `created_at`

### 3.10 Contact Privacy Label (per user, per person)
A user's labeling of their own contacts for disclosure purposes.
- `user_id`
- `person_id`
- `privacy_label` (public | standard | private)
- `set_at`

### 3.11 Rate Limit State (per requester-holder pair)
Tracks request volume for per-pair rate limiting.
- `requester_user_id`
- `holder_user_id`
- `requests_this_week`
- `week_start`

### 3.12 Invite (pre-acceptance)
- `invite_id`
- `inviter_user_id`
- `invitee_email`
- `intended_membership` (trust-list)
- `sent_at`
- `accepted_at` (nullable)

---

## 4. Non-Functional Requirements

### 4.1 Latency
- OAuth completion to first 200 contacts available: under 30 seconds.
- `query_network` response time: under 2 seconds for queries against a single user's graph.
- `get_import_status`: under 200ms.

### 4.2 Privacy and Data Handling
- Raw Gmail content is processed but not stored verbatim. Raw email bodies are discarded within the 24-hour processing window.
- What IS persisted: extracted entities (Person, Org), edge data, LLM-generated short excerpts (1-3 sentences each), embeddings of those excerpts, and enrichment data fetched from public sources. The excerpts are derived data, kept because they power semantic queries and ground relationship classification.
- Per-user data isolation. No query path can cross users without an explicit Share record. Excerpts and edges are strictly per-user; Orgs and their enrichment data are shared (no user-specific data lives on the Org node).
- User can delete their entire graph and all derived data (including excerpts and embeddings) via a single API call, with verifiable completion.
- All data encrypted at rest. OAuth tokens encrypted with a separate key.
- Enrichment via Exa, Tavily, etc. is on public web data only. We do not scrape closed sources (LinkedIn, Facebook, etc.) or violate any platform's ToS.
- No third-party tracking, analytics, or ad pixels on the NewCo OAuth page or anywhere in the user flow.
- The data-handling pact is published publicly and version-tracked; any change requires user notification.

### 4.3 Reliability
- The MCP server should aim for 99.5% uptime for MVP (95% acceptable for first 100 users).
- Email import is async and can recover from interruptions. If the pipeline crashes halfway through a user's import, it resumes from where it stopped on next worker pickup.

### 4.4 Agent compatibility
- The skill.md and MCP server must work with Claude (Anthropic MCP client), ChatGPT (Apps SDK / MCP), Gemini (Vertex AI Agent Builder), and Cursor at minimum.
- Tool definitions must be valid against the current MCP spec.
- The OAuth flow must work in both browser and embedded-browser contexts.

### 4.5 Scale (MVP)
- Designed to support up to 10,000 users without re-architecture.
- Designed to process up to 50,000 emails per user.
- Beyond those numbers, the architecture should degrade gracefully (slower imports, longer query latency) rather than fail.

---

## 5. Out of Scope for MVP

Explicitly not in v1:
- Any UI beyond the OAuth page and settings (no LinkedIn-style profile pages, no feed, no dashboard)
- Calendar integration (planned for v1.1)
- Slack, CRM, or other tool connectors (planned for v2)
- Federation across data sources beyond Gmail
- Verified credentials / W3C VC
- Mobile apps
- Notifications / email digests
- Paid tier features (team admin, audit logs, SSO)
- Vertical applications (recruiting, fundraising, etc.) — those are separate products built on top
- LinkedIn imports (intentionally avoided)
- Cross-user querying via federation (only via explicit Share records)

---

## 6. Success Criteria for the MVP

The MVP is successful if:

1. An agent (Claude, ChatGPT, or Gemini) can discover NewCo via web search or directory listing, with no prior knowledge of it.
2. From the user's first prompt to first useful answer: under 90 seconds end-to-end.
3. Entity resolution is good enough that a user does not lose trust in the first session. Anecdotally: fewer than 5% of returned contacts have visibly wrong attributes.
4. Of users who complete OAuth, at least 50% ask a second question within their first week.
5. Of users who complete OAuth, at least 20% accept the invite step and name at least one colleague or friend.
6. Of named invitees, at least 30% accept and complete OAuth themselves. This is the viral coefficient we need to be tracking.
7. The full system runs on under $5/user/month in infrastructure cost at MVP scale.

If we hit these, we know the wedge works and we can start building out v1.

---

## 7. Decisions Made + Open Questions

### Decisions for MVP

- **Database: Postgres + pgvector.** Relational graph patterns are fine for our scale. pgvector handles excerpt embeddings. Can add Apache AGE later if pure graph traversal becomes a bottleneck.
- **Hosting: Railway or Fly.io.** Self-hosted on a modern PaaS, not on AWS/GCP. Easier ops, regional deployment, fits the team scale.
- **Public enrichment: aggressive.** Exa and Tavily are cheap and information-rich. We enrich on first ingest and re-enrich on schedule. Signature parsing + web lookup + LLM synthesis on every contact and every Org. The more we know, the more useful the graph.
- **Entity resolution: frontier LLM at ingest.** Quality matters more than cost in the MVP. Revisit cost when we have volume.
- **Excerpt preservation: yes, forever.** 3-10 short excerpts per active edge, embedded with pgvector. Older excerpts stay queryable so users can ask "what did we discuss back in 2018." Powers semantic queries and is much more useful than metadata alone.
- **Invites: hard cap of 20, one at a time by email.** No bulk invite. No CSV upload. The friction is the feature: you have to type each address, one by one. This is what keeps the Trust List meaningful and stops spam at the source.
- **Multiple Gmail accounts per user: yes.** A user can connect any number of Gmail addresses (work, personal, side projects, etc.) to a single NewCo account. All emails flow into one unified graph with the same identity owning them. This is necessary because most professionals already have 2-3 inboxes.
- **Account merge across Google identities: yes (for distinct Google accounts).** If a user authorizes with two completely separate Google accounts, we offer to merge them into one NewCo account post-OAuth. The user is the merge authority.
- **Org dedupe: aggressive, LLM-driven.** Domain is the dedupe key when available, but we also fuzzy-match on name + location + industry + signature data to merge orgs across domains (acme.com / acmecorp.com / acme.co.uk → one Org). For the future, when we accept LinkedIn imports, contact uploads, etc., we have to make our best guess and resolve conservatively. Eventual admin-claim path for orgs is possible but not MVP.
- **Account deletion semantics.** If User A deletes their account, all of A's data is purged within 24 hours. Trust List memberships involving A become inactive; any disclosure requests in-flight expire. None of A's data was ever copied into B's graph, so B's graph is unaffected; B simply loses query paths that ran through A.
- **Enrichment retry on failure.** If Exa/Tavily/etc. are down or rate-limited, import continues with signature parsing only and enrichment for affected contacts is queued for retry with exponential backoff.

### Open Questions

1. **How much context per relationship is the right amount?** With excerpts kept forever, the question becomes how much detail to surface in any given query response. A "notes" summary on the edge is one cut. Per-thread excerpts is another. There's a Goldilocks question of "enough to feel like the agent really knows this person" vs. "so much it's noisy or creepy." Worth user testing.
2. **Account merge UX for multi-Google users.** What's the right flow when a user OAuths a second Google account? Auto-detect they already exist (by name / overlapping contacts)? Prompt explicitly? Let them choose at OAuth time?
3. **Re-enrichment cadence.** Active contacts weekly, dormant monthly is the starting heuristic. What other triggers should refresh enrichment (new email from that person, mentioned in a query, change detected in their bio summary)?
4. **What happens at "existence-level" disclosure for sensitive contacts?** "Cynthia knows someone at Acme" implicitly reveals that Cynthia has *any* contact at Acme. For users in sensitive professions (recruiters, lawyers, journalists), this can leak. The Contact Privacy Label "private" handles the explicit case but should standard contacts be more conservative by default?
5. **Disclosure broadcast vs. point-to-point.** Right now disclosure requests are point-to-point (A asks Cynthia specifically). Should we also support broadcast ("anyone in my Trust List who knows someone at Acme, please respond")? Saves the requester from asking five people one by one, but raises social complexity.
6. **Multi-Gmail and shared inboxes.** If a user connects a shared inbox (e.g., a founder's `team@startup.com` they also have access to), do we treat all team emails as the user's graph? Probably no, but the UX needs to detect and warn.
