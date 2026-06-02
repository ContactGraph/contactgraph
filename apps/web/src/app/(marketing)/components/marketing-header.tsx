const GITHUB_REPO_URL = "https://github.com/ContactGraph/contactgraph";
const API_BASE = "https://api.contactgraph.ai";

export function MarketingHeader() {
  const year: number = new Date().getFullYear();
  const mcpPath = `${API_BASE}/mcp`;

  return (
    <header className="border-b border-border">
      <div className="flex flex-col gap-4 px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex flex-col gap-0.5">
          <a href="/" className="text-sm font-semibold no-underline hover:underline">
            ContactGraph
          </a>
          <div className="text-sm text-muted-foreground">{year}</div>
        </div>
        <nav
          className="text-sm text-muted-foreground sm:text-right"
          aria-label="ContactGraph links"
        >
          <a href={`${API_BASE}/skill.md`} className="no-underline hover:underline">
            Skill
          </a>
          {" / "}
          <a href={mcpPath} className="no-underline hover:underline">
            MCP
          </a>
          {" / "}
          <a href={GITHUB_REPO_URL} className="no-underline hover:underline">
            GitHub
          </a>
          {" / "}
          <a href="/manifesto" className="no-underline hover:underline">
            Manifesto
          </a>
        </nav>
      </div>
    </header>
  );
}
