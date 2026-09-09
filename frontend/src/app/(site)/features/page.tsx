import { Hero, Section } from "@/components/ui";

export const metadata = { title: "Features" };

const GROUPS = [
  { id: "repository", title: "Research repository & dataset catalogue", items: ["Versioned uploads with checksum, MIME sniffing and malware-scan hook", "Asynchronous processing: validation → extraction → OCR → chunking → embedding → indexing", "Draft → review → approval → publication workflow with reviewer comments", "Tabular profiling, observation ingestion linked to administrative units", "Provenance, licensing, quality notes and related-document graph"] },
  { id: "search", title: "Hybrid search", items: ["Keyword search (OpenSearch or PostgreSQL full-text) fused with pgvector semantic search using reciprocal rank fusion", "Faceted filters: type, topic, geography, year, organisation, language, source", "Autocomplete, saved searches and search history", "Relevance explanation per result (keyword rank, vector rank, matched-by)"] },
  { id: "ai", title: "Evidence-based AI assistant", items: ["Query analysis → hybrid retrieval → re-ranking → evidence selection → citation-only generation", "Refuses to answer without sufficient evidence; never fabricates sources", "Confidence score with stated basis and limitations", "Every answer stored as a recommendation with evidence items and a provenance graph"] },
  { id: "gis", title: "GIS & remote sensing", items: ["Administrative hierarchy (country → state → district → sub-district → village) with real PostGIS geometry", "Thematic layers with legends, temporal validity and per-unit statistics", "Operations: intersection, geodesic area, proximity, aggregation, hotspot, boundary select, affected-area buffer", "STAC connector for Sentinel/Landsat scenes; NDVI/NDWI/NDBI, rule-based land cover and change detection"] },
  { id: "analytics", title: "Analytics engine", items: ["Descriptive statistics, linear trend, geographic comparison, correlation, anomaly detection, forecasting with intervals, composite risk scores, time-series profiles and spatial roll-ups", "Model registry with algorithms, parameters, evaluation notes and limitations", "Every run produces a recommendation with dataset-version evidence"] },
  { id: "simulation", title: "Policy simulation lab", items: ["Scenario baselines derived from observed land-cover layers or declared assumptions", "Interventions: reallocation, yield improvement, irrigation expansion, rainfall shifts", "Monte Carlo propagation of coefficient uncertainty with p10–p90 bands", "Outputs labelled OBSERVED / MODELLED / ASSUMPTION / SCENARIO / UNCERTAINTY, risk flags, scenario comparison and policy-maker approval"] },
  { id: "collab", title: "Workspaces & innovation portal", items: ["Workspaces with members, linked resources, tasks, comments, activity and a review-to-publish lifecycle", "Challenges with structured evaluation criteria, weighted scoring, shortlisting and pilot tracking"] },
  { id: "security", title: "Security, administration & integrations", items: ["JWT access tokens, rotating refresh tokens with reuse detection, lockout, password policy", "Thirteen roles, ~45 permissions, approvals queue, user lifecycle and system settings", "Append-only audit log with request IDs; security headers; rate limiting", "Connectors: geoBoundaries, data.gov.in, STAC imagery, OpenSearch, S3/MinIO, OpenAI-compatible LLMs, SMTP"] },
];

export default function FeaturesPage() {
  return (
    <>
      <Hero title="Platform" accent="Features" subtitle="Everything needed to move from documents and data to accountable policy insight." crumbs={[{ label: "Home", href: "/" }, { label: "Features" }]} tag="Knowledge for a Sustainable India" />
      <Section>
        <div className="grid gap-6 md:grid-cols-2">
          {GROUPS.map((g) => (
            <div key={g.id} id={g.id} className="card p-6">
              <h2 className="text-lg font-bold text-navy-800">{g.title}</h2>
              <ul className="mt-3 space-y-2 text-sm text-slate-700">{g.items.map((i) => <li key={i} className="flex gap-2"><span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" />{i}</li>)}</ul>
            </div>
          ))}
        </div>
      </Section>
    </>
  );
}
