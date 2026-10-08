import React, { useEffect, useState } from "react";
import { CompanySearchItem } from "../types";
import { Search, Building2, ExternalLink, Filter, ShieldCheck, ShieldAlert } from "lucide-react";

interface CompanySearchPageProps {
  onSelectCompany: (cik: string) => void;
}

export const CompanySearchPage: React.FC<CompanySearchPageProps> = ({ onSelectCompany }) => {
  const [companies, setCompanies] = useState<CompanySearchItem[]>([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string>("ALL");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchCompanies = async () => {
      try {
        setLoading(true);
        const url = searchTerm ? `/api/companies?q=${encodeURIComponent(searchTerm)}` : "/api/companies";
        const res = await fetch(url);
        if (!res.ok) throw new Error("Search failed");
        const data = await res.json();
        setCompanies(data);
      } catch (err) {
        console.error("Search error:", err);
      } finally {
        setLoading(false);
      }
    };

    const timer = setTimeout(() => {
      fetchCompanies();
    }, 200);

    return () => clearTimeout(timer);
  }, [searchTerm]);

  const filteredCompanies = companies.filter((c) => {
    if (categoryFilter === "ALL") return true;
    if (categoryFilter === "AAER_POSITIVE") return c.has_aaer_positive;
    return c.latest_risk_category === categoryFilter;
  });

  return (
    <div className="space-y-6 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* 1. Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Registrant Forensic Search</h1>
        <p className="text-sm text-slate-500 mt-1">
          Explore SEC EDGAR cohort registrants triaged by Calibrated Multi-Modal Fraud Risk Score.
        </p>
      </div>

      {/* 2. Search & Filter Bar */}
      <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm space-y-4">
        <div className="relative">
          <Search className="w-5 h-5 absolute left-3 top-3 text-slate-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search by company name, ticker symbol (e.g., AEP, MOOG, COTY), or 10-digit CIK..."
            className="w-full pl-10 pr-4 py-2 text-sm bg-slate-50 border border-slate-200 rounded-md focus:outline-none focus:ring-2 focus:ring-sky-500 focus:bg-white transition-all text-slate-900"
          />
        </div>

        {/* Filter Pills */}
        <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-slate-100 text-xs">
          <span className="text-slate-400 font-medium flex items-center mr-1">
            <Filter className="w-3.5 h-3.5 mr-1" /> Filter:
          </span>
          {[
            { id: "ALL", label: "All Registrants" },
            { id: "Very High", label: "Very High (80+)" },
            { id: "High", label: "High (60–79)" },
            { id: "Moderate", label: "Moderate (30–59)" },
            { id: "Low", label: "Low Risk (0–29)" },
            { id: "AAER_POSITIVE", label: "AAER Corporate Positives" },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setCategoryFilter(tab.id)}
              className={`px-3 py-1.5 rounded-full font-medium transition-colors ${
                categoryFilter === tab.id
                  ? "bg-sky-600 text-white"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* 3. Results Table */}
      <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
        <div className="py-3 px-6 bg-slate-50 border-b border-slate-200 flex justify-between items-center text-xs font-medium text-slate-500">
          <span>Showing {filteredCompanies.length} registrants</span>
          <span>Ranked by Calibrated Risk Priority</span>
        </div>

        {loading ? (
          <div className="py-16 text-center text-sm text-slate-500">Loading registrants...</div>
        ) : filteredCompanies.length === 0 ? (
          <div className="py-16 text-center text-sm text-slate-500">No matching registrants found.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 font-semibold text-slate-700 uppercase tracking-wider">
                  <th className="py-3 px-4">Company Name & Ticker</th>
                  <th className="py-3 px-3">CIK</th>
                  <th className="py-3 px-3">SIC Industry</th>
                  <th className="py-3 px-3">Latest FY</th>
                  <th className="py-3 px-3">Calibrated Risk Score</th>
                  <th className="py-3 px-3">Triage Priority</th>
                  <th className="py-3 px-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredCompanies.map((c) => {
                  const score = c.latest_risk_score;
                  const cat = c.latest_risk_category;
                  const isHigh = score >= 60;
                  const isPos = c.has_aaer_positive;

                  let badgeColor = "bg-emerald-50 text-emerald-800 border-emerald-200";
                  let barColor = "bg-emerald-500";
                  if (cat === "Moderate") {
                    badgeColor = "bg-sky-50 text-sky-800 border-sky-200";
                    barColor = "bg-sky-500";
                  } else if (cat === "High") {
                    badgeColor = "bg-amber-50 text-amber-800 border-amber-200";
                    barColor = "bg-amber-500";
                  } else if (cat === "Very High") {
                    badgeColor = "bg-rose-50 text-rose-800 border-rose-200";
                    barColor = "bg-rose-500";
                  }

                  return (
                    <tr
                      key={c.cik}
                      onClick={() => onSelectCompany(c.cik)}
                      className="hover:bg-slate-50 cursor-pointer transition-colors"
                    >
                      <td className="py-3.5 px-4">
                        <div className="flex items-center space-x-2">
                          {isPos && (
                            <span className="w-2 h-2 rounded-full bg-rose-500 flex-shrink-0" title="Corporate AAER Positive" />
                          )}
                          <div>
                            <div className="font-semibold text-slate-900">{c.name}</div>
                            <div className="text-[11px] text-slate-400 font-mono">{c.ticker !== "N/A" ? c.ticker : "UNLISTED"}</div>
                          </div>
                        </div>
                      </td>
                      <td className="py-3.5 px-3 font-mono text-slate-600">{c.cik}</td>
                      <td className="py-3.5 px-3 text-slate-600 max-w-xs truncate" title={c.sic_description}>
                        {c.sic} – {c.sic_description}
                      </td>
                      <td className="py-3.5 px-3 font-medium text-slate-700">FY{c.latest_year}</td>
                      <td className="py-3.5 px-3">
                        <div className="flex items-center space-x-2">
                          <span className="font-bold text-slate-900 w-7">{score}</span>
                          <div className="w-20 bg-slate-100 rounded-full h-1.5 overflow-hidden">
                            <div
                              className={`h-full ${barColor}`}
                              style={{ width: `${Math.max(4, score)}%` }}
                            />
                          </div>
                        </div>
                      </td>
                      <td className="py-3.5 px-3">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold border ${badgeColor}`}>
                          {cat}
                        </span>
                      </td>
                      <td className="py-3.5 px-4 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectCompany(c.cik);
                          }}
                          className="px-2.5 py-1 text-xs font-semibold rounded bg-sky-50 text-sky-700 hover:bg-sky-100 transition-colors inline-flex items-center space-x-1"
                        >
                          <span>Inspect</span>
                          <ExternalLink className="w-3 h-3" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
