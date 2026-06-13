/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface Alternative {
  readonly name: string;
  readonly tagline: string;
  readonly pros: readonly string[];
  readonly cons: readonly string[];
}

interface ComparisonRow {
  readonly feature: string;
  readonly competitorValue: string;
  readonly contactGraphValue: string;
}

interface FaqItem {
  readonly question: string;
  readonly answer: string;
}

export interface AlternativesPageData {
  readonly slug: string;
  readonly competitor: string;
  readonly targetKeyword: string;
  readonly pageTitle: string;
  readonly pageDescription: string;
  readonly heroHeading: string;
  readonly heroSubtitle: string;
  readonly whoThisIsFor: readonly string[];
  readonly alternatives: readonly Alternative[];
  readonly comparisonRows: readonly ComparisonRow[];
  readonly faqs: readonly FaqItem[];
}

/* ------------------------------------------------------------------ */
/*  Pages                                                              */
/* ------------------------------------------------------------------ */

const PAGES: readonly AlternativesPageData[] = [
  /* ---- LinkedIn Jobs ---- */
  {
    slug: "linkedin-jobs-alternatives",
    competitor: "LinkedIn Jobs",
    targetKeyword: "LinkedIn Jobs alternatives",
    pageTitle: "Best LinkedIn Jobs Alternatives",
    pageDescription:
      "Looking for LinkedIn Jobs alternatives? Compare tools that help you find roles through warm introductions instead of cold applications.",
    heroHeading: "ContactGraph does what LinkedIn can\u2019t: get you an interview.",
    heroSubtitle:
      "LinkedIn Jobs shows you listings — ContactGraph shows you listings where you already know someone. Stop competing with 500 applicants and start reaching out to real connections.",
    whoThisIsFor: [
      "Job seekers tired of applying into the void on LinkedIn and never hearing back.",
      "Professionals who have a strong network but no easy way to search it by company or role.",
      "Anyone who believes a warm intro beats a cold application, every time.",
    ],
    alternatives: [
      {
        name: "ContactGraph",
        tagline:
          "Your personal relationship graph — find open roles at companies where you already know someone.",
        pros: [
          "Shows jobs matched to your actual network connections",
          "Merges phone contacts + LinkedIn into one searchable graph",
          "Open source, free, nonprofit — never sells your data",
          "Works as an MCP server for AI agents",
        ],
        cons: [
          "Requires a one-time contact export to get started",
          "Focused on warm-path job search, not general job browsing",
        ],
      },
      {
        name: "Indeed",
        tagline: "The largest general-purpose job board.",
        pros: [
          "Massive volume of listings across industries",
          "Free to use for job seekers",
          "Simple, no-frills search experience",
        ],
        cons: [
          "No networking features — purely transactional",
          "High competition per listing",
          "No way to surface warm connections at a company",
        ],
      },
      {
        name: "Wellfound (AngelList Talent)",
        tagline: "Startup-focused job board with direct founder messaging.",
        pros: [
          "Strong startup and early-stage company coverage",
          "Salary transparency on many listings",
          "Direct messaging to hiring managers",
        ],
        cons: [
          "Limited to the startup ecosystem",
          "No contact-graph or warm-intro features",
          "Smaller listing volume than major boards",
        ],
      },
    ],
    comparisonRows: [
      {
        feature: "Warm intro paths",
        competitorValue: "No",
        contactGraphValue: "Yes — matched to your real contacts",
      },
      {
        feature: "Network search",
        competitorValue: "Limited to LinkedIn connections",
        contactGraphValue: "Phone + LinkedIn + shared graphs",
      },
      {
        feature: "Data ownership",
        competitorValue: "Platform owns the graph",
        contactGraphValue: "You own everything, export anytime",
      },
      {
        feature: "Open source",
        competitorValue: "No",
        contactGraphValue: "Yes — full codebase on GitHub",
      },
      {
        feature: "AI agent support",
        competitorValue: "No",
        contactGraphValue: "MCP server for Claude, ChatGPT, Gemini",
      },
      {
        feature: "Price",
        competitorValue: "Free (Premium from $30/mo)",
        contactGraphValue: "Free forever",
      },
    ],
    faqs: [
      {
        question: "Can ContactGraph replace LinkedIn entirely?",
        answer:
          "ContactGraph replaces the job-search and networking part of LinkedIn — finding who you know at a company and surfacing relevant openings. It doesn't replace LinkedIn's social feed or recruiter tools.",
      },
      {
        question: "Do I need to delete my LinkedIn account?",
        answer:
          "No. ContactGraph works alongside LinkedIn. You export your LinkedIn connections once, and ContactGraph merges them with your phone contacts into a single searchable graph.",
      },
      {
        question: "How does ContactGraph find job listings?",
        answer:
          "ContactGraph aggregates open roles from across the web and matches them to companies where you already have a contact — so every listing comes with a warm path in.",
      },
      {
        question: "Is my contact data safe?",
        answer:
          "Yes. ContactGraph is open source, nonprofit, and never sells or shares your data. You can export or delete everything at any time.",
      },
    ],
  },

  /* ---- CareerShift ---- */
  {
    slug: "careershift-alternatives",
    competitor: "CareerShift",
    targetKeyword: "CareerShift alternatives",
    pageTitle: "Best CareerShift Alternatives",
    pageDescription:
      "Looking for CareerShift alternatives? Compare modern tools for finding contacts at target companies and landing warm introductions.",
    heroHeading: "CareerShift finds strangers. ContactGraph finds people who\u2019ll take your call.",
    heroSubtitle:
      "CareerShift helps you find contacts at companies. ContactGraph starts with the contacts you already have — and shows you open roles where those relationships can actually help.",
    whoThisIsFor: [
      "Career changers who want to leverage existing relationships, not cold-email strangers.",
      "Users looking for a free, modern alternative to CareerShift's paid subscription.",
      "People who prefer AI-powered network search over manual company-by-company lookups.",
    ],
    alternatives: [
      {
        name: "ContactGraph",
        tagline:
          "Build on relationships you already have instead of cold-prospecting new ones.",
        pros: [
          "Starts from your real network — people who already know you",
          "AI-enriched profiles with current employer, role, and industry",
          "Free and open source — no subscription required",
          "Second-degree search through shared graphs",
        ],
        cons: [
          "Doesn't cold-prospect contacts at companies you have no connection to",
          "Requires exporting your contacts to get started",
        ],
      },
      {
        name: "Hunter.io",
        tagline: "Find and verify professional email addresses.",
        pros: [
          "Large database of professional emails",
          "Email verification tools",
          "Chrome extension for quick lookups",
        ],
        cons: [
          "Designed for sales outreach, not relationship-based job search",
          "No network graph or intro-path features",
          "Paid plans start at $49/mo",
        ],
      },
      {
        name: "Jobscan",
        tagline: "Resume optimization and ATS-matching tools.",
        pros: [
          "ATS keyword matching for resumes",
          "Job tracking features",
          "LinkedIn profile optimization",
        ],
        cons: [
          "Focused on resume optimization, not networking",
          "No contact-finding or intro features",
          "Limited free tier",
        ],
      },
    ],
    comparisonRows: [
      {
        feature: "Relationship-first approach",
        competitorValue: "No — finds strangers at companies",
        contactGraphValue: "Yes — starts from people you know",
      },
      {
        feature: "Contact enrichment",
        competitorValue: "Company staff directories",
        contactGraphValue: "AI-enriched profiles of your real contacts",
      },
      {
        feature: "Job matching",
        competitorValue: "Links to external job boards",
        contactGraphValue: "Roles matched to your network connections",
      },
      {
        feature: "Second-degree reach",
        competitorValue: "No",
        contactGraphValue: "Yes — search friends' shared graphs",
      },
      {
        feature: "Open source",
        competitorValue: "No",
        contactGraphValue: "Yes",
      },
      {
        feature: "Price",
        competitorValue: "From $97/quarter",
        contactGraphValue: "Free forever",
      },
    ],
    faqs: [
      {
        question: "How is ContactGraph different from CareerShift?",
        answer:
          "CareerShift helps you find strangers at target companies. ContactGraph shows you people you already know at companies with open roles — so you start with a warm relationship instead of a cold email.",
      },
      {
        question: "Does ContactGraph have a company contact database?",
        answer:
          "No. ContactGraph takes the opposite approach: instead of giving you a directory of strangers, it enriches your existing contacts with current employer and role data, then matches them to open jobs.",
      },
      {
        question: "Can I search for contacts at a specific company?",
        answer:
          "Yes. Search your graph by company name, role, or industry to instantly see who you know at any organization — and whether they have open positions.",
      },
      {
        question: "Is ContactGraph free?",
        answer:
          "Yes, completely free for personal use. No trial, no credit card, no paywall. ContactGraph is a nonprofit and the entire codebase is open source.",
      },
    ],
  },

  /* ---- VouchedIn ---- */
  {
    slug: "vouchedin-alternatives",
    competitor: "VouchedIn",
    targetKeyword: "VouchedIn alternatives",
    pageTitle: "Best VouchedIn Alternatives",
    pageDescription:
      "Looking for VouchedIn alternatives? Compare tools that combine AI-powered network search with warm introductions to target companies.",
    heroHeading: "VouchedIn gives you a referral. ContactGraph gives you your entire network.",
    heroSubtitle:
      "VouchedIn connects you with referrals at specific companies. ContactGraph searches your entire network — phone, LinkedIn, and shared graphs — with AI enrichment so you never miss a warm path.",
    whoThisIsFor: [
      "Professionals who want to search across all their contacts, not just a curated referral list.",
      "Job seekers who value AI-powered enrichment to keep contact data current and actionable.",
      "Anyone who wants a broader network-search experience beyond a single referral platform.",
    ],
    alternatives: [
      {
        name: "ContactGraph",
        tagline:
          "AI-enriched search across your full network — phone, LinkedIn, and second-degree connections.",
        pros: [
          "Searches your entire real network, not a curated subset",
          "AI enrichment keeps employer, role, and industry data current",
          "Second-degree search through shared graphs with friends",
          "Open source and free — no platform lock-in",
        ],
        cons: [
          "No built-in referral request or messaging feature",
          "Requires a one-time contact export",
        ],
      },
      {
        name: "Lunchclub",
        tagline: "AI-curated 1:1 professional networking meetings.",
        pros: [
          "Curated introductions based on goals and interests",
          "Low effort — the platform handles matching",
          "Good for expanding your network from scratch",
        ],
        cons: [
          "Random matches, not targeted company or role search",
          "No existing-network search or enrichment",
          "Doesn't surface job opportunities directly",
        ],
      },
      {
        name: "Refer Me",
        tagline: "Get employee referrals at top companies.",
        pros: [
          "Direct access to referrers at large companies",
          "Resume review and referral tracking",
          "Focuses on the referral conversion step",
        ],
        cons: [
          "Referrers are strangers — not warm connections",
          "Limited company coverage",
          "Paid premium tier for best features",
        ],
      },
    ],
    comparisonRows: [
      {
        feature: "Network scope",
        competitorValue: "Curated referral network",
        contactGraphValue: "Your full contact graph (phone + LinkedIn)",
      },
      {
        feature: "AI enrichment",
        competitorValue: "Limited",
        contactGraphValue: "Automatic employer, role, and industry enrichment",
      },
      {
        feature: "Second-degree search",
        competitorValue: "No",
        contactGraphValue: "Yes — search friends' shared graphs",
      },
      {
        feature: "Job matching",
        competitorValue: "Company-specific referrals",
        contactGraphValue: "Open roles matched to your network",
      },
      {
        feature: "Data ownership",
        competitorValue: "Platform-owned",
        contactGraphValue: "You own everything",
      },
      {
        feature: "Price",
        competitorValue: "Free tier + paid plans",
        contactGraphValue: "Free forever",
      },
    ],
    faqs: [
      {
        question: "How is ContactGraph different from VouchedIn?",
        answer:
          "VouchedIn focuses on connecting you with referrers at specific companies. ContactGraph takes a broader approach: it enriches your entire real-world network and shows you open roles where you already have a connection.",
      },
      {
        question: "Does ContactGraph help me request referrals?",
        answer:
          "ContactGraph shows you who you know at a company and what role they hold. The outreach is up to you — text, call, or message the people you already have a relationship with.",
      },
      {
        question: "Can I combine ContactGraph with VouchedIn?",
        answer:
          "Yes. Use ContactGraph to find warm paths through your existing network, and VouchedIn for companies where you have no connections at all. They solve different parts of the problem.",
      },
      {
        question: "What data sources does ContactGraph use?",
        answer:
          "Your phone contacts (.vcf) and LinkedIn connections (.csv). ContactGraph then enriches them with public web data to fill in current employer, role, and industry.",
      },
    ],
  },

  /* ---- Nudge ---- */
  {
    slug: "nudge-alternatives",
    competitor: "Nudge",
    targetKeyword: "Nudge alternatives",
    pageTitle: "Best Nudge Alternatives",
    pageDescription:
      "Looking for Nudge alternatives? Compare relationship-intelligence tools that help you find real intro paths into target companies.",
    heroHeading: "Nudge reminds you to keep in touch. ContactGraph shows you who to reach out to.",
    heroSubtitle:
      "Nudge helps you stay in touch with contacts. ContactGraph goes further — it maps your full network, enriches it with AI, and shows you open roles at companies where a real introduction is possible.",
    whoThisIsFor: [
      "Professionals who need more than CRM nudges — they need to find actual paths into target companies.",
      "Job seekers who want intro-path discovery, not just relationship reminders.",
      "Anyone who wants a free, open-source alternative to paid relationship-intelligence tools.",
    ],
    alternatives: [
      {
        name: "ContactGraph",
        tagline:
          "Map your full network, find warm intro paths, and see matched jobs — all for free.",
        pros: [
          "Finds warm intro paths into target companies through your real network",
          "AI-enriched contact profiles with current employer and role",
          "Second-degree search through shared graphs",
          "Free, open source, nonprofit",
        ],
        cons: [
          "No CRM-style relationship reminders or nudges",
          "Focused on network search, not relationship maintenance",
        ],
      },
      {
        name: "Clay",
        tagline: "Personal CRM for staying in touch with your network.",
        pros: [
          "Automatic contact enrichment from email and calendar",
          "Relationship reminders and activity tracking",
          "Clean, modern interface",
        ],
        cons: [
          "No job matching or intro-path discovery",
          "Paid subscription ($20/mo+)",
          "Closed source, data stays on their platform",
        ],
      },
      {
        name: "Dex",
        tagline: "Personal CRM built on top of your existing contacts.",
        pros: [
          "Browser extension for easy contact capture",
          "Tags, notes, and relationship reminders",
          "Integrates with LinkedIn, email, and calendar",
        ],
        cons: [
          "No network graph or intro-path features",
          "No job matching functionality",
          "Limited free tier",
        ],
      },
    ],
    comparisonRows: [
      {
        feature: "Intro-path discovery",
        competitorValue: "No — focuses on stay-in-touch reminders",
        contactGraphValue: "Yes — finds paths into target companies",
      },
      {
        feature: "Job matching",
        competitorValue: "No",
        contactGraphValue: "Open roles matched to your connections",
      },
      {
        feature: "Contact enrichment",
        competitorValue: "Basic (email/calendar sync)",
        contactGraphValue: "AI-powered (employer, role, industry)",
      },
      {
        feature: "Second-degree search",
        competitorValue: "No",
        contactGraphValue: "Yes — search friends' shared graphs",
      },
      {
        feature: "Open source",
        competitorValue: "No",
        contactGraphValue: "Yes — full codebase on GitHub",
      },
      {
        feature: "Price",
        competitorValue: "Free tier + paid ($10–20/mo)",
        contactGraphValue: "Free forever",
      },
    ],
    faqs: [
      {
        question: "How is ContactGraph different from Nudge?",
        answer:
          "Nudge is a relationship-maintenance tool — it reminds you to stay in touch. ContactGraph is a network-search tool — it helps you find who you know at target companies and surfaces open roles where a warm intro is possible.",
      },
      {
        question: "Does ContactGraph have relationship reminders?",
        answer:
          "Not currently. ContactGraph focuses on network search and job matching. If you need stay-in-touch reminders, you could use both tools together.",
      },
      {
        question: "Can I import my Nudge contacts into ContactGraph?",
        answer:
          "ContactGraph imports from phone contacts (.vcf) and LinkedIn (.csv). If your Nudge contacts overlap with those sources, they'll be included automatically.",
      },
      {
        question: "Why would I choose ContactGraph over a personal CRM?",
        answer:
          "If your goal is finding jobs or intros through your network, ContactGraph is purpose-built for that. Personal CRMs help you maintain relationships but don't search for intro paths or match jobs to your contacts.",
      },
    ],
  },

  /* ---- Notwork ---- */
  {
    slug: "notwork-alternatives",
    competitor: "Notwork",
    targetKeyword: "Notwork alternatives",
    pageTitle: "Best Notwork Alternatives",
    pageDescription:
      "Looking for Notwork alternatives? Compare tools that combine network search, contact enrichment, and AI workflows in one place.",
    heroHeading: "Notwork reimagines networking. ContactGraph actually searches yours.",
    heroSubtitle:
      "Notwork reimagines networking. ContactGraph takes it further — combining your phone and LinkedIn contacts into a single AI-enriched graph with job matching, second-degree search, and full MCP support for AI agents.",
    whoThisIsFor: [
      "People searching for a tool that combines network search, enrichment, and AI workflows.",
      "Users who want MCP-native AI agent support for querying their professional network.",
      "Anyone who wants a free, open-source networking tool they can self-host and fully own.",
    ],
    alternatives: [
      {
        name: "ContactGraph",
        tagline:
          "Your personal relationship graph with AI enrichment, job matching, and MCP agent support.",
        pros: [
          "Merges phone + LinkedIn into one searchable, AI-enriched graph",
          "Job matching surfaces roles at companies where you know someone",
          "MCP server for Claude, ChatGPT, Gemini, and terminal agents",
          "Free, open source, nonprofit — self-host or use hosted",
        ],
        cons: [
          "Requires a one-time contact export to set up",
          "No social feed or content features",
        ],
      },
      {
        name: "Polywork",
        tagline: "A professional social network beyond job titles.",
        pros: [
          "Rich profiles with projects and collaborations",
          "Unique approach to showcasing multi-faceted careers",
          "Community-driven networking",
        ],
        cons: [
          "Social network model — you maintain yet another profile",
          "No contact import, enrichment, or network search",
          "No job matching based on existing relationships",
        ],
      },
      {
        name: "Shapr",
        tagline: "Swipe-based professional networking app.",
        pros: [
          "Low-friction introduction matching",
          "Goal-based networking (hiring, mentoring, etc.)",
          "Mobile-first experience",
        ],
        cons: [
          "Matches you with strangers, not your existing contacts",
          "No network search or enrichment features",
          "Limited to the Shapr user base",
        ],
      },
    ],
    comparisonRows: [
      {
        feature: "Network search",
        competitorValue: "Limited",
        contactGraphValue: "Full-graph search by company, role, industry",
      },
      {
        feature: "Contact enrichment",
        competitorValue: "Varies",
        contactGraphValue: "AI-powered employer, role, industry enrichment",
      },
      {
        feature: "AI agent support",
        competitorValue: "No MCP support",
        contactGraphValue: "MCP server + skill.md for terminal agents",
      },
      {
        feature: "Job matching",
        competitorValue: "No",
        contactGraphValue: "Open roles matched to your connections",
      },
      {
        feature: "Self-hostable",
        competitorValue: "No",
        contactGraphValue: "Yes — full open-source codebase",
      },
      {
        feature: "Price",
        competitorValue: "Free tier + paid plans",
        contactGraphValue: "Free forever",
      },
    ],
    faqs: [
      {
        question: "How is ContactGraph different from Notwork?",
        answer:
          "Both aim to improve professional networking. ContactGraph focuses on searching and enriching the contacts you already have, then matching them to open jobs — rather than building a new social network from scratch.",
      },
      {
        question: "Does ContactGraph work with AI agents?",
        answer:
          "Yes. ContactGraph runs as an MCP server, so AI agents like Claude, ChatGPT, and Gemini can query your network directly. It also provides a skill.md for terminal-based agents.",
      },
      {
        question: "Can I self-host ContactGraph?",
        answer:
          "Yes. The entire codebase is open source on GitHub. You can run your own instance or use the free hosted version at contactgraph.ai.",
      },
      {
        question: "What does the enrichment process look like?",
        answer:
          "After you upload your contacts, ContactGraph uses public web data to fill in current employer, role, and industry for each contact — including people you haven't spoken to in years.",
      },
    ],
  },
];

/* ------------------------------------------------------------------ */
/*  Lookup                                                             */
/* ------------------------------------------------------------------ */

const PAGE_MAP: ReadonlyMap<string, AlternativesPageData> = new Map(
  PAGES.map((p: AlternativesPageData) => [p.slug, p]),
);

export function getAlternativesPage(
  slug: string,
): AlternativesPageData | undefined {
  return PAGE_MAP.get(slug);
}

export function getAllAlternativesSlugs(): readonly string[] {
  return PAGES.map((p: AlternativesPageData) => p.slug);
}
