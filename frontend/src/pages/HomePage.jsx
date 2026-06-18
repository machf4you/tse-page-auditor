import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { auditApi } from "@/lib/api";

function ScorePill({ score }) {
  const cls = score >= 75 ? "pill-good" : score >= 50 ? "pill-warn" : "pill-bad";
  return <span className={`pill ${cls}`} data-testid="history-score">{score}</span>;
}

function HistoryList() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    auditApi.list()
      .then((d) => { if (alive) setRows(d); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);
  if (loading) return <div className="muted">Loading history…</div>;
  if (!rows.length) {
    return <div className="muted" data-testid="history-empty">No audits yet. Run your first one above.</div>;
  }
  return (
    <div className="history" data-testid="history-list">
      {rows.map(r => (
        <Link key={r.id} to={`/audits/${r.id}`} className="history-row" data-testid={`history-row-${r.id}`}>
          <ScorePill score={r.overall_score} />
          <div>
            <div className="history-url">{r.url}</div>
            <div className="history-phrase">
              {r.primary_phrase} · {r.created_at?.slice(0, 16).replace("T", " ")}
            </div>
          </div>
          <span className="btn small">Open</span>
        </Link>
      ))}
    </div>
  );
}

export default function HomePage() {
  const [url, setUrl] = useState("");
  const [primary, setPrimary] = useState("");
  const [secondaryRaw, setSecondaryRaw] = useState("");
  const [renderJs, setRenderJs] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const run = (e) => {
    e?.preventDefault?.();
    if (!url.trim()) { setError("URL is required."); return; }
    if (!primary.trim()) { setError("Primary phrase is required."); return; }
    setError(""); setRunning(true);
    const secondaries = secondaryRaw
      .split(/[\n,]/)
      .map(s => s.trim())
      .filter(Boolean);
    auditApi.run({
      url: url.trim(),
      primary_phrase: primary.trim(),
      secondary_phrases: secondaries,
      render_js: renderJs,
    })
      .then((r) => navigate(`/audits/${r.id}`))
      .catch((err) => setError(err.response?.data?.detail || err.message))
      .finally(() => setRunning(false));
  };

  return (
    <div className="page" data-testid="home-page">
      <header>
        <div className="brand">TSE Page Auditor</div>
        <h1 className="page-title">Audit a single page</h1>
        <p className="page-sub">
          Enter a live URL and a target phrase. The auditor fetches the page,
          extracts everything that matters for ranking, and returns a 0-100
          score with priority-tagged strengths, weaknesses and recommendations.
        </p>
      </header>

      {error && <div className="alert error" data-testid="form-error">{error}</div>}

      <form className="card form" onSubmit={run} data-testid="audit-form">
        <label className="field">
          <span className="field-label">URL</span>
          <input
            type="url"
            className="input"
            placeholder="https://example.com/page/"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            data-testid="url-input"
            required
          />
        </label>

        <label className="field">
          <span className="field-label">Primary target phrase</span>
          <input
            type="text"
            className="input"
            placeholder="local seo services"
            value={primary}
            onChange={(e) => setPrimary(e.target.value)}
            data-testid="primary-phrase-input"
            required
          />
        </label>

        <label className="field">
          <span className="field-label">Secondary phrases (one per line, optional)</span>
          <textarea
            className="textarea"
            rows={4}
            placeholder={"local seo company\nlocal seo agency"}
            value={secondaryRaw}
            onChange={(e) => setSecondaryRaw(e.target.value)}
            data-testid="secondary-phrases-input"
          />
          <span className="field-help">Used to check H2 and body coverage of supporting variants.</span>
        </label>

        <div className="row">
          <button type="submit" className="btn primary" disabled={running} data-testid="analyse-btn">
            {running ? "Analysing…" : "Analyse page"}
          </button>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={renderJs}
              onChange={(e) => setRenderJs(e.target.checked)}
              data-testid="render-js-checkbox"
            />
            Render JS (slower; needed for SPAs)
          </label>
        </div>
      </form>

      <div className="card" style={{ marginTop: 22 }}>
        <h2 className="section-title">Recent audits</h2>
        <HistoryList />
      </div>
    </div>
  );
}
