/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface GuideApproach {
  readonly name: string;
  readonly summary: string;
  readonly pros: readonly string[];
  readonly cons: readonly string[];
}

export interface GuideSolutionStep {
  readonly title: string;
  readonly description: string;
}

export interface FaqItem {
  readonly question: string;
  readonly answer: string;
}

export interface ExternalReference {
  readonly label: string;
  readonly url: string;
}

export interface GuidePageData {
  readonly slug: string;
  readonly targetKeyword: string;
  readonly pageTitle: string;
  readonly pageDescription: string;
  readonly heroHeading: string;
  readonly heroSubtitle: string;
  readonly lastUpdated: string;
  readonly problemHeading: string;
  readonly problemParagraphs: readonly string[];
  readonly approaches: readonly GuideApproach[];
  readonly solutionHeading: string;
  readonly solutionIntro: string;
  readonly solutionSteps: readonly GuideSolutionStep[];
  readonly references: readonly ExternalReference[];
  readonly faqs: readonly FaqItem[];
}

export interface RelatedGuideLink {
  readonly slug: string;
  readonly title: string;
  readonly description: string;
}

/* ------------------------------------------------------------------ */
/*  Pages                                                              */
/* ------------------------------------------------------------------ */

const PAGES: readonly GuidePageData[] = [
  /* ---- Connect Claude to LinkedIn ---- */
  {
    slug: "connect-claude-to-linkedin",
    targetKeyword: "Claude connector for LinkedIn",
    pageTitle: "How to Connect Claude to Your LinkedIn Network",
    pageDescription:
      "LinkedIn blocks AI from reading your contacts. Learn why the Claude connector for LinkedIn doesn't exist officially — and how to connect Claude to your network safely with ContactGraph.",
    heroHeading:
      "There is no official Claude connector for LinkedIn — here\u2019s what to do instead.",
    heroSubtitle:
      "Millions of people search for a way to connect Claude to LinkedIn every month. LinkedIn doesn\u2019t offer consumer API access to your contacts, and scraping tools risk account suspension. ContactGraph lets you export your network once and connect Claude to it via MCP — no scraping, no subscription, no TOS violations.",
    lastUpdated: "June 2026",
    problemHeading: "Why you can\u2019t connect Claude to LinkedIn directly",
    problemParagraphs: [
      "When you search for a Claude connector for LinkedIn, you\u2019re looking for something that should be simple: let an AI assistant read your professional contacts, search your network, and help with outreach, recruiting, or job search. LinkedIn makes this deliberately hard.",
      "LinkedIn\u2019s official Consumer API is restricted to basic profile fields and posting — it does not expose your connection list, inbox, or search results to third-party developers without enterprise partner approval. That approval process can take months and costs tens of thousands of dollars per year.",
      "The community-built alternatives fall into two camps, both with serious drawbacks. Browser-scraping MCP servers hijack your logged-in session to read LinkedIn pages — a direct violation of LinkedIn\u2019s User Agreement that can trigger account restrictions. OAuth-based MCP servers use LinkedIn\u2019s official API but are limited to posting content; they cannot search your network or read your contacts.",
      "Paid services like ConnectSafely and LinkupAPI charge $10+/month and still operate in a gray area — automating actions LinkedIn explicitly prohibits for consumer accounts, like unsolicited outreach at scale.",
    ],
    approaches: [
      {
        name: "Browser-scraping MCP servers",
        summary:
          "Open-source MCP servers that automate a logged-in browser session to read profiles, jobs, and messages.",
        pros: [
          "Broad access to LinkedIn\u2019s web interface",
          "No LinkedIn Developer app required",
          "Works with Claude Desktop and Claude Code",
        ],
        cons: [
          "Violates LinkedIn\u2019s User Agreement",
          "High risk of account restriction or suspension",
          "Breaks when LinkedIn changes its UI",
          "Requires keeping a browser session alive",
        ],
      },
      {
        name: "OAuth posting MCP servers",
        summary:
          "MCP servers that use LinkedIn\u2019s official OAuth API — primarily for creating and scheduling posts.",
        pros: [
          "Uses LinkedIn\u2019s sanctioned API",
          "Low account-risk for posting",
          "Straightforward Claude Desktop setup",
        ],
        cons: [
          "Cannot read your connection list",
          "Cannot search your network",
          "No job-search or outreach capabilities",
          "Requires LinkedIn Developer app credentials",
        ],
      },
      {
        name: "Paid LinkedIn automation services",
        summary:
          "SaaS platforms that provide remote MCP endpoints for lead generation, messaging, and engagement.",
        pros: [
          "No-code setup in Claude Desktop",
          "Handles authentication and token refresh",
          "Supports outreach and lead search workflows",
        ],
        cons: [
          "$10\u201350+/month per account",
          "Proprietary — your data flows through a third party",
          "Automated outreach may still violate LinkedIn TOS",
          "Vendor lock-in with no data export",
        ],
      },
      {
        name: "ContactGraph (export + MCP)",
        summary:
          "Export your LinkedIn connections once, merge them with phone contacts into your own graph, and query everything via ContactGraph\u2019s MCP server.",
        pros: [
          "No scraping — uses LinkedIn\u2019s official data export",
          "No ongoing LinkedIn API dependency",
          "Full network search by company, role, and industry",
          "Open source, free, nonprofit — you own your data",
          "Works with Claude, ChatGPT, Gemini, and any MCP client",
        ],
        cons: [
          "One-time manual export required",
          "Snapshot-based — re-export to refresh connections",
          "Focused on your network, not LinkedIn\u2019s full member directory",
        ],
      },
    ],
    solutionHeading: "How to connect Claude to your LinkedIn network with ContactGraph",
    solutionIntro:
      "Instead of fighting LinkedIn\u2019s API restrictions, export the data LinkedIn already lets you download and connect Claude to it through ContactGraph\u2019s MCP server. Setup takes about five minutes.",
    solutionSteps: [
      {
        title: "Export your LinkedIn connections",
        description:
          "In LinkedIn, go to Settings \u2192 Data Privacy \u2192 Get a copy of your data, and download your Connections.csv file. This is LinkedIn\u2019s official export — fully permitted and safe.",
      },
      {
        title: "Upload to ContactGraph",
        description:
          "Sign up at contactgraph.ai (free) and upload your Connections.csv along with your phone contacts. ContactGraph merges everything into a single searchable relationship graph.",
      },
      {
        title: "Add the ContactGraph MCP server to Claude",
        description:
          "In Claude Desktop, go to Settings \u2192 Connectors \u2192 Add Custom Connection and paste your ContactGraph MCP URL. Or run the MCP server locally from the open-source repo on GitHub.",
      },
      {
        title: "Ask Claude about your network",
        description:
          "Prompt Claude with questions like \u201cWho do I know at Stripe?\u201d, \u201cFind warm paths to AI startups that are hiring\u201d, or \u201cDraft an intro request to my contact at Anthropic.\u201d Claude queries your graph via MCP and responds with real connection data.",
      },
    ],
    references: [
      {
        label: "LinkedIn API documentation",
        url: "https://learn.microsoft.com/en-us/linkedin/",
      },
      {
        label: "LinkedIn User Agreement (automation policy)",
        url: "https://www.linkedin.com/legal/user-agreement",
      },
      {
        label: "Model Context Protocol (MCP) specification",
        url: "https://modelcontextprotocol.io/",
      },
    ],
    faqs: [
      {
        question: "Is there an official Claude connector for LinkedIn?",
        answer:
          "No. Anthropic does not offer a built-in LinkedIn connector, and LinkedIn does not provide consumer API access for reading contacts or searching networks. Any tool claiming to be an official Claude-LinkedIn connector is using unofficial methods.",
      },
      {
        question: "Can I connect Claude to LinkedIn without risking my account?",
        answer:
          "Yes. Export your LinkedIn connections using LinkedIn\u2019s official data export, upload them to ContactGraph, and connect Claude via MCP. This approach uses data LinkedIn explicitly lets you download — no scraping, no session hijacking, no TOS violations.",
      },
      {
        question: "What can Claude do with my LinkedIn data through ContactGraph?",
        answer:
          "Claude can search your network by company, role, or industry; find warm introduction paths to employers; match open job listings to people you know; draft outreach messages based on real connection context; and answer questions about your professional relationships.",
      },
      {
        question: "Do I need a LinkedIn Developer app to use ContactGraph?",
        answer:
          "No. ContactGraph uses LinkedIn\u2019s standard data export (Connections.csv), not the API. You don\u2019t need developer credentials, OAuth tokens, or partner approval.",
      },
      {
        question: "How is this different from LinkedIn MCP servers on GitHub?",
        answer:
          "Most GitHub LinkedIn MCP servers either scrape LinkedIn\u2019s website (risking your account) or only support posting via OAuth (can\u2019t read your network). ContactGraph\u2019s MCP server queries your exported contact graph — giving Claude full network search without touching LinkedIn\u2019s live platform.",
      },
      {
        question: "Does ContactGraph work with Claude Code and Claude Desktop?",
        answer:
          "Yes. ContactGraph runs as a standard MCP server compatible with Claude Desktop, Claude Code, Cursor, and any MCP-compatible AI client. Add it as a custom connector or run it locally.",
      },
    ],
  },

  /* ---- LinkedIn MCP Server for Job Search ---- */
  {
    slug: "linkedin-mcp-server-job-search",
    targetKeyword: "LinkedIn MCP server",
    pageTitle: "LinkedIn MCP Server for Job Search",
    pageDescription:
      "Most LinkedIn MCP servers let you post or scrape profiles. ContactGraph\u2019s LinkedIn MCP server is built for job search — find warm introductions at companies that are hiring through your actual network.",
    heroHeading:
      "The LinkedIn MCP server built for job search — not posting.",
    heroSubtitle:
      "Developers are building LinkedIn MCP servers to let AI tools read profiles and post content. ContactGraph\u2019s MCP server does something different: it connects Claude to your exported LinkedIn connections so you can find warm paths into companies that are hiring — without scraping or account risk.",
    lastUpdated: "June 2026",
    problemHeading: "Why existing LinkedIn MCP servers don\u2019t help with job search",
    problemParagraphs: [
      "Search interest in \u201clinkedin mcp\u201d and \u201clinkedin mcp server\u201d has surged as professionals try to connect AI assistants to their LinkedIn data. The most popular open-source LinkedIn MCP servers (with thousands of GitHub stars) focus on two use cases: posting content and scraping profiles through a browser session.",
      "Neither helps with the use case most job seekers actually need: searching your own network to find who you know at a company with open roles. Scraping MCP servers can technically search LinkedIn, but they operate outside LinkedIn\u2019s terms and risk your account. Posting MCP servers use the official API but can\u2019t read your connection list at all.",
      "For job search, what you need is an MCP server that knows your contacts, knows which companies are hiring, and can match the two. That requires owning your network data — not renting access to LinkedIn\u2019s platform.",
    ],
    approaches: [
      {
        name: "Profile-scraping MCP servers",
        summary:
          "e.g. stickerdaniel/linkedin-mcp-server — reads LinkedIn through browser automation.",
        pros: [
          "Can search people, companies, and jobs on LinkedIn",
          "One-click Claude Desktop install (.mcpb bundle)",
          "Active open-source community",
        ],
        cons: [
          "Scraping violates LinkedIn TOS",
          "Account suspension risk",
          "Doesn\u2019t know YOUR connections — searches all of LinkedIn",
          "No warm-intro path analysis",
        ],
      },
      {
        name: "OAuth posting MCP servers",
        summary:
          "e.g. gacabartosz/linkedin-mcp-server — posts, schedules, and manages content via official API.",
        pros: [
          "Compliant with LinkedIn\u2019s posting API",
          "Rich posting features (images, scheduling, templates)",
          "24+ tools for content management",
        ],
        cons: [
          "Zero job-search capabilities",
          "Cannot access your connection list",
          "Requires LinkedIn Developer app setup",
          "Focused on content marketing, not networking",
        ],
      },
      {
        name: "ContactGraph MCP server",
        summary:
          "Queries your exported LinkedIn connections merged with phone contacts — matched to live job listings.",
        pros: [
          "Built specifically for warm-path job search",
          "Shows open roles at companies where you know someone",
          "Enriches contacts with current employer and role",
          "Open source MCP server — free, no API keys required",
          "No scraping, no account risk",
        ],
        cons: [
          "Requires one-time LinkedIn data export",
          "Network data is a snapshot until you re-export",
          "Not designed for posting to LinkedIn",
        ],
      },
    ],
    solutionHeading: "Set up ContactGraph as your LinkedIn MCP server for job search",
    solutionIntro:
      "ContactGraph\u2019s MCP server exposes your professional network as structured tools that Claude can query. Unlike scraping servers, it works entirely from data you own.",
    solutionSteps: [
      {
        title: "Export and upload your LinkedIn connections",
        description:
          "Download Connections.csv from LinkedIn\u2019s data export and upload it to ContactGraph along with your phone contacts. ContactGraph enriches each contact with current employer, title, and industry.",
      },
      {
        title: "Connect the MCP server to Claude",
        description:
          "Add ContactGraph as a custom MCP connector in Claude Desktop, or run the server locally via Claude Code. The server exposes tools for searching contacts, finding companies, and matching jobs.",
      },
      {
        title: "Search for warm paths to open roles",
        description:
          "Ask Claude: \u201cWhich companies in my network are hiring for engineering roles?\u201d or \u201cWho can introduce me to someone at Notion?\u201d Claude queries your graph and returns actionable warm-intro paths.",
      },
      {
        title: "Act on warm introductions",
        description:
          "Use Claude to draft personalized outreach based on your actual relationship context — not generic templates. A warm intro through someone you know beats a cold application every time.",
      },
    ],
    references: [
      {
        label: "ContactGraph MCP server documentation",
        url: "https://api.contactgraph.ai/skill.md",
      },
      {
        label: "Model Context Protocol specification",
        url: "https://modelcontextprotocol.io/",
      },
      {
        label: "LinkedIn data export instructions",
        url: "https://www.linkedin.com/help/linkedin/answer/a1339364",
      },
    ],
    faqs: [
      {
        question: "What is a LinkedIn MCP server?",
        answer:
          "A LinkedIn MCP server is a Model Context Protocol server that gives AI assistants like Claude access to LinkedIn data and actions. MCP is an open standard by Anthropic that lets AI tools call external APIs through a standardized interface.",
      },
      {
        question: "Which LinkedIn MCP server is best for job search?",
        answer:
          "For job search, ContactGraph\u2019s MCP server is the best fit because it searches your actual connections and matches them to open job listings. Scraping-based servers search all of LinkedIn (not your network specifically) and risk account suspension. Posting servers can\u2019t search contacts at all.",
      },
      {
        question: "Can I use a LinkedIn MCP server with Claude Desktop?",
        answer:
          "Yes. Both scraping MCP servers and ContactGraph work with Claude Desktop via custom connectors or local MCP configuration. ContactGraph also works with Claude Code, Cursor, and any MCP-compatible client.",
      },
      {
        question: "Is it safe to use a LinkedIn MCP server?",
        answer:
          "It depends on the approach. Scraping-based servers violate LinkedIn\u2019s terms and can get your account restricted. ContactGraph uses LinkedIn\u2019s official data export — the same file LinkedIn lets every user download — so there is no platform risk.",
      },
      {
        question: "How does ContactGraph find jobs to match with my network?",
        answer:
          "ContactGraph aggregates open roles from across the web and matches them to companies where you have a contact in your graph. Every job listing comes with a warm path — someone you know who can make an introduction.",
      },
      {
        question: "Do I need to pay for a LinkedIn MCP server?",
        answer:
          "ContactGraph is free — open source, nonprofit, no subscription. Many alternatives charge $10\u201350/month (ConnectSafely, LinkupAPI, Composio) or require you to run fragile scraping infrastructure yourself.",
      },
    ],
  },

  /* ---- AI with LinkedIn Contacts ---- */
  {
    slug: "ai-linkedin-contacts",
    targetKeyword: "AI LinkedIn contacts",
    pageTitle: "Use AI with Your LinkedIn Contacts",
    pageDescription:
      "Your LinkedIn contacts are locked inside LinkedIn\u2019s walled garden. Learn how to use AI with your LinkedIn contacts — export once, own your data, and connect any AI tool via MCP.",
    heroHeading:
      "Your LinkedIn contacts should work with any AI — not just LinkedIn\u2019s.",
    heroSubtitle:
      "LinkedIn built a trillion-dollar business on your professional relationships — then locked that data inside their platform. You can\u2019t use AI to search your own network, find warm introductions, or automate outreach without violating their terms. ContactGraph gives you back ownership of your contact data so any AI tool can help you use it.",
    lastUpdated: "June 2026",
    problemHeading: "Why your LinkedIn contacts are trapped",
    problemParagraphs: [
      "You\u2019ve spent years building a professional network on LinkedIn — hundreds or thousands of connections representing real relationships. But that data isn\u2019t yours in any meaningful sense. LinkedIn controls how you access it, what tools can use it, and what you can do with it.",
      "Want to ask Claude \u201cwho do I know in fintech?\u201d LinkedIn says no — there\u2019s no consumer API for that. Want to use AI to draft personalized outreach based on your connection history? LinkedIn\u2019s automation policies prohibit it. Want to merge your LinkedIn contacts with your phone contacts into one searchable graph? LinkedIn actively prevents it.",
      "The result is a massive gap between what AI can do and what LinkedIn allows. Professionals in sales, recruiting, job seeking, and business development are searching for ways to use AI with their LinkedIn contacts — and finding that the platform they trusted with their network won\u2019t let them.",
      "This isn\u2019t a technology problem. LinkedIn could open an API tomorrow. It\u2019s a business model problem — LinkedIn monetizes your network through Sales Navigator, Recruiter, and Premium subscriptions, and giving you free AI access would undermine that.",
    ],
    approaches: [
      {
        name: "Stay inside LinkedIn\u2019s ecosystem",
        summary:
          "Use LinkedIn Premium, Sales Navigator, or Recruiter — LinkedIn\u2019s own (expensive) tools for network search.",
        pros: [
          "Official, fully supported by LinkedIn",
          "Real-time data — always current",
          "Integrated messaging and InMail",
        ],
        cons: [
          "Premium: $30\u201360/month, limited search",
          "Sales Navigator: $100+/month",
          "No AI agent or MCP integration",
          "Data locked in LinkedIn — no export for AI tools",
        ],
      },
      {
        name: "Scrape or automate against LinkedIn",
        summary:
          "Browser extensions, headless browsers, and MCP servers that simulate human browsing.",
        pros: [
          "Access to LinkedIn\u2019s full interface",
          "Can automate search, messaging, and outreach",
          "Works with AI through MCP bridges",
        ],
        cons: [
          "Explicitly prohibited by LinkedIn TOS",
          "Accounts get restricted or banned regularly",
          "Fragile — breaks on every LinkedIn UI change",
          "Ethical concerns around unsolicited automation",
        ],
      },
      {
        name: "Export and own your data (ContactGraph)",
        summary:
          "Download your LinkedIn connections, merge with other contact sources, and use any AI tool via MCP.",
        pros: [
          "You own your data — export or delete anytime",
          "Works with Claude, ChatGPT, Gemini, and any MCP client",
          "Merges LinkedIn + phone + shared graphs",
          "Open source, nonprofit, free forever",
          "Enriches contacts with current employer and role",
        ],
        cons: [
          "Snapshot model — re-export to refresh",
          "Doesn\u2019t replace LinkedIn messaging",
          "One-time setup required",
        ],
      },
    ],
    solutionHeading: "How to use AI with your LinkedIn contacts today",
    solutionIntro:
      "You don\u2019t need LinkedIn\u2019s permission to use AI with your own professional relationships. Export your data, own your graph, and connect any AI tool.",
    solutionSteps: [
      {
        title: "Export your professional network",
        description:
          "Download your LinkedIn Connections.csv (Settings \u2192 Data Privacy \u2192 Get a copy of your data). Optionally export your phone contacts too. These are your relationships — LinkedIn is just one place you stored them.",
      },
      {
        title: "Build your unified contact graph",
        description:
          "Upload everything to ContactGraph. It deduplicates, enriches contacts with current employer and role from public data, and builds a searchable relationship graph you fully own.",
      },
      {
        title: "Connect your preferred AI tool",
        description:
          "ContactGraph runs as an MCP server, so Claude, ChatGPT, Gemini, Cursor, and terminal-based agents can all query your network. No vendor lock-in — switch AI tools anytime.",
      },
      {
        title: "Put your network to work",
        description:
          "Use AI for what it\u2019s actually good at: finding patterns in your network, identifying warm paths, drafting personalized messages, and matching opportunities to relationships. Your contacts, your AI, your rules.",
      },
    ],
    references: [
      {
        label: "LinkedIn data portability (official export)",
        url: "https://www.linkedin.com/help/linkedin/answer/a1339364",
      },
      {
        label: "ContactGraph on GitHub (open source)",
        url: "https://github.com/ContactGraph/contactgraph",
      },
      {
        label: "Model Context Protocol",
        url: "https://modelcontextprotocol.io/",
      },
    ],
    faqs: [
      {
        question: "Can I use AI with my LinkedIn contacts legally?",
        answer:
          "Yes. LinkedIn provides an official data export that includes your connections. Using that exported data with AI tools like Claude is fully within your rights. What LinkedIn prohibits is automated scraping of their live platform — not using data they explicitly let you download.",
      },
      {
        question: "What AI tools work with exported LinkedIn contacts?",
        answer:
          "Any AI tool that supports MCP (Model Context Protocol) can query your ContactGraph network — including Claude Desktop, Claude Code, ChatGPT, Gemini, Cursor, and custom agents. ContactGraph also provides a skill.md for terminal-based AI workflows.",
      },
      {
        question: "Will using AI with my LinkedIn contacts get me banned?",
        answer:
          "Not if you use ContactGraph. It works from your exported data, not by automating actions on LinkedIn\u2019s platform. Scraping-based tools and automated outreach bots are what trigger account restrictions.",
      },
      {
        question: "How is ContactGraph different from LinkedIn Premium or Sales Navigator?",
        answer:
          "LinkedIn\u2019s paid tools keep your data locked on their platform with no AI integration. ContactGraph lets you own your network data and connect it to any AI tool via MCP — for free. It also merges phone contacts and shared graphs that LinkedIn never sees.",
      },
      {
        question: "Can ContactGraph help with sales, recruiting, and job seeking?",
        answer:
          "Yes. Sales professionals use it to find warm paths to prospects. Recruiters use it to identify mutual connections for candidate outreach. Job seekers use it to find who they know at companies with open roles. The same graph powers all three use cases.",
      },
      {
        question: "Is ContactGraph a nonprofit? Why does that matter?",
        answer:
          "Yes. ContactGraph is an open-source nonprofit with no investors and no data-selling business model. Your contact graph is never monetized, never shared, and never used to train AI models. You can self-host the entire stack from GitHub if you want full control.",
      },
    ],
  },
];

