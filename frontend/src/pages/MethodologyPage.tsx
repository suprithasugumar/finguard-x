import React from "react";
import { BookOpen, Database, Shield, Layers, Scale, GitBranch } from "lucide-react";

export const MethodologyPage: React.FC = () => {
  return (
    <div className="space-y-6 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* 1. Header */}
      <div className="bg-white p-6 rounded-lg border border-slate-200 shadow-sm">
        <div className="flex items-center space-x-3">
          <div className="p-2 rounded-lg bg-sky-50 text-sky-700">
            <BookOpen className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900 tracking-tight">System Methodology & Data Architecture</h1>
            <p className="text-xs text-slate-500 mt-0.5">
              Scientific foundations, data provenance verification, label reconstruction funnel, and multimodal evaluation design.
            </p>
          </div>
        </div>
      </div>

      {/* 2. Core Pillars Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Pillar 1 */}
        <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm space-y-3">
          <div className="flex items-center space-x-2 text-sky-700">
            <Database className="w-5 h-5" />
            <h3 className="text-sm font-semibold text-slate-900">SEC EDGAR Bulk Ingestion</h3>
          </div>
          <p className="text-xs text-slate-600 leading-relaxed">
            All data is ingested directly from authentic SEC EDGAR bulk archives (<code>companyfacts.zip</code> and <code>submissions.zip</code>) covering 14,841 registrants, 128,091 annual filings, and over 4.19M verified XBRL facts. Zero synthetic fixtures or simulated data exist in production tables.
          </p>
          <div className="text-[11px] font-mono text-slate-500 bg-slate-50 p-2 rounded border border-slate-100">
            Rule R1: Automated Provenance Check pre-flight gate on all records.
          </div>
        </div>

        {/* Pillar 2 */}
        <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm space-y-3">
          <div className="flex items-center space-x-2 text-indigo-700">
            <Scale className="w-5 h-5" />
            <h3 className="text-sm font-semibold text-slate-900">AAER Positive Labels & Controls</h3>
          </div>
          <p className="text-xs text-slate-600 leading-relaxed">
            Accounting and Auditing Enforcement Releases (AAERs) are parsed via <code>pypdf</code> to extract authentic misstated fiscal years. 185 corporate positive company-years across 104 independent CIKs are matched 1:5 against 921 clean control company-years on 2-digit SIC, fiscal year, and total assets &plusmn;30% with zero contamination.
          </p>
          <div className="text-[11px] font-mono text-slate-500 bg-slate-50 p-2 rounded border border-slate-100">
            Cohort: 185 Positives vs 921 Controls (1,106 Total Company-Years).
          </div>
        </div>

        {/* Pillar 3 */}
        <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm space-y-3">
          <div className="flex items-center space-x-2 text-emerald-700">
            <Layers className="w-5 h-5" />
            <h3 className="text-sm font-semibold text-slate-900">Four Analytical Modalities</h3>
          </div>
          <p className="text-xs text-slate-600 leading-relaxed">
            Integrates (1) Numeric signals including 18 core ratios and all 8 Beneish M-Score components, (2) Textual MD&amp;A semantic drift using MiniLM sentence embeddings, (3) Related-party transaction graphs with shell affiliate tracking, and (4) Financial-Narrative Contradiction Scores (FNCS).
          </p>
          <div className="text-[11px] font-mono text-slate-500 bg-slate-50 p-2 rounded border border-slate-100">
            Spec Taxonomy: GROWTH, PROFITABILITY, LIQUIDITY, DEMAND, CASH FLOW, RISK, OUTLOOK.
          </div>
        </div>
      </div>

      {/* 3. Evaluation & Inference Standards */}
      <div className="bg-white p-6 rounded-lg border border-slate-200 shadow-sm space-y-4">
        <div className="flex items-center space-x-2 text-slate-900">
          <GitBranch className="w-5 h-5 text-sky-600" />
          <h2 className="text-base font-semibold">Evaluation Design & Out-of-Fold Explanations</h2>
        </div>
        <p className="text-xs text-slate-600 leading-relaxed">
          FinGuard-X enforces strict forward-looking temporal isolation and group-aware cross validation:
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          <div className="p-4 rounded-lg bg-slate-50 border border-slate-200 space-y-2">
            <span className="font-semibold text-slate-800">Primary Evaluation: Time-Aware Held-Out Split</span>
            <ul className="list-disc list-inside space-y-1 text-slate-600">
              <li><strong>Train Split:</strong> Earlier fiscal years (&le; FY2018, 614 records).</li>
              <li><strong>Validation Split:</strong> Middle fiscal years (FY2019–FY2020, 267 records).</li>
              <li><strong>Held-Out Test Split:</strong> Latest fiscal years (FY2021–FY2023, 225 records).</li>
              <li><strong>Zero CIK Leakage:</strong> Registrants never cross partitions.</li>
            </ul>
          </div>
          <div className="p-4 rounded-lg bg-slate-50 border border-slate-200 space-y-2">
            <span className="font-semibold text-slate-800">Honest Statistical Inference</span>
            <ul className="list-disc list-inside space-y-1 text-slate-600">
              <li><strong>CIK-Cluster Bootstrap:</strong> B = 2000 resamples preserving firm clustering.</li>
              <li><strong>Holm-Bonferroni Correction:</strong> Controls family-wise error across M9 vs M1, M2, M8.</li>
              <li><strong>Out-of-Fold Scores:</strong> All displayed risk scores and TreeSHAP attributions come strictly from held-out predictions.</li>
              <li><strong>Prevalence Baseline:</strong> Every PR-AUC is displayed beside its random-guess prevalence baseline.</li>
            </ul>
          </div>
        </div>
      </div>

      {/* 4. Ethical & Regulatory Boundary Notice */}
      <div className="bg-amber-50 p-6 rounded-lg border border-amber-200 text-xs text-amber-900 space-y-2">
        <div className="flex items-center space-x-2 font-bold text-sm text-amber-950">
          <Shield className="w-4 h-4" />
          <span>Decision Support and Forensic Triage Policy (Rule R5)</span>
        </div>
        <p className="leading-relaxed">
          FinGuard-X is an automated triage decision-support tool designed for forensic accounting examination, regulatory scoping, and audit resource allocation. Model predictions, calibrated probabilities, and TreeSHAP attributions indicate statistical anomaly review priority—never legal or regulatory proof of intentional misrepresentation.
        </p>
      </div>
    </div>
  );
};
