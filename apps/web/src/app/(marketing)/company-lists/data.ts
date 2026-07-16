import { companyPageHref, companySlug } from "@/lib/company-slug";
import { env } from "@/lib/env";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface FaqItem {
  readonly question: string;
  readonly answer: string;
}

export interface CategoryPageData {
  readonly slug: string;
  readonly targetKeyword: string;
  readonly pageTitle: string;
  readonly pageDescription: string;
  readonly heroHeading: string;
  readonly heroSubtitle: string;
  readonly whyThisCategoryMatters: readonly string[];
  readonly networkFitHeading: string;
  readonly networkFitBody: readonly string[];
  readonly faqs: readonly FaqItem[];
}

export interface CategoryJob {
  readonly job_id: string;
  readonly title: string;
  readonly location: string | null;
  readonly url: string;
  readonly remote_status: string | null;
  readonly posted_at: string | null;
}

export interface CategoryCompany {
  readonly org_id: string;
  readonly slug: string;
  readonly name: string;
  readonly primary_domain: string | null;
  readonly description: string | null;
  readonly company_size_band: string | null;
  readonly active_job_count: number;
  readonly sample_jobs: readonly CategoryJob[];
}

export interface CategoryCompaniesResult {
  readonly category: string;
  readonly companies: readonly CategoryCompany[];
  readonly total_companies: number;
  readonly total_jobs: number;
  readonly generated_at: string;
}

const EMPTY_CATEGORY_RESULT: CategoryCompaniesResult = {
  category: "",
  companies: [],
  total_companies: 0,
  total_jobs: 0,
  generated_at: new Date(0).toISOString(),
};

/* ------------------------------------------------------------------ */
/*  Static category pages                                              */
/* ------------------------------------------------------------------ */

