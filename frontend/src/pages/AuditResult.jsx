import { Link, useParams } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { auditApi, API } from "@/lib/api";

const AREA_LABEL = {
  url:               "URL",
  meta_title:        "Meta title",
  meta_description:  "Meta description",
  h1:                "H1",
  h2:                "H2 sub-headings",
  content:           "Content",
  internal_linking:  "Internal linking",
  schema:            "Schema",
  images:            "Images",
  faq:               "FAQ",
};

function ScoreRing({ value }) {
  const cls = value >= 75 ? "ring-good" : value >= 50 ? "ring-warn" : "ring-bad";
  return (
    <div className={`score-ring ${cls}`} data-testid="overall-score-ring">
      <div className="score-ring-value">{value}</div>
      <div className="score-ring-label">/ 100</div>
    </div>
  );
}

function ExportMenu({ auditId }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState("");
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onClick = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  // Synchronous download. Critical: do NOT await anything before .click() —
  // Chrome requires the download to happen in the same tick as the user
  // gesture or it silently refuses. Cross-origin downloads with
  // `Content-Disposition: attachment` (set by the backend) trigger the
  // browser's download flow rather than a page navigation.
  const download = (fmt, evt) => {
    if (evt) { evt.preventDefault(); evt.stopPropagation(); }
    const url = `${API}/audits/${auditId}/export?format=${fmt}`;
    console.log("[TSE Export]", fmt, "→", url);
    setErr("");
    setBusy(fmt);
    try {
      const a = document.createElement("a");
      a.href = url;
      a.download = `tse-audit-${auditId.slice(0, 8)}.${fmt}`;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.style.display = "none";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => { setBusy(null); setOpen(false); }, 400);
    } catch (e) {
      console.error("[TSE Export] anchor click failed:", e);
      setErr("Download failed: " + (e?.message || e));
      setBusy(null);
      // Last-resort fallback — open the export URL in a new tab so the user
      // can right-click → Save As if the direct download is blocked.
      try {
        window.open(url, "_blank", "noopener,noreferrer");
      } catch (_openErr) {
        // already reported via setErr above
      }
    }
  };

  const openUrl = (fmt) => `${API}/audits/${auditId}/export?format=${fmt}`;

  return (
    <div className="export-menu" ref={ref}>
      <button
        type="button"
        className="btn"
        onClick={() => setOpen((v) => !v)}
        data-testid="export-btn"
        aria-expanded={open}
      >
        Export report ▾
      </button>
      {open && (
        <div className="export-menu-pop" data-testid="export-menu-pop">
          <a className="export-menu-item" href={openUrl("pdf")}
             target="_blank" rel="noopener noreferrer"
             download={`tse-audit-${auditId.slice(0, 8)}.pdf`}
             onClick={(e) => download("pdf", e)}
             data-testid="export-pdf">
            {busy === "pdf" ? "Preparing PDF…" : "PDF (.pdf)"}
          </a>
          <a className="export-menu-item" href={openUrl("md")}
             target="_blank" rel="noopener noreferrer"
             download={`tse-audit-${auditId.slice(0, 8)}.md`}
             onClick={(e) => download("md", e)}
             data-testid="export-md">
            {busy === "md" ? "Preparing Markdown…" : "Markdown (.md)"}
          </a>
          <a className="export-menu-item" href={openUrl("txt")}
             target="_blank" rel="noopener noreferrer"
             download={`tse-audit-${auditId.slice(0, 8)}.txt`}
             onClick={(e) => download("txt", e)}
             data-testid="export-txt">
            {busy === "txt" ? "Preparing text…" : "Plain text (.txt)"}
          </a>
          {err && <div className="export-menu-error" data-testid="export-error">{err}</div>}
          <div className="export-menu-hint">If nothing happens, right-click an option → “Save link as…”.</div>
        </div>
      )}
    </div>
  );
}

