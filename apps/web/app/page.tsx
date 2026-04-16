const featuredProjects = [
  {
    title: "Design systems with teeth",
    summary:
      "Portfolio case studies can explain not just what shipped, but how decisions held up under real product constraints.",
    tags: ["Systems", "UX", "Engineering"],
  },
  {
    title: "Research-shaped product thinking",
    summary:
      "Show the path from ambiguity to delivery: inputs, framing, tradeoffs, and what changed after feedback.",
    tags: ["Strategy", "Research", "Execution"],
  },
  {
    title: "Calm technical storytelling",
    summary:
      "Use writing, diagrams, and artifacts to make complex work feel legible to collaborators, clients, and hiring teams.",
    tags: ["Writing", "Architecture", "Communication"],
  },
];

const workingPrinciples = [
  "Build interfaces that earn attention instead of begging for it.",
  "Make technical choices visible, explicit, and reversible.",
  "Treat documentation as part of the product surface.",
];

export default function HomePage() {
  return (
    <main className="page-shell">
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">Portfolio platform</p>
          <h1>
            A personal website for thoughtful product work,
            <span> built to grow without losing its shape.</span>
          </h1>
          <p className="lede">
            This starter is intentionally structured for case studies, writing, and future API-backed content. It uses
            a bold editorial layout up front and keeps room for Python services behind the scenes.
          </p>
          <div className="hero-actions">
            <a className="primary-link" href="#work">
              View featured work
            </a>
            <a className="secondary-link" href="#contact">
              Plan the next iteration
            </a>
          </div>
        </div>
        <div className="hero-panel">
          <p className="panel-label">Current direction</p>
          <ul>
            <li>Next.js frontend tuned for Cloudflare hosting</li>
            <li>FastAPI backend ready for structured content and integrations</li>
            <li>Agent-readable docs so the repo stays maintainable as it grows</li>
          </ul>
        </div>
      </section>

      <section className="section-grid" id="work">
        <div className="section-intro">
          <p className="eyebrow">Featured structure</p>
          <h2>Case studies, writing, and proof of taste.</h2>
        </div>
        <div className="project-grid">
          {featuredProjects.map((project) => (
            <article className="project-card" key={project.title}>
              <h3>{project.title}</h3>
              <p>{project.summary}</p>
              <div className="tag-row">
                {project.tags.map((tag) => (
                  <span key={tag}>{tag}</span>
                ))}
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="section-grid about-band">
        <div className="section-intro">
          <p className="eyebrow">Working style</p>
          <h2>Present the thinking, not just the polish.</h2>
        </div>
        <div className="principles">
          {workingPrinciples.map((principle) => (
            <p key={principle}>{principle}</p>
          ))}
        </div>
      </section>

      <section className="section-grid contact-band" id="contact">
        <div className="section-intro">
          <p className="eyebrow">Next steps</p>
          <h2>Replace the starter content with your real story.</h2>
        </div>
        <div className="contact-card">
          <p>
            Add real projects, writing, and contact links here. The backend already gives you a clean place to grow
            into forms, CMS syncing, analytics summaries, or structured content APIs.
          </p>
          <a className="primary-link" href="mailto:hello@yourdomain.com">
            hello@yourdomain.com
          </a>
        </div>
      </section>
    </main>
  );
}
