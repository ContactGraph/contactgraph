# Agent-Native Personal Graph: Requirements Doc v0.1

*Working title: "NewCo." Final name TBD.*

A free-forever consumer graph of professional and personal relationships, owned and controlled by the user, populated by their own email and calendar data through their AI agents, and queryable through any agent via MCP. Designed to take back the territory currently controlled by LinkedIn, Facebook, and Instagram by inverting the model: the user owns the data, the agent populates the graph, and the human never has to maintain a profile.

The viral loop: any user can invite their colleagues, friends, or community members to opt in to a shared team or group view, instantly unlocking second-degree network expansion ("who at our company knows someone at Stripe?", "which of my friends has a contact in Berlin?"). This is the feature The Swarm charges $99-$10k/month for, given away free, distributed through consumer-style word-of-mouth instead of enterprise sales. Each user controls what they share; the team view is an opt-in overlay on already-private personal graphs.

## The motivation

Letting private, billionaire-controlled, extractive companies own our social infrastructure was a step in the wrong direction. We aim to correct that.

For two decades, the social networks (LinkedIn, Facebook, Instagram) have extracted enormous value from data that users freely contributed. The deal was: you tell us who you know, what you do, and where you've been; we give you a free service and monetize your attention to advertisers. That bargain made sense in 2005. It does not make sense now.

The AI agent era changes the economics. A user's agent can populate a richer, more truthful, more current graph from the user's own email and calendar than they ever could by hand on a profile page. The graph belongs to the user. The user's agent uses it on their behalf. Third parties (recruiters, salespeople, journalists, neighbors, anyone) can request access through the user's agent, with the user's consent, on the user's terms.

The goal is not to build a better LinkedIn. The goal is to make LinkedIn, Facebook, and Instagram structurally irrelevant for the use cases people actually care about: finding people, getting introductions, hiring, job hunting, building community, asking for recommendations. Those use cases do not require a destination social network owned by a single private company. They require a graph the user owns and an agent that can query it.

This is a project about giving people back control of their relational data and putting it to work for them, not for the platforms.

---

## 1. The Market Need

### The user problem

People increasingly do their work, planning, and decision-making by talking to an AI agent (Claude, ChatGPT, Gemini). When those conversations turn to anything involving other people, the agent hits a wall. It cannot answer:

- "Who do I know who works at Stripe?"
- "Find me a job through someone in my actual network."
- "Who should I talk to about hiring a roofer in my neighborhood?"
- "Which of my friends became VCs?"
- "Who in my graph is closest to this person I want to reach?"
- "Who's the warmest path to a recruiter at Anthropic?"

The information needed to answer these questions exists, scattered across the user's Gmail, Calendar, Slack, phone contacts, and historical interactions. But no agent can stitch it into a queryable graph today, and the one place where this data partially exists in structured form (LinkedIn) is locked behind a hostile UI and aggressive anti-agent enforcement.

### The structural problem

LinkedIn is the de facto professional graph, and its moat is one of the deepest in software. Microsoft paid $26B for it, and the entire $50B+ ecosystem of sales intelligence, recruiting tech, and outreach automation is built on workarounds (Apollo, ZoomInfo, Clay, The Swarm, Champify, Cognism). LinkedIn's data is:

- **Self-reported and stale.** Titles are inflated, jobs lag actual changes by months, most "connections" represent zero relationship.
- **Locked away from agents.** LinkedIn's API is closed to programmatic use; ToS is hostile to scraping despite the hiQ ruling.
- **Optimized for ad revenue, not utility.** Recruiters pay $10k+/seat to access what should be a queryable graph.