function AreaBars({ areaScores }) {
  if (!areaScores) return null;
  return (
    <div className="area-bars">
      {Object.keys(AREA_LABEL).map(k => {
        const v = areaScores[k] ?? 0;
        const cls = v >= 75 ? "bar-good" : v >= 50 ? "bar-warn" : "bar-bad";
        return (
          <div className="area-bar" key={k}>
            <div className="area-bar-head">
              <span>{AREA_LABEL[k]}</span>
              <span className="area-bar-val">{v}</span>
            </div>
            <div className="area-bar-track">
              <div className={`area-bar-fill ${cls}`} style={{ width: `${v}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function CheckList({ items, kind, testid, emptyText }) {
  if (!items?.length) {
    return <ul className={`checklist checklist-${kind}`} data-testid={testid}><li className="muted">{emptyText || "None."}</li></ul>;
  }
  return (
    <ul className={`checklist checklist-${kind}`} data-testid={testid}>
      {items.map((c, i) => (
        <li key={`${c.key}-${i}`} className={`check check-${c.priority}`}>
          <div className="check-head">
            <span className={`prio prio-${c.priority}`}>{c.priority.toUpperCase()}</span>
            <span className="check-label">{c.label}</span>
            <span className="check-area">{AREA_LABEL[c.area] || c.area}</span>
          </div>
          {c.detail && <div className="check-detail">{c.detail}</div>}
        </li>
      ))}
    </ul>
  );
}

export default function AuditResult() {
  const { auditId } = useParams();
  const [audit, setAudit] = useState(null);
  const [loading, setLoading] = useState(true);
  const [reRunning, setReRunning] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    auditApi.get(auditId)
      .then(d => { if (alive) setAudit(d); })
      .catch(e => { if (alive) setError(e.message); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [auditId]);

  const rerun = () => {
    if (!audit) return;
    setReRunning(true); setError("");
    auditApi.run({
      url: audit.url,
      primary_phrase: audit.primary_phrase,
      secondary_phrases: audit.secondary_phrases || [],
      render_js: audit.render_method === "js",
    })
      .then(setAudit)
      .catch(e => setError(e.response?.data?.detail || e.message))
      .finally(() => setReRunning(false));
  };

  if (loading) {
    return (
      <div className="page loading" data-testid="result-loading">
        <div className="spinner" />
        <div className="muted">Loading audit…</div>
      </div>
    );
  }
  if (!audit) {
    return (
      <div className="page" data-testid="result-not-found">
        <Link to="/" className="back-link">← New audit</Link>
        <h1 className="page-title">Audit not found</h1>
        <p className="muted">{error || "It may have been deleted or evicted from history."}</p>
      </div>
    );
  }

  return (
    <div className="page" data-testid="audit-result-page">
      <Link to="/" className="back-link" data-testid="back-to-home">← New audit</Link>

      <header className="result-head">
        <div>
          <div className="brand">TSE Page Auditor</div>
          <div className="result-url" data-testid="result-url">{audit.final_url || audit.url}</div>
          <div className="result-meta">
            <span data-testid="result-phrase">Phrase: <strong>{audit.primary_phrase}</strong></span>
            <span>·</span>
            <span>{audit.render_method === "js" ? "JS-rendered" : "HTTP fetch"} in {audit.fetch_ms}ms</span>
            <span>·</span>
            <span>HTTP {audit.fetch_status}</span>
          </div>
        </div>
        <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
          <ScoreRing value={audit.overall_score} />
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <button className="btn" onClick={rerun} disabled={reRunning} data-testid="rerun-btn">
              {reRunning ? "Re-running…" : "Re-analyse"}
            </button>
            <ExportMenu auditId={audit.id} />
          </div>
        </div>
      </header>

      {error && <div className="alert error" data-testid="rerun-error">{error}</div>}

      <section className="card">
        <h2 className="section-title">Area scores</h2>
        <AreaBars areaScores={audit.area_scores} />
      </section>

      <section className="card grid-3">
        <div>
          <h2 className="section-title">Strengths</h2>
          <CheckList items={audit.strengths} kind="pass" testid="strengths-list" emptyText="No strengths detected." />
        </div>
        <div>
          <h2 className="section-title">Weaknesses</h2>
          <CheckList items={audit.weaknesses} kind="fail" testid="weaknesses-list" emptyText="No weaknesses detected." />
        </div>
        <div>
          <h2 className="section-title">Recommendations</h2>
          <CheckList items={audit.recommendations} kind="warn" testid="recommendations-list" emptyText="No recommendations." />
        </div>
      </section>

      <section className="card">
        <h2 className="section-title">Page basics</h2>
        <dl className="facts">
          <dt>Meta title</dt><dd>{audit.page_snapshot?.title || <span className="muted">—</span>}</dd>
          <dt>Meta description</dt><dd>{audit.page_snapshot?.meta_description || <span className="muted">—</span>}</dd>
          <dt>Canonical</dt><dd>{audit.page_snapshot?.canonical || <span className="muted">—</span>}</dd>
          <dt>H1</dt><dd>{audit.page_snapshot?.h1?.length ? audit.page_snapshot.h1.join(" · ") : <span className="muted">—</span>}</dd>
          <dt>H2s</dt><dd>{audit.page_snapshot?.h2?.length ? audit.page_snapshot.h2.join(" · ") : <span className="muted">—</span>}</dd>
          <dt>Word count</dt><dd>{audit.page_snapshot?.word_count ?? 0}</dd>
          <dt>Internal links</dt><dd>{audit.page_snapshot?.internal_link_count ?? 0}</dd>
          <dt>External links</dt><dd>{audit.page_snapshot?.external_link_count ?? 0}</dd>
          <dt>Images</dt>
          <dd>
            {audit.page_snapshot?.image_count ?? 0}
            {audit.page_snapshot?.image_count > 0 && (
              <> · alt coverage {Math.round((audit.page_snapshot?.image_alt_coverage ?? 0) * 100)}%</>
            )}
          </dd>
          <dt>Schema types</dt>
          <dd>{audit.page_snapshot?.schema_types?.length ? audit.page_snapshot.schema_types.join(", ") : <span className="muted">—</span>}</dd>
          <dt>FAQ items</dt><dd>{audit.page_snapshot?.faq_count ?? 0}</dd>
          <dt>Secondary phrases</dt>
          <dd>{audit.secondary_phrases?.length ? audit.secondary_phrases.join(", ") : <span className="muted">—</span>}</dd>
        </dl>
      </section>
    </div>
  );
}