const PAGES: readonly CategoryPageData[] = [
  {
    slug: "top-tech-companies-hiring",
    targetKeyword: "Top tech companies hiring",
    pageTitle: "Top Tech Companies Hiring Right Now",
    pageDescription:
      "See which top tech companies are hiring right now — with live open-role counts — and find a warm intro path through your network with ContactGraph.",
    heroHeading: "Top tech companies hiring right now — with a warm path in.",
    heroSubtitle:
      "Browse real employers with active engineering, product, and design openings. ContactGraph shows you who you already know at each company so you can skip the cold application queue.",
    whyThisCategoryMatters: [
      "Big tech and high-growth software companies post hundreds of roles at once — but most applicants never get a reply because they apply cold.",
      "The best time to target a tech employer is when they are actively hiring across multiple teams, not when a single role pops up on a job board.",
      "Knowing which companies have the most open roles right now helps you prioritize where a warm introduction could actually move your candidacy forward.",
    ],
    networkFitHeading: "Your network already reaches further than you think.",
    networkFitBody: [
      "ContactGraph merges your phone contacts and LinkedIn connections, enriches them with current employer data, and matches open roles at tech companies where someone will take your call.",
      "Search by company name to see who you know there — then reach out directly instead of applying into a black hole.",
      "When your network is not enough, search trusted friends' shared graphs for second-degree intros into the same employers.",
    ],
    faqs: [
      {
        question: "How often is this list updated?",
        answer:
          "Company and job counts refresh from ContactGraph's live job database, typically updated as new roles are scraped from company career pages and job aggregators.",
      },
      {
        question: "Do I need to know someone at every company on this list?",
        answer:
          "No — but ContactGraph shines when you do. Upload your contacts once and we show you which of these employers already have someone in your graph.",
      },
      {
        question: "Are these jobs only on LinkedIn?",
        answer:
          "No. ContactGraph aggregates openings from ATS boards (Greenhouse, Lever, Ashby) and other sources — wherever companies actually post roles.",
      },
      {
        question: "How is ContactGraph different from a job board?",
        answer:
          "Job boards show listings. ContactGraph shows listings where you already have a relationship — so every application can start with a warm intro instead of a cold resume drop.",
      },
    ],
  },
  {
    slug: "ai-startups-hiring",
    targetKeyword: "AI startups hiring",
    pageTitle: "AI Startups Hiring Right Now",
    pageDescription:
      "Discover AI startups with active open roles and find warm intro paths into ML, LLM, and applied-AI teams through your network.",
    heroHeading: "AI startups hiring right now — find a warm path in.",
    heroSubtitle:
      "From foundation-model shops to applied-AI products, these employers have live openings. ContactGraph helps you find who you know before you apply.",
    whyThisCategoryMatters: [
      "AI startups hire in bursts — a funding round or product launch can mean dozens of new roles overnight.",
      "Many AI roles never reach mainstream job boards; they spread through networks and niche communities first.",
      "Early-stage AI teams heavily weight referrals — a warm intro from someone who knows the founders or hiring manager is often the fastest path in.",
    ],
    networkFitHeading: "AI hiring runs on trust and referrals.",
    networkFitBody: [
      "Your ex-coworkers, classmates, and conference contacts may already be at an AI startup you are targeting — ContactGraph surfaces those connections automatically.",
      "Search your graph by company or industry tag to see current employers and roles for people you actually know.",
      "Pool networks with trusted friends to uncover second-degree paths into teams building LLMs, agents, and applied AI products.",
    ],
    faqs: [
      {
        question: "Which companies count as AI startups here?",
        answer:
          "We include technology companies whose profiles mention artificial intelligence, machine learning, LLMs, or generative AI, typically at startup scale (under ~500 employees).",
      },
      {
        question: "I do not have ML experience — can I still use this?",
        answer:
          "Yes. AI startups hire across engineering, product, design, sales, and operations. The list reflects all active roles we track, not just research positions.",
      },
      {
        question: "How do I get an intro to a small AI team?",
        answer:
          "Upload your contacts to ContactGraph, search the company name, and message someone you already have a real relationship with — not a LinkedIn cold request.",
      },
      {
        question: "Is ContactGraph free?",
        answer:
          "Yes. ContactGraph is free for personal use, open source, and never sells your contact data.",
      },
    ],
  },
  {
    slug: "remote-first-companies-hiring",
    targetKeyword: "Remote-first companies hiring",
    pageTitle: "Remote-First Companies Hiring Right Now",
    pageDescription:
      "Find remote-first companies with active hiring and discover warm intro paths into distributed teams through ContactGraph.",
    heroHeading: "Remote-first companies hiring right now — find a warm path in.",
    heroSubtitle:
      "These employers have the majority of their open roles listed as remote. ContactGraph shows you who you know there before you apply from across the country.",
    whyThisCategoryMatters: [
      "Remote-first companies compete globally for talent — which means more applicants per role unless you have an inside connection.",
      "Distributed teams often hire through referrals because they cannot rely on local networks or campus recruiting.",
      "Knowing which employers are genuinely remote-first (not just 'remote OK') helps you focus on companies whose culture matches how you want to work.",
    ],
    networkFitHeading: "Distance does not matter if you know someone there.",
    networkFitBody: [
      "ContactGraph finds people in your existing network who work at remote-first companies — regardless of where you or they live.",
      "Warm intros matter even more for remote roles, where hiring managers rely on trusted referrals to filter global applicant pools.",
      "Share graphs with friends to expand your reach into distributed teams at companies you would never find through a local network alone.",
    ],
    faqs: [
      {
        question: "How do you define remote-first?",
        answer:
          "Companies where more than half of their currently active job postings are marked as fully remote in our job database.",
      },
      {
        question: "Are hybrid roles included?",
        answer:
          "This page focuses on employers that are predominantly hiring for remote roles. Individual listings may still include hybrid or onsite positions.",
      },
      {
        question: "Can ContactGraph help if I do not know anyone at these companies?",
        answer:
          "ContactGraph is built for warm-path search. If you have no connections, second-degree search through trusted friends' shared graphs is your next best option.",
      },
      {
        question: "Do job links go to the original posting?",
        answer:
          "Yes. Each role links out to the employer's original job posting — we never re-host full job descriptions.",
      },
    ],
  },
  {
    slug: "series-a-startups-hiring",
    targetKeyword: "Series A startups hiring",
    pageTitle: "Series A Startups Hiring Right Now",
    pageDescription:
      "Explore Series A-stage startups with active open roles and find warm introductions through your professional network.",
    heroHeading: "Series A startups hiring right now — find a warm path in.",
    heroSubtitle:
      "Post-product, pre-scale companies with live hiring across engineering, GTM, and operations. ContactGraph shows you who you know before you send a cold email.",
    whyThisCategoryMatters: [
      "Series A is when startups shift from founding team to building real departments — creating a wave of senior and IC hires at once.",
      "These companies rarely have dedicated recruiting teams; hiring managers and founders lean heavily on referrals.",
      "Getting in early at a Series A company often means more ownership, equity, and impact — but only if you can actually reach the hiring manager.",
    ],
    networkFitHeading: "Series A hiring is almost entirely network-driven.",
    networkFitBody: [
      "Someone in your phone contacts or LinkedIn network may already have joined a Series A startup in the last year — ContactGraph enriches stale contact data with current employers.",
      "Search by company name to find who you know, what role they hold, and whether they can intro you to the right team.",
      "Job seekers who pool networks with friends often discover second-degree paths into startups none of them could reach alone.",
    ],
    faqs: [
      {
        question: "How do you identify Series A startups?",
        answer:
          "We use company size (typically 11–200 employees) as a proxy for Series A stage, combined with active job postings in our database. We do not currently track funding rounds directly.",
      },
      {
        question: "Are these only Bay Area startups?",
        answer:
          "No. Our job database includes startups hiring across the US and globally, including many remote-friendly Series A companies.",
      },
      {
        question: "What roles do Series A startups hire for?",
        answer:
          "Common openings include software engineers, product managers, designers, sales, customer success, and first operations hires — whatever appears in their live postings.",
      },
      {
        question: "Why use ContactGraph instead of Wellfound?",
        answer:
          "Wellfound is great for browsing startup listings. ContactGraph adds the missing piece: who you already know at each company so you can get referred instead of lost in the pile.",
      },
    ],
  },
  {
    slug: "fintech-companies-hiring",
    targetKeyword: "Fintech companies hiring",
    pageTitle: "Fintech Companies Hiring Right Now",
    pageDescription:
      "See fintech and financial-services companies with active open roles and find warm intro paths through your network with ContactGraph.",
    heroHeading: "Fintech companies hiring right now — find a warm path in.",
    heroSubtitle:
      "Payments, banking, lending, and financial infrastructure employers with live openings. ContactGraph helps you find who you know before you apply.",
    whyThisCategoryMatters: [
      "Fintech combines regulated-industry hiring with startup-speed growth — roles span engineering, compliance, risk, product, and partnerships.",
      "Many fintech companies hire through referrals because trust and reputation matter in financial services.",
      "Knowing which fintech employers are actively hiring helps you target companies where your background — and your network — align.",
    ],
    networkFitHeading: "Fintech runs on relationships as much as resumes.",
    networkFitBody: [
      "Former colleagues from banks, payments companies, or tech firms may now be at a fintech you are targeting — ContactGraph maps those connections from your existing contacts.",
      "Search by company or industry to see who in your graph works where, enriched with current role and employer data.",
      "Second-degree search through trusted friends can surface paths into fintech teams that require a credible referral.",
    ],
    faqs: [
      {
        question: "Which companies are included in fintech?",
        answer:
          "Financial-services employers (NAICS sector 52) plus technology companies whose profiles mention fintech, payments, banking, or financial services.",
      },
      {
        question: "Do I need finance experience for these roles?",
        answer:
          "Not always. Fintech companies hire engineers, designers, product managers, and operators — check individual listings for requirements.",
      },
      {
        question: "How current are the job counts?",
        answer:
          "Counts reflect active roles in ContactGraph's job database, refreshed as our scrapers discover new postings and mark closed roles inactive.",
      },
      {
        question: "Can I target specific fintech sub-sectors?",
        answer:
          "Use ContactGraph's job preferences and target-company lists inside the product to narrow further. This page shows the broad fintech hiring landscape.",
      },
    ],
  },
  {
    slug: "healthtech-companies-hiring",
    targetKeyword: "Healthtech companies hiring",
    pageTitle: "Healthtech Companies Hiring Right Now",
    pageDescription:
      "Discover healthtech and healthcare companies with active open roles and warm intro paths through your professional network.",
    heroHeading: "Healthtech companies hiring right now — find a warm path in.",
    heroSubtitle:
      "Digital health, clinical software, and healthcare technology employers with live openings. ContactGraph shows you who you know before you apply cold.",
    whyThisCategoryMatters: [
      "Healthtech sits at the intersection of healthcare and technology — hiring spans clinical, regulatory, engineering, and commercial roles.",
      "Many healthtech companies prefer referrals because domain knowledge and trust are hard to assess from a resume alone.",
      "The sector continues to grow as providers, payers, and startups digitize care — creating steady hiring even in slower tech markets.",
    ],
    networkFitHeading: "Healthcare hiring rewards trusted connections.",
    networkFitBody: [
      "Clinicians, operators, and engineers in your network may already be at healthtech companies you have never thought to search — ContactGraph enriches contacts with current employers.",
      "Find warm paths into digital health startups, clinical software vendors, and healthcare platforms by searching your graph by company name.",
      "Share networks with friends in healthcare or tech to discover second-degree intros into teams building the next generation of health products.",
    ],
    faqs: [
      {
        question: "What counts as healthtech here?",
        answer:
          "Healthcare-sector employers (NAICS 62) plus technology companies whose profiles mention health, medical, clinical, or digital health products.",
      },
      {
        question: "Do I need a clinical background?",
        answer:
          "Many healthtech roles are engineering, product, data, and operations positions. Clinical roles are included when they appear in live postings.",
      },
      {
        question: "Are these jobs remote?",
        answer:
          "Some employers offer remote roles; others require onsite or hybrid work. Each listing links to the original posting with location details.",
      },
      {
        question: "How does ContactGraph protect my contacts?",
        answer:
          "Your graph is private to you. ContactGraph never messages your contacts, never sells your data, and is fully open source.",
      },
    ],
  },
];