/* ------------------------------------------------------------------ */
/*  Lookup                                                             */
/* ------------------------------------------------------------------ */

const PAGE_MAP: ReadonlyMap<string, GuidePageData> = new Map(
  PAGES.map((p: GuidePageData) => [p.slug, p]),
);

export function getGuidePage(slug: string): GuidePageData | undefined {
  return PAGE_MAP.get(slug);
}

export function getAllGuideSlugs(): readonly string[] {
  return PAGES.map((p: GuidePageData) => p.slug);
}

export function getAllGuidePages(): readonly GuidePageData[] {
  return PAGES;
}

export function guidePageHref(slug: string): `/guides/${string}` {
  return `/guides/${slug}`;
}

/** Cross-link targets for the LinkedIn Jobs alternatives page. */
export const LINKEDIN_JOBS_RELATED_GUIDES: readonly RelatedGuideLink[] = [
  {
    slug: "connect-claude-to-linkedin",
    title: "How to Connect Claude to Your LinkedIn Network",
    description:
      "No official Claude connector exists — here\u2019s the safe way to connect Claude to your contacts via MCP.",
  },
  {
    slug: "linkedin-mcp-server-job-search",
    title: "LinkedIn MCP Server for Job Search",
    description:
      "Most LinkedIn MCP servers post or scrape. ContactGraph\u2019s is built for warm-path job search.",
  },
  {
    slug: "ai-linkedin-contacts",
    title: "Use AI with Your LinkedIn Contacts",
    description:
      "Export your network, own your data, and connect any AI tool to your professional relationships.",
  },
] as const;
