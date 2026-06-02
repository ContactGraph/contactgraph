const GITHUB_REPO_URL = "https://github.com/ContactGraph/contactgraph";

export function MarketingFooter() {
  return (
    <footer className="site-footer">
      <div>~*~ © ContactGraph ~*~</div>
      <div className="rule">–––</div>
      <div className="links">
        <a href="https://api.contactgraph.ai/skill.md">Skill</a> |{" "}
        <a href="/manifesto">Manifesto</a> |{" "}
        <a href="/privacy">Privacy</a> |{" "}
        <a href="/terms">Terms</a> |{" "}
        <a href={GITHUB_REPO_URL}>GitHub</a>
      </div>
    </footer>
  );
}