/* ------------------------------------------------------------------ */
/*  Lookup                                                             */
/* ------------------------------------------------------------------ */

const PAGE_MAP: ReadonlyMap<string, CategoryPageData> = new Map(
  PAGES.map((page: CategoryPageData) => [page.slug, page]),
);

export function getCategoryPage(slug: string): CategoryPageData | undefined {
  return PAGE_MAP.get(slug);
}

export function getAllCategorySlugs(): readonly string[] {
  return PAGES.map((page: CategoryPageData) => page.slug);
}

export function getAllCategoryPages(): readonly CategoryPageData[] {
  return PAGES;
}

/* ------------------------------------------------------------------ */
/*  Live company data                                                  */
/* ------------------------------------------------------------------ */

export async function fetchCategoryCompanies(
  slug: string,
): Promise<CategoryCompaniesResult> {
  const apiUrl: string = env.apiUrl.replace(/\/$/, "");
  const url: string = `${apiUrl}/api/public/companies-by-category?category=${encodeURIComponent(slug)}`;

  try {
    const response: Response = await fetch(url, {
      next: { revalidate: 3600 },
    });

    if (!response.ok) {
      return { ...EMPTY_CATEGORY_RESULT, category: slug };
    }

    const payload: unknown = await response.json();
    return parseCategoryCompaniesResult(payload, slug);
  } catch {
    return { ...EMPTY_CATEGORY_RESULT, category: slug };
  }
}

