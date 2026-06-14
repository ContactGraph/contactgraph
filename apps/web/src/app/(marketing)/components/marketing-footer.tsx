const GITHUB_REPO_URL = "https://github.com/ContactGraph/contactgraph";

export function MarketingFooter() {
  return (
    <footer className="border-t border-border px-5 py-4 text-sm text-muted-foreground">
      <div>© ContactGraph</div>
      <div className="mt-3 text-foreground">
        <a href="https://api.contactgraph.ai/skill.md" className="no-underline hover:underline">
          Skill
        </a>
        {" | "}
        <a href="/about" className="no-underline hover:underline">
          About
        </a>
        {" | "}
        <a href="/manifesto" className="no-underline hover:underline">
          Manifesto
        </a>
        {" | "}
        <a href="/privacy" className="no-underline hover:underline">
          Privacy
        </a>
        {" | "}
        <a href="/terms" className="no-underline hover:underline">
          Terms
        </a>
        {" | "}
        <a href="/resources" className="no-underline hover:underline">
          Resources
        </a>
        {" | "}
        <a href="/blog" className="no-underline hover:underline">
          Blog
        </a>
        {" | "}
        <a href="/alternatives/linkedin-jobs-alternatives" className="no-underline hover:underline">
          Alternatives
        </a>
        {" | "}
        <a href="/guides/connect-claude-to-linkedin" className="no-underline hover:underline">
          Guides
        </a>
        {" | "}
        <a href={GITHUB_REPO_URL} className="no-underline hover:underline">
          GitHub
        </a>
      </div>
      <div className="mt-2 text-foreground">
        <span className="text-muted-foreground">Guides: </span>
        <a
          href="/guides/connect-claude-to-linkedin"
          className="no-underline hover:underline"
        >
          Connect Claude
        </a>
        {" | "}
        <a
          href="/guides/linkedin-mcp-server-job-search"
          className="no-underline hover:underline"
        >
          LinkedIn MCP
        </a>
        {" | "}
        <a
          href="/guides/ai-linkedin-contacts"
          className="no-underline hover:underline"
        >
          AI Contacts
        </a>
      </div>
    </footer>
  );
}
