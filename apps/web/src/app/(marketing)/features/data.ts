/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface HowItWorksStep {
  readonly number: string;
  readonly title: string;
  readonly body: string;
}

export interface Benefit {
  readonly title: string;
  readonly body: string;
}

export interface UseCase {
  readonly title: string;
  readonly body: string;
}

export interface FaqItem {
  readonly question: string;
  readonly answer: string;
}

export interface FeaturePageData {
  readonly slug: string;
  readonly targetKeyword: string;
  readonly pageTitle: string;
  readonly pageDescription: string;
  readonly heroHeading: string;
  readonly heroSubtitle: string;
  readonly howItWorksHeading: string;
  readonly howItWorksSteps: readonly HowItWorksStep[];
  readonly benefitsHeading: string;
  readonly benefits: readonly Benefit[];
  readonly useCasesHeading: string;
  readonly useCases: readonly UseCase[];
  readonly faqs: readonly FaqItem[];
  readonly ctaHeading: string;
  readonly ctaBody: string;
}

/* ------------------------------------------------------------------ */
/*  Pages                                                              */
/* ------------------------------------------------------------------ */

const PAGES: readonly FeaturePageData[] = [
  {
    slug: "warm-intro-job-search",
    targetKeyword: "warm intro job search",
    pageTitle: "Warm Intro Job Search",
    pageDescription:
      "Find jobs where you already have a trusted connection who can introduce you — not another cold application into the void.",
    heroHeading: "Stop applying cold. Start with someone who knows you.",
    heroSubtitle:
      "Warm intro job search means targeting roles at companies where a real relationship can get you past the resume pile. ContactGraph maps your network to open jobs so every search starts with a path in.",
    howItWorksHeading: "How warm intro job search works in ContactGraph",
    howItWorksSteps: [
      {
        number: "01",
        title: "Import your real contacts",
        body: "Upload your phone contacts and LinkedIn connections once. ContactGraph merges them into a single searchable graph — the people who would actually take your call.",
      },
      {
        number: "02",
        title: "See jobs matched to your network",
        body: "We aggregate open roles from across the web and surface listings at companies where you already know someone — ranked by how strong that connection is.",
      },
      {
        number: "03",
        title: "Reach out to people you trust",
        body: "Search by company or role to find who you know there. Text, call, or message the people in your phone — not strangers on LinkedIn.",
      },
      {
        number: "04",
        title: "Apply with a warm path",
        body: "Every application starts with context: a mutual contact, a shared history, or a direct introduction. Referrals convert at 4–5× the rate of cold applications.",
      },
    ],
    benefitsHeading: "Why warm intros beat cold applications",
    benefits: [
      {
        title: "Higher response rates",
        body: "Hiring managers and recruiters prioritize candidates who come through a trusted referral. Your message lands in a real inbox, not a black hole of 500 applicants.",
      },
      {
        title: "Better role fit",
        body: "People who know you can tell you honestly whether a team or role is a good match — before you spend weeks in an interview process.",
      },
      {
        title: "Faster timelines",
        body: "Warm intros skip the external recruiter screen and often move straight to a hiring manager conversation.",
      },
    ],
    useCasesHeading: "Who warm intro job search is for",
    useCases: [
      {
        title: "Mid-career job changers",
        body: "You have years of relationships across companies and industries — but no easy way to search them by employer or open role.",
      },
      {
        title: "Laid-off professionals",
        body: "When you need to move fast, your existing network is your biggest asset. Warm intro search helps you activate it systematically.",
      },
      {
        title: "Passive job seekers",
        body: "You are not actively applying everywhere — but when the right role appears at a company where you know someone, you want to know immediately.",
      },
    ],
    faqs: [
      {
        question: "What is warm intro job search?",
        answer:
          "Warm intro job search means finding open roles at companies where you already have a trusted relationship — and using that connection to get referred or introduced before applying cold.",
      },
      {
        question: "How is this different from asking friends for referrals?",
        answer:
          "ContactGraph systematizes what people do informally: it merges all your contacts, enriches them with current employer data, and matches them to live job listings — so you do not have to remember who works where.",
      },
      {
        question: "Do I need to know someone at every company?",
        answer:
          "No — but ContactGraph is most valuable when you do. It shows you which of your target employers already have a connection in your graph, so you prioritize warm paths over cold ones.",
      },
      {
        question: "Is ContactGraph free?",
        answer:
          "Yes. ContactGraph is free for personal use, open source, and never sells your contact data.",
      },
    ],
    ctaHeading: "Your next job probably starts with someone you already know.",
    ctaBody:
      "Upload your contacts once. ContactGraph shows you open roles where a warm intro is possible — not just another job board.",
  },
  {
    slug: "career-network-search",
    targetKeyword: "career network search",
    pageTitle: "Career Network Search",
    pageDescription:
      "Search your combined contact graph and LinkedIn network for the strongest paths to your next role.",
    heroHeading: "Search your whole career network — not just LinkedIn.",
    heroSubtitle:
      "Career network search across phone contacts, LinkedIn connections, and shared graphs — enriched with current employer and role data so you find the strongest path to any company.",
    howItWorksHeading: "How career network search works",
    howItWorksSteps: [
      {
        number: "01",
        title: "Unify your contacts",
        body: "Phone contacts and LinkedIn connections live in separate silos. ContactGraph merges them into one graph with deduplication and enrichment.",
      },
      {
        number: "02",
        title: "Enrich with current data",
        body: "Public web data fills in current employer, role, and industry for each contact — including people you have not spoken to in years.",
      },
      {
        number: "03",
        title: "Search by company, role, or industry",
        body: "Ask who you know at Stripe, who works in product management, or who is in fintech — and get instant answers from your real network.",
      },
      {
        number: "04",
        title: "Borrow trusted friends' networks",
        body: "Share graphs with trusted friends and search second-degree connections for paths into companies none of you could reach alone.",
      },
    ],
    benefitsHeading: "Why unified career network search matters",
    benefits: [
      {
        title: "No more siloed searching",
        body: "Stop scrolling LinkedIn for an hour to find one connection. Search your entire professional network in seconds.",
      },
      {
        title: "Stale data, refreshed",
        body: "That contact from 2019 may now be a VP at your target company. Enrichment keeps your graph current without manual updates.",
      },
      {
        title: "Second-degree reach",
        body: "When your direct network is not enough, search trusted friends' shared graphs for intro paths you would never find alone.",
      },
    ],
    useCasesHeading: "When to use career network search",
    useCases: [
      {
        title: "Targeting a specific company",
        body: "Before applying anywhere, search who you know there — and what role they hold — to decide whether a warm path exists.",
      },
      {
        title: "Exploring a new industry",
        body: "Search your graph by industry tag to find contacts already working in the space you want to enter.",
      },
      {
        title: "Coordinated job hunts",
        body: "Laid off with colleagues? Pool your networks and search as a group to cover more employers with warm paths.",
      },
    ],
    faqs: [
      {
        question: "What sources does career network search include?",
        answer:
          "Your phone contacts (.vcf export) and LinkedIn connections (.csv export). ContactGraph merges and deduplicates them, then enriches with public web data.",
      },
      {
        question: "Can I search by job title or industry?",
        answer:
          "Yes. Search by company name, role, industry tag, or person name. ContactGraph returns matches from your graph ranked by relationship strength.",
      },
      {
        question: "Does ContactGraph replace LinkedIn search?",
        answer:
          "For finding who you actually know, yes. ContactGraph focuses on real relationships — people in your phone with numbers you can text — not weak LinkedIn connections.",
      },
      {
        question: "Who can see my network?",
        answer:
          "Only you. Your graph is private by default. You choose explicitly if and when to share it with trusted friends.",
      },
    ],
    ctaHeading: "Your career network is bigger than you think.",
    ctaBody:
      "Merge your contacts, enrich them with current employer data, and search your whole network for the strongest path to your next role.",
  },
  {
    slug: "relationship-graph-enrichment",
    targetKeyword: "relationship graph enrichment",
    pageTitle: "Relationship Graph Enrichment",
    pageDescription:
      "Enrich the people you know with public data to surface current employers, roles, and better job opportunities in your network.",
    heroHeading: "Your contacts are stale. Your graph should not be.",
    heroSubtitle:
      "Relationship graph enrichment fills in current employer, role, and industry for everyone you know — turning an outdated contact list into a live map of your professional network.",
    howItWorksHeading: "How relationship graph enrichment works",
    howItWorksSteps: [
      {
        number: "01",
        title: "Start with your raw contacts",
        body: "Import phone contacts and LinkedIn connections as-is — names, emails, and phone numbers, often with outdated employer info.",
      },
      {
        number: "02",
        title: "Enrich from public web data",
        body: "ContactGraph uses public web sources to fill in current employer, job title, industry, and company metadata for each contact.",
      },
      {
        number: "03",
        title: "Keep your graph searchable",
        body: "Enriched profiles make your network searchable by company, role, and industry — even for contacts you have not updated in years.",
      },
      {
        number: "04",
        title: "Match enriched contacts to jobs",
        body: "Open roles are matched to companies where enriched contacts work, so every listing comes with a named connection.",
      },
    ],
    benefitsHeading: "What enrichment unlocks",
    benefits: [
      {
        title: "Find hidden connections",
        body: "That college friend you have not talked to in five years may now be an engineering manager at your dream company. Enrichment surfaces these paths.",
      },
      {
        title: "Searchable by employer",
        body: "Without enrichment, searching who works at Google requires scrolling hundreds of contacts manually. With enrichment, it takes two seconds.",
      },
      {
        title: "Better job matching",
        body: "Job listings matched to enriched contacts are dramatically more actionable — you know exactly who to reach out to and what role they hold.",
      },
    ],
    useCasesHeading: "Who needs relationship graph enrichment",
    useCases: [
      {
        title: "Job seekers with large networks",
        body: "If you have 500+ contacts across phone and LinkedIn, manual updates are impossible. Enrichment keeps your graph current automatically.",
      },
      {
        title: "Career changers",
        body: "Your network spans multiple industries. Enrichment tags contacts by current sector so you can find paths into a new field.",
      },
      {
        title: "AI agent users",
        body: "Connect Claude or ChatGPT to your enriched graph via MCP — so your AI assistant can answer who you know at any company with current data.",
      },
    ],
    faqs: [
      {
        question: "What data does enrichment add?",
        answer:
          "Current employer, job title, industry sector, and company metadata like size band and description — sourced from public web data, not from contacting your connections.",
      },
      {
        question: "Does enrichment contact my connections?",
        answer:
          "No. ContactGraph never emails, messages, or notifies anyone in your graph. Enrichment uses publicly available information only.",
      },
      {
        question: "How often is enrichment updated?",
        answer:
          "ContactGraph re-enriches contacts on a rolling basis as you use the product and as new public data becomes available.",
      },
      {
        question: "Can I correct enriched data?",
        answer:
          "Yes. You can edit any contact's profile manually. Your edits take precedence over automated enrichment.",
      },
    ],
    ctaHeading: "Turn your contact list into a live professional graph.",
    ctaBody:
      "Upload your contacts once. ContactGraph enriches them with current employer and role data — free, private, and open source.",
  },
  {
    slug: "job-referral-platform",
    targetKeyword: "job referral platform",
    pageTitle: "Job Referral Platform",
    pageDescription:
      "Find and activate referral paths through your real network — not paid stranger-referral marketplaces.",
    heroHeading: "Referrals from people who actually know you.",
    heroSubtitle:
      "A job referral platform built on your real relationships — find open roles at companies where someone in your graph can refer you, then reach out directly.",
    howItWorksHeading: "How ContactGraph works as a referral platform",
    howItWorksSteps: [
      {
        number: "01",
        title: "Map your referral network",
        body: "Import contacts from phone and LinkedIn. ContactGraph identifies who works where and how strong each relationship is.",
      },
      {
        number: "02",
        title: "Match jobs to referrers",
        body: "Live job listings are matched to companies where you have a contact — surfacing referral opportunities you would otherwise miss.",
      },
      {
        number: "03",
        title: "Reach out to your referrer",
        body: "ContactGraph shows you who to ask and what role they hold. The outreach is yours — text, call, or message people you already trust.",
      },
      {
        number: "04",
        title: "Track your referral paths",
        body: "Save target companies, monitor new openings, and see when new roles appear at employers where you already have a connection.",
      },
    ],
    benefitsHeading: "Real referrals vs. paid referral marketplaces",
    benefits: [
      {
        title: "People who know your work",
        body: "Paid referral platforms connect you with strangers who do not know your background. ContactGraph starts with people who have actually worked with you.",
      },
      {
        title: "No referral fees",
        body: "ContactGraph is free for personal use. You are not paying a stranger $50 to submit your resume into their company's referral portal.",
      },
      {
        title: "Higher conversion",
        body: "Referrals from genuine relationships convert at much higher rates than anonymous marketplace submissions.",
      },
    ],
    useCasesHeading: "When to use a referral-first workflow",
    useCases: [
      {
        title: "Applying to competitive companies",
        body: "At companies with thousands of applicants per role, a referral from someone who knows your work is often the only way in.",
      },
      {
        title: "Switching industries",
        body: "A referral from someone who can vouch for your transferable skills matters more than a keyword-optimized resume.",
      },
      {
        title: "Returning to a former employer",
        body: "Search your graph for contacts still at companies where you previously worked — boomerang hires often start with a warm referral.",
      },
    ],
    faqs: [
      {
        question: "Is ContactGraph a paid referral marketplace?",
        answer:
          "No. ContactGraph does not connect you with stranger referrers or charge referral fees. It helps you find referral paths through people you already know.",
      },
      {
        question: "Does ContactGraph submit referrals on my behalf?",
        answer:
          "No. ContactGraph shows you who to ask. You reach out directly to people in your network — the same way referrals work in the real world.",
      },
      {
        question: "How is this different from LinkedIn referrals?",
        answer:
          "LinkedIn shows you connections at a company but not which ones would actually refer you. ContactGraph ranks contacts by relationship strength and matches them to specific open roles.",
      },
      {
        question: "Can I use ContactGraph alongside Refer Me or similar tools?",
        answer:
          "Yes. Use ContactGraph for companies where you have real connections, and paid referral services only for companies where you have no network at all.",
      },
    ],
    ctaHeading: "Your best referrer is someone who already knows you.",
    ctaBody:
      "Find open roles at companies where your network can actually refer you — not strangers from a marketplace.",
  },
  {
    slug: "linkedin-network-search",
    targetKeyword: "LinkedIn network search",
    pageTitle: "LinkedIn Network Search",
    pageDescription:
      "Search your LinkedIn connections and phone contacts together for job intro opportunities — faster and more private than LinkedIn search.",
    heroHeading: "Search your LinkedIn network — without LinkedIn's limits.",
    heroSubtitle:
      "LinkedIn network search in ContactGraph merges your LinkedIn connections with phone contacts, enriches them with current data, and matches them to open jobs — so you find intro opportunities LinkedIn cannot show you.",
    howItWorksHeading: "How LinkedIn network search works in ContactGraph",
    howItWorksSteps: [
      {
        number: "01",
        title: "Export your LinkedIn connections",
        body: "Download your connections as a .csv from LinkedIn settings — a one-time export that takes about five minutes.",
      },
      {
        number: "02",
        title: "Merge with phone contacts",
        body: "ContactGraph deduplicates and merges LinkedIn connections with your phone contacts into one unified, searchable graph.",
      },
      {
        number: "03",
        title: "Search beyond LinkedIn's UI",
        body: "Search by company, role, or industry across your full merged network — not just what LinkedIn's connection search returns.",
      },
      {
        number: "04",
        title: "Find jobs with LinkedIn paths",
        body: "Open roles are matched to companies where your LinkedIn connections (and phone contacts) work — ranked by relationship strength.",
      },
    ],
    benefitsHeading: "Why search LinkedIn connections in ContactGraph",
    benefits: [
      {
        title: "Beyond LinkedIn's search limits",
        body: "LinkedIn restricts how you can search connections and hides weak ties. ContactGraph searches your full exported network without platform limits.",
      },
      {
        title: "Phone contacts included",
        body: "Your strongest professional relationships are often in your phone, not on LinkedIn. ContactGraph searches both together.",
      },
      {
        title: "Matched to live jobs",
        body: "LinkedIn shows you who works where. ContactGraph also shows you which of those companies have open roles right now.",
      },
    ],
    useCasesHeading: "When LinkedIn network search is not enough",
    useCases: [
      {
        title: "Finding intro paths at target companies",
        body: "Before applying, search who in your LinkedIn network works at your target employer — and whether they are strong enough to ask.",
      },
      {
        title: "Job search without LinkedIn Premium",
        body: "ContactGraph gives you network search and job matching without a LinkedIn subscription.",
      },
      {
        title: "Connecting AI to your LinkedIn network",
        body: "Export once and connect Claude, ChatGPT, or any MCP client to search your LinkedIn connections programmatically.",
      },
    ],
    faqs: [
      {
        question: "Do I need LinkedIn Premium for this?",
        answer:
          "No. ContactGraph uses your free LinkedIn connections export (.csv). You do not need Premium, Sales Navigator, or any paid LinkedIn tier.",
      },
      {
        question: "Does ContactGraph scrape LinkedIn?",
        answer:
          "No. You export your connections manually once. ContactGraph never logs into LinkedIn or automates any actions on the platform.",
      },
      {
        question: "Can I still use LinkedIn alongside ContactGraph?",
        answer:
          "Yes. ContactGraph complements LinkedIn — it gives you a searchable, enriched copy of your network that LinkedIn's own search cannot provide.",
      },
      {
        question: "Is my LinkedIn data safe?",
        answer:
          "Yes. Your graph is private to you, never shared or sold. ContactGraph is open source — you can verify exactly what happens to your data.",
      },
    ],
    ctaHeading: "Your LinkedIn network is more valuable than LinkedIn shows you.",
    ctaBody:
      "Export your connections once. Search them by company, match them to open jobs, and find intro paths LinkedIn cannot surface.",
  },
];

/* ------------------------------------------------------------------ */
/*  Lookup                                                             */
/* ------------------------------------------------------------------ */

const PAGE_MAP: ReadonlyMap<string, FeaturePageData> = new Map(
  PAGES.map((page: FeaturePageData) => [page.slug, page]),
);

export function getFeaturePage(slug: string): FeaturePageData | undefined {
  return PAGE_MAP.get(slug);
}

export function getAllFeatureSlugs(): readonly string[] {
  return PAGES.map((page: FeaturePageData) => page.slug);
}

export function getAllFeaturePages(): readonly FeaturePageData[] {
  return PAGES;
}

export function featurePageHref(slug: string): `/features/${string}` {
  return `/features/${slug}`;
}