function parseCategoryCompaniesResult(
  payload: unknown,
  fallbackCategory: string,
): CategoryCompaniesResult {
  if (typeof payload !== "object" || payload === null) {
    return { ...EMPTY_CATEGORY_RESULT, category: fallbackCategory };
  }

  const data: Record<string, unknown> = payload as Record<string, unknown>;
  const category: string =
    typeof data.category === "string" ? data.category : fallbackCategory;
  const totalCompanies: number =
    typeof data.total_companies === "number" ? data.total_companies : 0;
  const totalJobs: number =
    typeof data.total_jobs === "number" ? data.total_jobs : 0;
  const generatedAt: string =
    typeof data.generated_at === "string"
      ? data.generated_at
      : new Date().toISOString();

  const companiesRaw: unknown = data.companies;
  const companies: CategoryCompany[] = Array.isArray(companiesRaw)
    ? companiesRaw
        .map(parseCategoryCompany)
        .filter((company: CategoryCompany | null): company is CategoryCompany => company !== null)
    : [];

  return {
    category,
    companies,
    total_companies: totalCompanies,
    total_jobs: totalJobs,
    generated_at: generatedAt,
  };
}

function parseCategoryCompany(raw: unknown): CategoryCompany | null {
  if (typeof raw !== "object" || raw === null) {
    return null;
  }

  const item: Record<string, unknown> = raw as Record<string, unknown>;
  const orgId: string | null = typeof item.org_id === "string" ? item.org_id : null;
  const name: string | null = typeof item.name === "string" ? item.name : null;
  const slug: string | null =
    typeof item.slug === "string" ? item.slug : name !== null ? companySlug(name) : null;
  const activeJobCount: number | null =
    typeof item.active_job_count === "number" ? item.active_job_count : null;

  if (orgId === null || name === null || slug === null || activeJobCount === null) {
    return null;
  }

  const sampleJobsRaw: unknown = item.sample_jobs;
  const sampleJobs: CategoryJob[] = Array.isArray(sampleJobsRaw)
    ? sampleJobsRaw
        .map(parseCategoryJob)
        .filter((job: CategoryJob | null): job is CategoryJob => job !== null)
    : [];

  return {
    org_id: orgId,
    slug,
    name,
    primary_domain:
      typeof item.primary_domain === "string" ? item.primary_domain : null,
    description: typeof item.description === "string" ? item.description : null,
    company_size_band:
      typeof item.company_size_band === "string" ? item.company_size_band : null,
    active_job_count: activeJobCount,
    sample_jobs: sampleJobs,
  };
}

function parseCategoryJob(raw: unknown): CategoryJob | null {
  if (typeof raw !== "object" || raw === null) {
    return null;
  }

  const item: Record<string, unknown> = raw as Record<string, unknown>;
  const jobId: string | null = typeof item.job_id === "string" ? item.job_id : null;
  const title: string | null = typeof item.title === "string" ? item.title : null;
  const url: string | null = typeof item.url === "string" ? item.url : null;

  if (jobId === null || title === null || url === null) {
    return null;
  }

  return {
    job_id: jobId,
    title,
    location: typeof item.location === "string" ? item.location : null,
    url,
    remote_status:
      typeof item.remote_status === "string" ? item.remote_status : null,
    posted_at: typeof item.posted_at === "string" ? item.posted_at : null,
  };
}

export { companyPageHref };

export function sampleCompanies(
  companies: readonly CategoryCompany[],
  limit: number = 4,
): readonly CategoryCompany[] {
  return companies.slice(0, limit);
}
