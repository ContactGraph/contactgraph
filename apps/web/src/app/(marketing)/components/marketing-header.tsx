const GITHUB_REPO_URL = "https://github.com/ContactGraph/contactgraph";
const API_BASE = "https://api.contactgraph.ai";

export function MarketingHeader() {
  const year: number = new Date().getFullYear();
  const mcpPath = `${API_BASE}/mcp`;

  return (
    <header>
      <div className="masthead">
        <div className="brand-block">
          <a href="/">CONTACTGRAPH</a>
          <div className="brand-meta">{year}</div>
        </div>
        <nav className="nav-block" aria-label="ContactGraph links">
          <div className="nav-bracket">
            [&nbsp;
            <a href={`${API_BASE}/skill.md`}>SKILL.MD</a>
            &nbsp;/&nbsp;
            <a href={mcpPath}>MCP</a>
            &nbsp;/&nbsp;
            <a href={GITHUB_REPO_URL}>GITHUB</a>
            &nbsp;/&nbsp;
            <a href="/manifesto">MANIFESTO</a>
            &nbsp;]
          </div>
        </nav>
      </div>
    </header>
  );
}
