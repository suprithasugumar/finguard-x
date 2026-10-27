import React, { useEffect, useState } from "react";
import {
  CompanyRiskResponse,
  CompanyFinancialsResponse,
  CompanyNarrativeResponse,
  CompanyGraphResponse,
  CompanyExplanationResponse,
} from "../types";
import {
  Building2,
  Calendar,
  AlertOctagon,
  FileText,
  Network,
  Calculator,
  GitCompare,
  TrendingUp,
  Layers,
  HelpCircle,
  ExternalLink,
} from "lucide-react";
import { NetworkGraphVisualizer } from "../components/NetworkGraphVisualizer";

interface CompanyProfilePageProps {
  cik: string;
}

export const CompanyProfilePage: React.FC<CompanyProfilePageProps> = ({ cik }) => {
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<"overview" | "numeric" | "narrative" | "graph" | "fncs">("overview");

  const [riskData, setRiskData] = useState<CompanyRiskResponse | null>(null);
  const [finData, setFinData] = useState<CompanyFinancialsResponse | null>(null);
  const [narrData, setNarrData] = useState<CompanyNarrativeResponse | null>(null);
  const [graphData, setGraphData] = useState<CompanyGraphResponse | null>(null);
  const [explData, setExplData] = useState<CompanyExplanationResponse | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchCompanyData = async () => {
      try {
        setLoading(true);
        const fyParam = selectedYear ? `?fiscal_year=${selectedYear}` : "";

        const [rRes, fRes, nRes, gRes, eRes] = await Promise.all([
          fetch(`/api/companies/${cik}/risk${fyParam}`),
          fetch(`/api/companies/${cik}/financials${fyParam}`),
          fetch(`/api/companies/${cik}/narrative${fyParam}`),
          fetch(`/api/companies/${cik}/graph${fyParam}`),
          fetch(`/api/companies/${cik}/explanation${fyParam}`),
        ]);

        if (!rRes.ok) throw new Error("Failed to load company risk profile");

        const rJson = await rRes.json();
        const fJson = fRes.ok ? await fRes.json() : null;
        const nJson = nRes.ok ? await nRes.json() : null;
        const gJson = gRes.ok ? await gRes.json() : null;
        const eJson = eRes.ok ? await eRes.json() : null;

        setRiskData(rJson);
        setFinData(fJson);
        setNarrData(nJson);
        setGraphData(gJson);
        setExplData(eJson);

        if (!selectedYear && rJson.selected_year) {
          setSelectedYear(rJson.selected_year);
        }
      } catch (err: any) {
        setError(err.message || "Failed to load company data");
      } finally {
        setLoading(false);
      }
    };

    fetchCompanyData();
  }, [cik, selectedYear]);

  if (loading) {
    return (
      <div className="py-24 text-center">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-sky-600 border-t-transparent"></div>
        <p className="mt-4 text-sm text-slate-500 font-medium">Assembling live multi-modal forensic profile for CIK {cik}...</p>
      </div>
    );
  }

  if (error || !riskData) {
    return (
      <div className="p-8 max-w-4xl mx-auto my-12 bg-red-50 border border-red-200 rounded-lg text-red-800">
        <h3 className="text-base font-semibold">Error Loading Profile</h3>
        <p className="text-sm mt-1">{error}</p>
      </div>
    );
  }

  const { company, available_years, risk } = riskData;
  const score = risk.risk_score;
  const category = risk.risk_category;

  let badgeBg = "bg-emerald-50 text-emerald-800 border-emerald-200";
  let gaugeColor = "#10b981";
  if (category === "Moderate") {
    badgeBg = "bg-sky-50 text-sky-800 border-sky-200";
    gaugeColor = "#0284c7";
  } else if (category === "High") {
    badgeBg = "bg-amber-50 text-amber-800 border-amber-200";
    gaugeColor = "#f59e0b";
  } else if (category === "Very High") {
    badgeBg = "bg-rose-50 text-rose-800 border-rose-200";
    gaugeColor = "#e11d48";
  }

  const isNumericAvail = finData?.selected_year != null;
  const isTextAvail = narrData?.selected_year?.narrative_drift_score != null;
  const isGraphAvail = graphData?.selected_year?.related_party_state === "graph_built" || (graphData?.selected_year?.graph_available === true && (graphData.selected_year.num_nodes || 0) > 1);
  const isFncsAvail = explData?.fncs?.fncs_score != null;
  const availCount = [isNumericAvail, isTextAvail, isGraphAvail, isFncsAvail].filter(Boolean).length;

  return (
    <div className="space-y-6 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* 1. Header Banner */}
      <div className="bg-white p-6 rounded-lg border border-slate-200 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-3">
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">{company.name}</h1>
            <span className="text-xs font-mono font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200">
              {company.ticker && company.ticker !== "N/A" ? company.ticker : "UNLISTED / CIK"}
            </span>
            <span className="text-xs text-slate-500 font-mono">CIK: {company.cik}</span>
            <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold border ${
              availCount === 4
                ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                : availCount >= 2
                ? "bg-sky-50 text-sky-700 border-sky-200"
                : "bg-slate-100 text-slate-600 border-slate-200"
            }`}>
              Data Completeness: {availCount}/4 Modalities
            </span>
          </div>
          <div className="text-xs text-slate-500 mt-1">
            SIC {company.sic} – {company.sic_description} | Exchange: {company.exchange && company.exchange !== "N/A" ? company.exchange : "SEC OTC / Private / Delisted"}
          </div>
        </div>

        {/* Year Selector */}
        <div className="flex items-center space-x-2">
          <Calendar className="w-4 h-4 text-slate-400" />
          <span className="text-xs font-medium text-slate-600">Reporting Period:</span>
          <select
            value={selectedYear || available_years[0]}
            onChange={(e) => setSelectedYear(Number(e.target.value))}
            className="text-xs font-semibold bg-slate-50 border border-slate-200 rounded-md px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-sky-500 text-slate-900 cursor-pointer"
          >
            {available_years.map((y) => (
              <option key={y} value={y}>
                Fiscal Year {y}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* 2. Top Risk Triage Summary Card */}
      <div className="bg-white p-6 rounded-lg border border-slate-200 shadow-sm">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-center">
          {/* Gauge & Score */}
          <div className="flex items-center space-x-5 border-b md:border-b-0 md:border-r border-slate-100 pb-4 md:pb-0 pr-0 md:pr-4">
            <div className="relative w-24 h-24 flex-shrink-0 flex items-center justify-center">
              <svg className="w-24 h-24 transform -rotate-90">
                <circle cx="48" cy="48" r="38" stroke="#f1f5f9" strokeWidth="8" fill="transparent" />
                <circle
                  cx="48"
                  cy="48"
                  r="38"
                  stroke={gaugeColor}
                  strokeWidth="8"
                  fill="transparent"
                  strokeDasharray="238.76"
                  strokeDashoffset={238.76 - (238.76 * score) / 100}
                  strokeLinecap="round"
                />
              </svg>
              <div className="absolute flex flex-col items-center">
                <span className="text-2xl font-black text-slate-900">{score}</span>
                <span className="text-[10px] text-slate-400 font-medium">/ 100</span>
              </div>
            </div>

            <div>
              <span className={`inline-flex items-center px-2.5 py-1 rounded text-xs font-bold border ${badgeBg}`}>
                {category} Priority
              </span>
              <div className="text-xs font-semibold text-slate-700 mt-1.5">
                {risk.review_priority_label}
              </div>
              <div className="text-[11px] text-slate-400 mt-0.5">
                Calibrated posterior: {(risk.fraud_probability * 100).toFixed(1)}%
              </div>
            </div>
          </div>

          {/* Executive Summary */}
          <div className="md:col-span-2">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">
              Plain-Language Forensic Summary
            </h3>
            <p className="text-xs text-slate-700 leading-relaxed bg-slate-50 p-3.5 rounded border border-slate-100">
              {risk.plain_language_summary}
            </p>
          </div>
        </div>

        {/* Multi-Modal Modality Risk Share Progress */}
        <div className="mt-6 pt-5 border-t border-slate-100">
          <div className="text-xs font-semibold text-slate-700 mb-2 flex justify-between">
            <span>Multi-Modal Anomaly Contribution Share</span>
            <span className="text-slate-400 font-normal">TreeSHAP attribution across 58 feature dimensions</span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { id: "numeric", label: "Numeric Ratios", color: "bg-blue-600", avail: isNumericAvail },
              { id: "text", label: "NLP Text Drift", color: "bg-purple-600", avail: isTextAvail },
              { id: "graph", label: "Related Graph", color: "bg-amber-600", avail: isGraphAvail },
              { id: "fncs", label: "FNCS Contradiction", color: "bg-emerald-600", avail: isFncsAvail },
            ].map((m) => {
              const modalityInfo = risk.modality_breakdown?.[m.id];
              const isModAvail = m.avail && modalityInfo?.risk_share_pct != null;
              const val = modalityInfo?.risk_share_pct;
              const shap = modalityInfo?.shap_sum;
              return (
                <div key={m.id} className="p-2.5 rounded bg-slate-50 border border-slate-100">
                  <div className="flex justify-between items-center text-xs">
                    <span className="font-medium text-slate-700">{m.label}</span>
                    <span className="font-bold text-slate-900">
                      {isModAvail && val != null ? (
                        `${val}%`
                      ) : (
                        <span className="text-slate-400 font-normal italic text-[11px]">Not available</span>
                      )}
                    </span>
                  </div>
                  <div className="w-full bg-slate-200 rounded-full h-1.5 mt-1.5 overflow-hidden">
                    <div
                      className={`h-full ${m.color}`}
                      style={{ width: isModAvail && val != null ? `${Math.min(100, Math.max(5, val))}%` : "0%" }}
                    />
                  </div>
                  <div className="text-[10px] text-slate-400 mt-1">
                    {isModAvail && shap != null ? (
                      `SHAP: ${shap > 0 ? "+" : ""}${shap.toFixed(3)}`
                    ) : (
                      "Modality not present"
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* 3. Deep Dive Navigation Tabs */}
      <div className="border-b border-slate-200">
        <nav className="flex space-x-6 text-xs font-medium">
          {[
            { id: "overview", label: "Top Risk Factors", icon: AlertOctagon },
            { id: "numeric", label: "Numeric & Beneish", icon: Calculator },
            { id: "narrative", label: "Text Narrative & Drift", icon: FileText },
            { id: "graph", label: "Related-Party Network", icon: Network },
            { id: "fncs", label: "FNCS Accounting Categories", icon: Layers },
          ].map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`py-3 px-1 border-b-2 flex items-center space-x-1.5 transition-colors ${
                  activeTab === tab.id
                    ? "border-sky-600 text-sky-700 font-semibold"
                    : "border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300"
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* 4. Tab Panels */}
      {/* Tab: Top Risk Factors Overview */}
      {activeTab === "overview" && (
        <div className="bg-white p-6 rounded-lg border border-slate-200 shadow-sm space-y-4">
          <h3 className="text-sm font-semibold text-slate-900">Top Individual Risk Drivers (XGBoost TreeSHAP)</h3>
          <p className="text-xs text-slate-500">
            Ranked by marginal positive contribution to fraud probability relative to cohort peer expectations.
          </p>

          <div className="space-y-3 mt-4">
            {risk.top_factors.map((f) => (
              <div key={f.rank} className="p-3.5 rounded bg-slate-50 border border-slate-200 flex flex-col sm:flex-row justify-between sm:items-center gap-2">
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="w-5 h-5 rounded-full bg-slate-200 text-slate-700 text-[10px] font-bold flex items-center justify-center">
                      {f.rank}
                    </span>
                    <span className="font-semibold text-slate-900 text-xs">{f.human_name}</span>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-200/70 text-slate-600 uppercase">
                      {f.modality}
                    </span>
                  </div>
                  <div className="text-xs text-slate-600 mt-1 pl-7">{f.plain_language}</div>
                </div>

                <div className="pl-7 sm:pl-0 text-right">
                  <span className="font-bold text-rose-600 text-xs">+{f.risk_contribution_pct}%</span>
                  <div className="text-[10px] text-slate-400 font-mono">SHAP: +{f.shap_value.toFixed(4)}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab: Numeric & Beneish Panel */}
      {activeTab === "numeric" && finData && (
        <div className="space-y-6">
          {/* Beneish Overview */}
          <div className="bg-white p-6 rounded-lg border border-slate-200 shadow-sm">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-900">Beneish M-Score Assessment</h3>
              {finData.selected_year?.beneish?.is_financial_firm && (
                <span className="text-xs bg-amber-100 text-amber-800 px-2.5 py-0.5 rounded font-medium border border-amber-200">
                  Financial Institution (SIC 6000–6999) — Excluded from Beneish
                </span>
              )}
            </div>
            <div className="mt-3 grid grid-cols-1 sm:grid-cols-4 gap-4">
              <div className="p-3.5 rounded bg-slate-50 border border-slate-200">
                <span className="text-xs text-slate-500">Beneish Neutral (Standardized)</span>
                <div className="text-xl font-bold text-slate-900 mt-1">
                  {finData.selected_year?.beneish?.neutral != null
                    ? finData.selected_year.beneish.neutral.toFixed(2)
                    : finData.selected_year?.beneish?.m_score?.toFixed(2) || (
                      <span className="text-slate-400 text-sm font-normal italic" title={finData.selected_year?.null_reasons?.beneish_strict || "Not available"}>
                        Not available
                      </span>
                    )}
                </div>
                <div className="text-[11px] text-slate-500 mt-0.5">
                  {finData.selected_year?.beneish?.n_components ? `${finData.selected_year.beneish.n_components}/8 components` : "Threshold -1.78"}
                </div>
              </div>

              <div className="p-3.5 rounded bg-slate-50 border border-slate-200">
                <span className="text-xs text-slate-500">Beneish Strict (8/8 Required)</span>
                <div className="text-xl font-bold text-slate-900 mt-1">
                  {finData.selected_year?.beneish?.strict != null ? (
                    finData.selected_year.beneish.strict.toFixed(2)
                  ) : (
                    <span
                      className="text-slate-400 text-xs font-normal italic cursor-help"
                      title={finData.selected_year?.null_reasons?.beneish_strict || "Incomplete components"}
                    >
                      {finData.selected_year?.beneish?.is_financial_firm
                        ? "N/A (Financial Firm)"
                        : "Not available (Missing components)"}
                    </span>
                  )}
                </div>
                <div className="text-[11px] text-slate-500 mt-0.5">Strict GAAP Disclosure</div>
              </div>

              <div className="p-3.5 rounded bg-slate-50 border border-slate-200">
                <span className="text-xs text-slate-500">Flag at -1.78 Threshold</span>
                <div className="text-base font-bold mt-1">
                  {finData.selected_year?.beneish?.flag_178 ? (
                    <span className="text-rose-600">Flagged Anomaly</span>
                  ) : (
                    <span className="text-emerald-600">Unflagged</span>
                  )}
                </div>
              </div>

              <div className="p-3.5 rounded bg-slate-50 border border-slate-200">
                <span className="text-xs text-slate-500">Flag at -2.22 Threshold</span>
                <div className="text-base font-bold mt-1">
                  {finData.selected_year?.beneish?.flag_222 ? (
                    <span className="text-rose-600">Flagged Anomaly</span>
                  ) : (
                    <span className="text-emerald-600">Unflagged</span>
                  )}
                </div>
              </div>
            </div>

            {/* 8 Beneish Indices */}
            <div className="mt-6">
              <h4 className="text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2">8 Beneish Sub-Indices</h4>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                {Object.entries(finData.selected_year?.beneish || {})
                  .filter(([k]) => ["dsri", "gmi", "aqi", "sgi", "depi", "sgai", "lvgi", "tata"].includes(k))
                  .map(([k, v]: [string, any]) => (
                    <div key={k} className="p-2.5 rounded bg-slate-50 border border-slate-100 flex justify-between items-center">
                      <span className="font-mono text-slate-600 uppercase">{k}</span>
                      {typeof v === "number" ? (
                        <span className="font-bold text-slate-900">{v.toFixed(3)}</span>
                      ) : (
                        <span
                          className="text-slate-400 italic text-[11px] cursor-help"
                          title={finData.selected_year?.null_reasons?.[`beneish_${k}`] || "Not reported"}
                        >
                          Not available
                        </span>
                      )}
                    </div>
                  ))}
              </div>
            </div>
          </div>

          {/* Multi-Year Financial Accounting Trends */}
          <div className="bg-white p-6 rounded-lg border border-slate-200 shadow-sm space-y-4">
            <div>
              <h3 className="text-sm font-semibold text-slate-900">Multi-Year Financial Trends (SEC 10-K Disclosures)</h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Trajectory of revenue, net income, operating cash flow, receivables, and margins across reporting periods.
              </p>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold uppercase tracking-wider text-[11px]">
                    <th className="py-2.5 px-3">Fiscal Year</th>
                    <th className="py-2.5 px-3">Revenue ($M)</th>
                    <th className="py-2.5 px-3">Net Income ($M)</th>
                    <th className="py-2.5 px-3">Operating CFO ($M)</th>
                    <th className="py-2.5 px-3">Receivables ($M)</th>
                    <th className="py-2.5 px-3">Operating Margin</th>
                    <th className="py-2.5 px-3">Net Margin</th>
                    <th className="py-2.5 px-3">Beneish M-Score</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {finData.history.map((h: any) => {
                    const isSel = h.fiscal_year === finData.selected_year?.fiscal_year;
                    const t = h.trends || {};
                    return (
                      <tr key={h.fiscal_year} className={isSel ? "bg-sky-50/60 font-semibold" : ""}>
                        <td className="py-2.5 px-3 font-mono text-slate-900">
                          FY{h.fiscal_year}
                          {isSel && (
                            <span className="ml-1.5 text-[10px] text-sky-700 bg-sky-100 px-1 py-0.5 rounded">Current</span>
                          )}
                        </td>
                        <td className="py-2.5 px-3 font-mono">
                          {t.revenue != null ? `$${(t.revenue / 1e6).toFixed(1)}M` : "N/A"}
                        </td>
                        <td className={`py-2.5 px-3 font-mono ${t.net_income != null && t.net_income < 0 ? "text-rose-600 font-bold" : ""}`}>
                          {t.net_income != null ? `$${(t.net_income / 1e6).toFixed(1)}M` : "N/A"}
                        </td>
                        <td className={`py-2.5 px-3 font-mono ${t.operating_cash_flow != null && t.operating_cash_flow < 0 ? "text-rose-600 font-bold" : ""}`}>
                          {t.operating_cash_flow != null ? `$${(t.operating_cash_flow / 1e6).toFixed(1)}M` : "N/A"}
                        </td>
                        <td className="py-2.5 px-3 font-mono">
                          {t.receivables != null ? `$${(t.receivables / 1e6).toFixed(1)}M` : "N/A"}
                        </td>
                        <td className="py-2.5 px-3 font-mono">
                          {t.operating_margin != null ? `${(t.operating_margin * 100).toFixed(1)}%` : "N/A"}
                        </td>
                        <td className="py-2.5 px-3 font-mono">
                          {t.net_margin != null ? `${(t.net_margin * 100).toFixed(1)}%` : "N/A"}
                        </td>
                        <td className="py-2.5 px-3 font-mono">
                          {h.beneish?.m_score != null ? (
                            <span className={h.beneish.m_score > -1.78 ? "text-rose-600 font-bold" : "text-slate-700"}>
                              {h.beneish.m_score.toFixed(2)}
                            </span>
                          ) : (
                            <span
                              className="text-slate-400 italic text-[11px] cursor-help"
                              title={h.null_reasons?.beneish_strict || "Not available"}
                            >
                              Not available
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* 18 Core Ratios */}
          <div className="bg-white p-6 rounded-lg border border-slate-200 shadow-sm">
            <h3 className="text-sm font-semibold text-slate-900 mb-3">18 Core Financial Accounting Ratios</h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 text-xs">
              {Object.entries(finData.selected_year?.ratios || {}).map(([k, v]: [string, any]) => (
                <div key={k} className="p-2.5 rounded bg-slate-50 border border-slate-100 flex justify-between items-center">
                  <span className="text-slate-600">{k.replace(/_/g, " ")}</span>
                  <span className="font-mono font-semibold text-slate-900">
                    {typeof v === "number" ? (
                      v.toFixed(4)
                    ) : (
                      <span
                        className="text-slate-400 italic text-[11px] cursor-help"
                        title={finData.selected_year?.null_reasons?.[k] || "Not available"}
                      >
                        Not available
                      </span>
                    )}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Tab: Narrative & Text Drift Panel */}
      {activeTab === "narrative" && narrData && (
        <div className="space-y-6">
          <div className="bg-white p-6 rounded-lg border border-slate-200 shadow-sm">
            <h3 className="text-sm font-semibold text-slate-900">NLP Narrative Drift & Disclosure Complexity</h3>
            <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div className="p-3 rounded bg-slate-50 border border-slate-200">
                <span className="text-slate-500">Semantic Drift Score</span>
                <div className="text-lg font-bold text-slate-900 mt-1">
                  {narrData.selected_year?.narrative_drift_score?.toFixed(3) ?? "N/A"}
                </div>
              </div>

              <div className="p-3 rounded bg-slate-50 border border-slate-200">
                <span className="text-slate-500">Cosine Embedding Drift</span>
                <div className="text-lg font-bold text-slate-900 mt-1">
                  {narrData.selected_year?.doc_embedding_cosine_drift?.toFixed(3) ?? "N/A"}
                </div>
              </div>

              <div className="p-3 rounded bg-slate-50 border border-slate-200">
                <span className="text-slate-500">Gunning Fog Index</span>
                <div className="text-lg font-bold text-slate-900 mt-1">
                  {narrData.selected_year?.readability_fog_index?.toFixed(1) ?? "N/A"}
                </div>
              </div>

              <div className="p-3 rounded bg-slate-50 border border-slate-200">
                <span className="text-slate-500">Uncertainty Density</span>
                <div className="text-lg font-bold text-slate-900 mt-1">
                  {narrData.selected_year?.uncertainty_rate?.toFixed(4) ?? "N/A"}
                </div>
              </div>
            </div>
          </div>

          {/* Drift Snippets Side-by-Side */}
          <div className="bg-white p-6 rounded-lg border border-slate-200 shadow-sm space-y-4">
            <h3 className="text-sm font-semibold text-slate-900">Semantic Revision Snippets (Year-over-Year Shift)</h3>
            <p className="text-xs text-slate-500">
              Low-match sentences in Item 7 MD&A indicating unexplained narrative pivots from prior disclosures.
            </p>

            {narrData.selected_year?.drift_evidence_snippets && narrData.selected_year.drift_evidence_snippets.length > 0 ? (
              <div className="space-y-3 mt-3">
                {narrData.selected_year.drift_evidence_snippets.slice(0, 4).map((s, idx) => (
                  <div key={idx} className="p-4 rounded bg-slate-50 border border-slate-200 grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                    <div>
                      <span className="font-semibold text-slate-700 block mb-1">Current Year Filing Statement:</span>
                      <p className="text-slate-800 bg-white p-2.5 rounded border border-slate-100 italic">
                        &quot;{s.current_sentence}&quot;
                      </p>
                    </div>
                    <div>
                      <span className="font-semibold text-slate-500 block mb-1">Nearest Prior Year Statement:</span>
                      <p className="text-slate-600 bg-white p-2.5 rounded border border-slate-100 italic">
                        &quot;{s.prior_sentence || "No prior sentence alignable."}&quot;
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-xs text-slate-400 py-6 text-center">No high-drift text snippets detected.</div>
            )}
          </div>
        </div>
      )}

      {/* Tab: Related-Party Knowledge Graph Panel */}
      {activeTab === "graph" && graphData && (
        <div className="space-y-6">
          <div className="bg-white p-6 rounded-lg border border-slate-200 shadow-sm">
            {(() => {
              const rpState = graphData.selected_year?.related_party_state || (
                graphData.selected_year?.graph_available && (graphData.selected_year?.num_nodes || 0) > 1
                  ? "graph_built"
                  : "no_note_disclosed"
              );
              const nodeChurn = graphData.selected_year?.yoy_node_churn || 0;
              const edgeChurn = graphData.selected_year?.yoy_edge_churn || 0;
              const hasHighChurn = rpState === "graph_built" && (nodeChurn > 0.3 || edgeChurn > 0.3);

              return (
                <>
                  <div className="flex justify-between items-center mb-3">
                    <h3 className="text-sm font-semibold text-slate-900">Related-Party Network Topology</h3>
                    <span className={`text-xs px-2.5 py-0.5 rounded font-semibold ${
                      rpState === "graph_built"
                        ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                        : rpState === "note_found_extraction_failed"
                        ? "bg-amber-50 text-amber-700 border border-amber-200"
                        : rpState === "note_by_reference"
                        ? "bg-slate-100 text-slate-600 border border-slate-200"
                        : "bg-slate-100 text-slate-500 border border-slate-200"
                    }`}>
                      {rpState === "graph_built" && "Graph Built"}
                      {rpState === "note_found_extraction_failed" && "Data-Quality Flag: Extraction Incomplete"}
                      {rpState === "note_by_reference" && "Disclosed by Reference to Proxy / Item 13"}
                      {rpState === "no_note_disclosed" && "No Note Disclosed"}
                    </span>
                  </div>

                  {/* Warning banner ONLY shown for (d) graph_built with churn above 0.30 threshold */}
                  {hasHighChurn && (
                    <div className="mb-4 p-3 rounded bg-amber-50 border border-amber-200 text-xs text-amber-800 space-y-1">
                      <div className="font-semibold text-amber-900">
                        Network Evolution Warning: Rapid YoY Related-Party Topology Churn
                      </div>
                      <div>
                        Elevated entity churn ({(nodeChurn * 100).toFixed(0)}%) or edge restructuring ({(edgeChurn * 100).toFixed(0)}%) detected in footnote disclosures, indicating potential structural reconfiguration or opacity risks.
                      </div>
                    </div>
                  )}

                  {/* Render based on the 4 distinct states */}
                  {rpState === "graph_built" ? (
                    <>
                      {/* Network Year Scrub Slider */}
                      {available_years && available_years.length > 1 && (
                        <div className="mb-5 p-4 rounded-lg bg-slate-50 border border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
                          <div className="flex items-center space-x-2">
                            <span className="font-semibold text-slate-700">Timeline Year Scrub:</span>
                            <span className="px-2 py-0.5 rounded bg-sky-100 text-sky-800 font-bold font-mono">
                              FY {selectedYear || available_years[0]}
                            </span>
                          </div>
                          <div className="flex items-center space-x-3 flex-1 max-w-md">
                            <span className="text-slate-400 font-mono text-[11px]">{available_years[available_years.length - 1]}</span>
                            <input
                              type="range"
                              min={0}
                              max={available_years.length - 1}
                              value={available_years.indexOf(selectedYear || available_years[0])}
                              onChange={(e) => {
                                const idx = parseInt(e.target.value, 10);
                                if (available_years[idx]) {
                                  setSelectedYear(available_years[idx]);
                                }
                              }}
                              className="w-full accent-sky-600 cursor-pointer"
                            />
                            <span className="text-slate-400 font-mono text-[11px]">{available_years[0]}</span>
                          </div>
                        </div>
                      )}

                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                        <div className="p-3 rounded bg-slate-50 border border-slate-200">
                          <span className="text-slate-500">Network Entities</span>
                          <div className="text-lg font-bold text-slate-900 mt-1">{graphData.selected_year?.num_nodes || 0}</div>
                        </div>
                        <div className="p-3 rounded bg-slate-50 border border-slate-200">
                          <span className="text-slate-500">Transaction Edges</span>
                          <div className="text-lg font-bold text-slate-900 mt-1">{graphData.selected_year?.num_edges || 0}</div>
                        </div>
                        <div className="p-3 rounded bg-slate-50 border border-slate-200">
                          <span className="text-slate-500">Shell / LLC Affiliates</span>
                          <div className="text-lg font-bold text-rose-600 mt-1">{graphData.selected_year?.num_undisclosed_or_shell || 0}</div>
                        </div>
                        <div className="p-3 rounded bg-slate-50 border border-slate-200">
                          <span className="text-slate-500">Opacity Anomaly Score</span>
                          <div className="text-lg font-bold text-slate-900 mt-1">
                            {graphData.selected_year?.graph_anomaly_score?.toFixed(3) || "0.000"}
                          </div>
                        </div>
                      </div>

                      {/* Interactive Network Diagram Visualizer */}
                      <div className="mt-6 border border-slate-200 rounded-lg p-6 bg-slate-50/50">
                        <h4 className="text-xs font-semibold text-slate-700 mb-3">Extracted Entity Network Topology</h4>
                        <NetworkGraphVisualizer
                          nodes={graphData.selected_year?.graph_payload?.nodes || []}
                          edges={graphData.selected_year?.graph_payload?.edges || []}
                          evidenceEdges={graphData.selected_year?.evidence_edges || []}
                          companyName={company.name}
                        />
                      </div>
                    </>
                  ) : rpState === "note_found_extraction_failed" ? (
                    <div className="p-6 rounded-lg bg-amber-50/60 border border-amber-200 text-xs space-y-2">
                      <div className="flex items-center space-x-2 font-bold text-sm text-amber-800">
                        <AlertOctagon className="w-4 h-4 text-amber-600 flex-shrink-0" />
                        <span>Data-Quality Flag: Footnote Disclosed, Entity Extraction Incomplete</span>
                      </div>
                      <p className="text-amber-700 leading-relaxed">
                        A related-party footnote disclosure was found in this 10-K filing, but automated entity-relation extraction could not parse structured transaction pairs. The footnote text is preserved in filing sections for manual inspection.
                      </p>
                    </div>
                  ) : rpState === "note_by_reference" ? (
                    <div className="p-6 rounded-lg bg-slate-50 border border-slate-200 text-xs space-y-2">
                      <div className="font-semibold text-sm text-slate-700">
                        Footnote Disclosed by Reference to Definitive Proxy / Item 13
                      </div>
                      <p className="text-slate-500 leading-relaxed">
                        This registrant incorporates information regarding certain relationships and related transactions by reference to its definitive Proxy Statement (Schedule 14A) pursuant to Part III, Item 13 of Form 10-K.
                      </p>
                    </div>
                  ) : (
                    <div className="p-6 rounded-lg bg-slate-50 border border-slate-200 text-xs space-y-2">
                      <div className="font-semibold text-sm text-slate-700">
                        No Related-Party Note Disclosed
                      </div>
                      <p className="text-slate-500 leading-relaxed">
                        No related-party transactions footnote disclosure was identified in this 10-K filing.
                      </p>
                    </div>
                  )}
                </>
              );
            })()}
          </div>
        </div>
      )}

      {/* Tab: FNCS Accounting Deception Categories Panel */}
      {activeTab === "fncs" && explData && (
        <div className="space-y-6">
          <div className="bg-white p-6 rounded-lg border border-slate-200 shadow-sm">
            <div className="flex justify-between items-center mb-3">
              <h3 className="text-sm font-semibold text-slate-900">Financial-Narrative Consistency Score (FNCS)</h3>
              <div className="flex space-x-2 text-xs">
                <span className="px-2.5 py-1 rounded bg-slate-100 font-mono text-slate-700">
                  Consistency: {explData.fncs?.fncs_score?.toFixed(2) ?? "N/A"}
                </span>
                <span className="px-2.5 py-1 rounded bg-rose-50 border border-rose-200 font-mono text-rose-700 font-semibold">
                  Contradiction: {explData.fncs?.contradiction_score?.toFixed(2) ?? "N/A"}
                </span>
              </div>
            </div>

            <div className="mb-4 p-3 rounded bg-sky-50 border border-sky-200 text-xs text-sky-800">
              <strong>Notice:</strong> Potential inconsistency between quantitative accounting ratios and qualitative MD&A disclosure tone.
            </div>

            <p className="text-xs text-slate-500">
              Cross-modal divergence between quantitative accounting ratios (z-score + tanh) and qualitative MD&A tone (Loughran-McDonald).
            </p>

            {/* 7 Accounting Categories Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-5">
              {Object.entries(explData.fncs?.categories || {}).map(([k, c]: [string, any]) => (
                <div key={k} className="p-4 rounded-lg bg-slate-50 border border-slate-200 space-y-2 text-xs">
                  <div className="flex justify-between items-center">
                    <span className="font-bold text-slate-900">{c.name}</span>
                    <span className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                      c.contradiction_xc != null && c.contradiction_xc > 0.25
                        ? "bg-rose-100 text-rose-800"
                        : c.contradiction_xc != null
                        ? "bg-emerald-100 text-emerald-800"
                        : "bg-slate-100 text-slate-500"
                    }`}>
                      {c.contradiction_xc != null ? `Contradiction: ${c.contradiction_xc.toFixed(2)}` : (c.status || "N/A")}
                    </span>
                  </div>

                  <div className="grid grid-cols-3 gap-2 py-1 border-y border-slate-200/60 text-[11px]">
                    <div>
                      <span className="text-slate-400 block">Numeric Signal</span>
                      <span className="font-mono font-semibold text-slate-800">
                        {c.numeric_signal_nc != null ? `${c.numeric_signal_nc > 0 ? "+" : ""}${c.numeric_signal_nc.toFixed(2)}` : "N/A"}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-400 block">Text Tone</span>
                      <span className="font-mono font-semibold text-slate-800">
                        {c.text_tone_tc != null ? `${c.text_tone_tc > 0 ? "+" : ""}${c.text_tone_tc.toFixed(2)}` : "N/A"}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-400 block">Relevance Weight</span>
                      <span className="font-mono font-semibold text-slate-800">
                        {c.presence_weight_wc != null ? c.presence_weight_wc.toFixed(2) : "N/A"}
                      </span>
                    </div>
                  </div>

                  {c.retrieved_sentence ? (
                    <div className="mt-2">
                      <span className="text-[10px] text-slate-500 font-semibold block mb-0.5">Retrieved Disclosure Sentence:</span>
                      <p className="text-[11px] text-slate-700 bg-white p-2.5 rounded border border-slate-100 italic">
                        &quot;{c.retrieved_sentence}&quot;
                      </p>
                    </div>
                  ) : (
                    <div className="mt-2 text-[11px] text-slate-400 italic">
                      Status: {c.status === "below_similarity_threshold" ? "Disclosure below semantic relevance threshold (0.32)" : c.status || "No disclosure"}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