The professional graph is structurally a commons (it describes shared reality, not anyone's IP), but it has been privatized. Every previous attempt to unseat LinkedIn has failed because they tried to rebuild the supply side: convince users to fill out a profile on a new platform. Users will not do this twice.

### Why now

Three things changed in the last 18 months that make this tractable for the first time:

1. **LLMs are cheap enough to do entity resolution and enrichment at population time.** The dedupe step (Sarah Chen in Gmail = Sarah Chen in your CRM = "Sarah" in Slack) used to require expensive paid APIs or manual work. Now an LLM can do it for fractions of a cent per contact, at population time, with high accuracy.

2. **Agents are now the primary UI.** Users increasingly start tasks by talking to Claude/ChatGPT/Gemini, not by opening an app. This means the agent itself can be the distribution channel: the user asks for help, the agent discovers and installs the right MCP server, the work gets done.

3. **MCP is the connective tissue.** The protocol is now supported by Claude, ChatGPT, Gemini, Cursor, and most major agent runtimes. An MCP server is the natural way to expose this graph to any agent the user happens to be using.

### Why free, why consumer-first

The graph is fundamentally a consumer product, not a B2B product, and the pricing posture has to reflect that. Specifically:

- **Free + consumer-first earns deeper data access** than a paid tool can. Users who would never give a B2B SaaS startup their Gmail will give a consumer product their Gmail, especially when the agent is asking on their behalf for a specific task.
- **Free enables agent-initiated distribution.** The agent can install the tool mid-conversation, with no payment step, no trial wall, no "talk to sales." This is the entire distribution mechanism.
- **The graph itself is structurally a commons.** It describes shared reality (who works where, who knows whom) and trying to extract rent on it is what created the LinkedIn problem in the first place.
- **Monetization happens at the application layer.** Recruiting tools, sales prospecting, fundraising tools, real-estate matching, journalist source-finders all build on the graph. The graph stays free; the apps on top can charge whatever the market bears.

### Competitive landscape

The closest existing players and why none of them are the same thing:

- **The Swarm** ($8M raised, founded 2021) is the most strategically similar. They have an MCP server, a relationship graph, and team-level federation. But they sell B2B, depend on LinkedIn imports, charge $99-$10k/month, and use a SaaS UI rather than agent-as-UI. Their model is structurally incompatible with going free.
- **Clay.earth, Dex, Folk, Rings.ai** are personal-CRM-style products. They have the Gmail population but no agent-native discovery and no cross-user layer.
- **Connect the Dots** ($15M Series A in 2021) had the email-crawl model but is a SaaS app, not agent-native.
- **Apollo, ZoomInfo, People Data Labs** are paid B2B data layers, not consumer networks.

No one is shipping the combination of: free forever for consumers, agent-discovered, agent-installed, agent-queried, Gmail-populated, with a consented cross-user query layer.

---

## 2. The Product

### What it is, at the layer below the user

NewCo is an MCP server that maintains a user's personal graph of people, organizations, and relationships, derived primarily from their own email and calendar with progressively deeper read access to other tools they opt into.

Each user's graph is private by default. Cross-user queries are opt-in and consent-based: when User A's agent wants to ask "does anyone in the network know Sarah Chen at Stripe," the system can answer based only on what other users have explicitly chosen to make queryable about themselves.

### What the user experiences

The user never installs NewCo from a website. They never see a marketing landing page during onboarding. The flow is:

1. User is talking to Claude/ChatGPT/Gemini about something that requires their network. ("Who do I know who's done a Series A in healthtech?" "Help me find a babysitter someone in my network recommends." "Who should I ask about moving to Berlin?")
2. The agent realizes it does not have the graph data needed. It searches for and finds NewCo. It surfaces this as a suggestion: "I could help with this if I had access to your contact graph. There's a free tool called NewCo that builds it from your Gmail. Want me to set it up?"
3. User says yes. The agent reads the skill/connector documentation, walks them through the OAuth flow (Gmail first, calendar next, then optional others).
4. NewCo begins crawling email in reverse chronological order. Within seconds it has the user's top 50 most-recent correspondents. Within minutes, hundreds. Within hours, the full graph.
5. The user goes back to their original question. The agent now answers it.

The user never opens NewCo's website. They might not even remember the name. The graph is invisible infrastructure that their agent uses.

### What lives in the graph

Per user, organized as a property graph:

- **Person nodes** (resolved across email addresses, phone numbers, social handles, name spellings).
- **Org nodes** (companies, schools, nonprofits, community groups, neighborhoods).
- **Edges** representing relationships, with type, strength, recency, and provenance.
- **Inferred attributes** on each person (current role, employer, location, areas of expertise) derived from email signatures, public sources, and LLM-extracted context.

The graph is *bidirectionally useful*: the user can query it ("who do I know who..."), and their agent can query it as part of larger workflows (drafting an email, preparing for a meeting, sourcing candidates).

---

## 3. The Wedge: How to Make the First 10 Users Love It

The first 10 users need a single-player experience so good they would use it if no one else ever did. The network effect is a future moat, not a launch moat.

### Killer first-session experience

A user who has just OAuthed into Gmail should, within 60 seconds, get an answer to a question LinkedIn cannot answer for them. Examples that prove the value:

- **"Show me everyone I've emailed at least 5 times in the last year who I haven't talked to in the last 90 days."** This is the warm-but-cooling list, and it's immediately actionable.
- **"Which of my contacts changed jobs recently?"** Job-change detection from email signatures + public sources. This is what Champify charges thousands per year for, and we deliver it free in 60 seconds.
- **"What VCs do I know?"** Pull all contacts whose current company is in a maintained list of VC firms. Show me a list. Most users have never seen this view of their own network.
- **"Who in my network lives in Berlin?"** (or any city they care about). Pulls from email signatures, calendar locations, mentioned in threads.

The bet: every user has at least one of these queries that delights them, and the agent surfaces it on first run.

### The first 10 users

Recruit them directly. Founders and operators with rich email histories and active networks. They will:

- Validate that the entity resolution is good enough to be trusted.
- Surface the queries we did not anticipate.
- Test the graph density required before cross-user features start paying off.
- Give honest feedback about whether the value is real or merely interesting.

Pick users with diverse network shapes: a VC, a senior engineer, a journalist, a salesperson, an indie founder, a community organizer, an academic, a recruiter, a job seeker, a real-estate agent. If the product works for all of them, the use case is general.

### The first 1000 users

The first 1000 should come from agent-initiated discovery. The mechanism:

1. We work with Anthropic, OpenAI, and Google to get NewCo listed in their MCP/connector directories with a clear, trustworthy description.
2. We seed a few high-quality blog posts, podcast appearances, and Reddit/HN discussions so that when an agent web-searches for "find people in my network" or "build a graph from my Gmail," NewCo comes up.
3. The skill.md is excellent. When an agent reads it, the install flow is obvious and the OAuth experience is frictionless.
4. We do not do paid acquisition. The signal we want is that the agent surfaces us organically because we are genuinely the right answer.

### What works pre-network

Even before any cross-user features exist, the single-player graph answers real questions:

| User type | First-session value (no network needed) |
|-----------|-----------------------------------------|
| Job seeker | "Who in my contacts works at [target company]?" |
| Salesperson | "Who do I already know at this account I'm trying to break into?" |
| Founder fundraising | "Which VCs are in my graph and how strong is each tie?" |
| Recruiter | "Who in my network does the kind of role I'm hiring for?" |
| New parent | "Who in my network has kids in [school district]?" |
| Mover | "Who do I know in [new city]?" |
| Anyone | "Who haven't I talked to in a year but used to be close to?" |
| Anyone | "Who in my network had a major life change recently?" (new job, new company, new city) |

Each of these is the kind of answer that earns a user's loyalty in one session.

### The bottoms-up team unlock

The most powerful viral mechanic the product has: when multiple people from the same company are using NewCo for personal reasons, they should be able to pool their graphs into a free team view with one click.

This is the use case The Swarm has built a $99-$10k/month B2B business around: "who at my company knows someone at the target account?" We give it away for free, distributed through consumer-style adoption.

How it works:

1. User A from acme.com signs up for personal use (job search, prep for a meeting, finding a contractor, whatever brought them in). Their personal graph populates.
2. The system detects that other users with @acme.com addresses are already on NewCo.
3. NewCo surfaces a prompt (through the agent or in the settings UI): "4 of your colleagues are also on NewCo. Want to pool your graphs into a team view? Each person controls what they share."
4. Each colleague gets the same prompt. If they opt in, their graphs are queryable together (with per-user privacy controls) under a shared team workspace.
5. Anyone at the company can now ask "who at our company knows someone at Acme Corp" or "who has the strongest tie to Stripe."

This is The Swarm's flagship feature, free, with no admin, no procurement, no contract, no SSO setup. A team of five SDRs can spin it up in 10 minutes.

Why this is a uniquely good consumer-to-team motion:

- **No buyer.** It is not sold to a CRO. It is discovered by an individual contributor, then organically pulled in by colleagues. By the time the CRO hears about it, the team is already using it.
- **No commitment.** Each user controls their own graph. Leaving the team workspace does not delete their personal graph. There is no enterprise contract to unwind.
- **Real value at small scale.** Two colleagues pooling networks is already useful for a startup. Five is great. Twenty is The Swarm at enterprise scale.
- **Free is the wedge, not a discount.** The Swarm has to charge to survive. We do not, because the team feature is just an opt-in overlay on already-existing personal graphs that we operate at near-zero marginal cost.

Specific user segments this is killer for:
- **Early-stage startups.** A founding team of 5-15 with rich personal networks. The collective graph is enormous relative to headcount. Best fit for fundraising, sales, hiring, partnerships.
- **Guerrilla marketing teams.** Small marketing/BD teams trying to reach press, influencers, partners. Pooling their personal networks unlocks paths they would never find individually.
- **Investment firms.** Especially smaller ones (seed funds, angel groups) without the budget for Affinity or The Swarm. The whole partnership pooling their networks is genuinely transformative.
- **Sales teams in companies that haven't bought enterprise tooling yet.** They organically start using it for warm-intro discovery and the value is obvious within a week.
- **Job-seekers who all left the same company.** A laid-off cohort can pool their networks to find new opportunities together.
- **Alumni groups, founder cohorts, accelerator batches.** Any cluster of people who already trust each other and have overlapping interests.

This adoption path also creates the most natural monetization later: once teams hit a certain size or want admin/SSO/audit/seat-based features, that is the paid tier. The free version is genuinely useful forever; the paid version adds enterprise plumbing.

---

## 4. Distribution: How Users Find It

### The core distribution thesis

Users do not find NewCo. Their agent does. The user has a need, asks their agent, and the agent surfaces NewCo as the answer. The entire user acquisition strategy is making sure that when an agent is faced with a graph-shaped question, NewCo is the obvious answer.

This requires three distinct surfaces to work:

1. **In-app connector marketplaces.** Claude Connectors, ChatGPT Apps, Gemini Tools. We need to be listed, well-described, and trusted. Anthropic and OpenAI both vet these; the consumer-first, free-forever framing should help us get accepted.
2. **Organic agent web search.** When an agent runs a web search for "find people I know who work at X" or "build a network graph from my email," the top results should describe NewCo. This is achieved through high-quality blog content, developer docs, and presence in the right communities (HN, IndieHackers, dev.to, RevOps Slack).
3. **Skill/MCP registries.** smithery.ai, glama.ai, the official MCP registry, PulseMCP, Anthropic's MCP directory. Being indexed and discoverable from these is part of the agent's normal lookup behavior.

### The discovery scenarios

**Scenario A: Job search.** User says to Claude: "I'm thinking about leaving my job and want to explore startups working on climate. Can you help me figure out who to talk to?" Claude needs to know who's in the user's network. It searches, finds NewCo, suggests it. The user OAuths, the graph populates, Claude returns a list of climate-startup founders in the user's network ranked by tie strength.

**Scenario B: Local services.** User says to ChatGPT: "I need a plumber and I'd rather use someone a friend recommends. Anyone in my contacts I should ask?" ChatGPT realizes it needs to know who lives near the user and might have a recommendation. It surfaces NewCo, the graph builds, the response is "Three people in your network live within 10 miles of you. Sarah recommended a plumber in an email last March. Want me to draft a message?"

**Scenario C: Sales prospecting.** User says to Gemini: "I'm trying to close a deal with Acme Corp. Who do I already know there?" Gemini surfaces NewCo, the graph builds, the answer is "You've corresponded with three people at Acme. One of them, Jamie Lee, you exchanged 14 emails with last year about a partnership. Strongest existing tie."

**Scenario D: Community / personal.** User says to Claude: "I'm moving to Austin. Who do I know there?" The graph builds, the answer is "Six contacts list Austin as their location. Two of them you haven't talked to in over a year. Three are people you worked with previously. Want me to draft reconnection emails?"

In every case, the user did not come looking for a "personal CRM." They had a real, urgent need, and the agent recognized that the missing piece was a graph and went to get one.

### Why this discovery model works structurally

The Swarm cannot do this. They need a paid B2B sale. A user asking Claude "help me find someone to fix my roof" would never get The Swarm suggested because The Swarm is not a free, instant tool an agent can install on the user's behalf.

NewCo can do this because:

- It is free, so the agent does not have to ask the user to pay first.
- It is fast to install (one OAuth, no manual config), so the agent can complete the workflow in the same session.
- It is broadly useful (not just sales, not just recruiting), so it gets surfaced across diverse user intents.
- It is trustworthy (clear consumer pact on data handling, no resale, user owns their graph), so users say yes when the agent asks for OAuth access.

---

## 5. Scaling Beyond Single-Player

### Phase 1: Single-player (first 1000 users)

The product is fully useful with a graph of one. The user's own email is enough to answer most queries. Cross-user features are not on the critical path for early value.

### Phase 2: Consented cross-user queries (1000-10,000 users)

The graph is centralized (one database, NewCo-operated) for reliability and consistency. Cross-user value comes from consent, not architecture. When User A's agent wants to find a path to a target person, the system can answer based on the union of opted-in users' graphs, with each user controlling what is queryable about them. Defaults are private; the user (through their agent) chooses what to expose.

This is structurally Signal-like: centralized service, strong consent and data-control commitments, end-user trust earned through policy and product rather than through distributed architecture.

### Phase 3: Cross-graph queries at scale (10,000+ users)

At scale, NewCo offers an opt-in index for cross-user queries. Users can choose to expose specific attributes (current employer, city, areas of expertise, willingness to take meetings about specific topics) to a queryable layer. This makes "find me anyone who works at Stripe and is open to coffee" possible.

The cross-graph layer is what eventually displaces LinkedIn for warm-intro use cases. But it depends on first having enough single-player value to get to 10,000 users, and on the data-handling commitments being credible enough that users actually opt in.

### Why centralized

Federation has consistently produced mediocre consumer experiences (Mastodon, Matrix, Diaspora, even email). The products users actually trust at scale (Signal, Stripe, Wikipedia, 1Password) are centralized with strong policy and product commitments. Trust comes from governance and posture, not architecture.

What we borrow from the federation playbook anyway: scoped permissions for third-party apps (built into MCP), verifiable credentials for third-party-issued claims (W3C VC standard), full data export in a real standard format, and a consent layer where the user's agent mediates third-party access. Centralized data, open ecosystem.

---

## 6. Critical Design Constraints

### Trust

The product asks for Gmail OAuth access. This is the single highest-friction step in the entire experience and the single highest-stakes promise the project makes.

Requirements:
- All processing happens in user-isolated infrastructure. No cross-user data leakage in the population pipeline.
- The graph is the user's. They can export it, delete it, or take it elsewhere.
- The company commits in its terms of service to never selling the graph, never training general-purpose models on it, and never commercializing user data without explicit opt-in. This is a load-bearing promise.
- Transparency reports, open-source core, public roadmap.
- Clear policy on government requests and law enforcement access.
- SOC 2 from day one, not as an afterthought.

### Entity resolution quality

The product is only as useful as its dedupe. If "Sarah Chen" appears as three different people, the user loses trust within the first session.

Requirements:
- LLM-based resolution that combines email, name, domain, signature, and behavioral signals.
- A user-facing "merge these" / "split these" tool for corrections.
- Active learning: corrections feed back into the resolution model for that user.
- Probabilistic match scores exposed to the agent so it can ask the user when uncertain.

### Query latency

The agent expects sub-second answers to graph queries during a conversation. The user is talking to Claude in real time.

Requirements:
- Pre-computed indexes for common query shapes ("who works at X", "who lives in Y", "warmest tie to Z").
- Incremental population: first 100 contacts available within 30 seconds, full graph by background completion.
- Local-or-edge query execution for sensitive data, with the user's agent never having to send graph contents to a third party.

### Cross-user query safety

Phase 2/3 cross-user queries create new attack surfaces (probing, inference attacks, social engineering of agents).

Requirements:
- Cross-user queries are rate-limited per requesting user.
- Agents enforce explicit user consent for outbound queries on the user's behalf.
- A "ghost mode" that lets users opt out of being queried entirely.

---

## 7. Monetization and Sustainability

### What stays free forever

The base consumer experience. The graph itself. The MCP server. Querying your own graph through any agent. The cross-user query layer (basic tier). These are free for individual users, full stop.

The promise is load-bearing. "Free forever for consumers" is the entire reason agents and users trust the product enough to grant deep data access. Reneging on this breaks the business.

### Where revenue comes from

There are several plausible revenue layers, all sitting above the free consumer base:

**1. B2B / team tier.** Companies that want to pool their employees' graphs for collective use (the Swarm use case) pay per seat. The data each employee contributes stays under their personal control, but the company gets shared visibility into the union. This is the most obvious revenue line and probably the first one to ship.

**2. Premium consumer features.** A paid tier for power users that adds things like: unlimited cross-user queries, advanced job-change alerts, deeper enrichment, scheduled reports, priority entity-resolution support. Modeled on Superhuman or 1Password rather than LinkedIn Premium.

**3. Vertical applications.** Separate products built on top of the graph, monetized in their own categories:
- Recruiting product (companies pay to reach opted-in candidates)
- Sales prospecting product (companies pay for warm-intro path-finding)
- Fundraising tool (founders pay for VC-graph access)
- Real-estate matching (agents pay for local-graph features)
- Journalist source-finder (newsrooms pay for expertise search)

Each is a real product with real pricing power. The consumer never sees these unless they choose to opt in (e.g., flipping a switch that says "I'm open to recruiter outreach").

**4. API and platform fees.** Third-party developers building agentic products can pay to query the graph at scale, the way Mapbox pays for OpenStreetMap-derived infrastructure.

### The structural argument

The reason this works as a for-profit while staying free for consumers is the same reason it works for Spotify (free tier subsidized by ads and premium), Notion (free for personal, paid for teams), and 1Password (free for one device, paid for multi). The consumer free tier is the acquisition and trust mechanism. The revenue comes from B2B and from the small percentage of consumers who upgrade for power features, and most importantly from the vertical applications layered on top.

Crucially, none of the revenue paths require selling the graph or violating the consumer-data pact. They are all about charging for *capabilities and access*, not for *data exfiltration*.

### Funding to get there

Venture-funded, but with a clear thesis that the company should look more like Signal-meets-Notion than like LinkedIn-meets-Salesforce. Investors who understand consumer-network-effect plays with a delayed monetization curve. Probably 2-3 years of focused consumer growth before turning on serious revenue.

---

## 8. Open Questions

Things to resolve before we commit to v1:

1. **The brand.** Should it sound like infrastructure (boring, trusted) or like a consumer product (fun, memorable)? The Signal/1Password/Notion model suggests "trusted utility with a consumer-friendly face."
2. **What about LinkedIn data?** Do we allow optional LinkedIn import where users have it, or refuse on principle to depend on LinkedIn at all? The latter is purer but loses some richness.
3. **How explicit do we make the "free forever for consumers" promise in the agent's pitch?** Too explicit and it sounds defensive. Too implicit and we lose the trust advantage.
4. **What's the relationship to existing players?** Could we acqui-hire or partner with Connect the Dots? License The Swarm's data layer? Or stay clean and build alone?
5. **How do we prevent abuse?** Stalkers, doxxers, ICE, abusive ex-partners. The fact that this is a graph of real people in real life means we need a clear abuse-prevention story before we ship cross-user queries.
6. **Which monetization layer ships first?** Premium consumer, B2B team tier, or a single vertical (recruiting being the most obvious)? Each has different unit economics and different signal-to-noise on whether the consumer growth is real.
7. **What's the data-handling pact?** The "we will never do X" promises need to be specific enough to be trustworthy and durable enough to survive growth pressure. Worth drafting these explicitly and treating them as part of the product, not just legal boilerplate.
8. **Who's the right co-founder profile?** Consumer-first growth muscle plus deep technical chops on entity resolution and graph systems. Different from a standard B2B SaaS team.

---

*End of v0.1. Looking forward to iterating.*
