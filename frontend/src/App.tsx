import React, { useState } from "react";
import { Navbar } from "./components/Navbar";
import { DashboardPage } from "./pages/DashboardPage";
import { CompanySearchPage } from "./pages/CompanySearchPage";
import { CompanyProfilePage } from "./pages/CompanyProfilePage";
import { MethodologyPage } from "./pages/MethodologyPage";

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<"dashboard" | "search" | "profile" | "methodology">("dashboard");
  const [selectedCik, setSelectedCik] = useState<string | null>("0000004977");

  const handleSelectCompany = (cik: string) => {
    setSelectedCik(cik);
    setActiveTab("profile");
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col font-sans">
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        selectedCik={selectedCik}
      />

      <main className="flex-1 pb-16">
        {activeTab === "dashboard" && <DashboardPage />}
        {activeTab === "search" && (
          <CompanySearchPage onSelectCompany={handleSelectCompany} />
        )}
        {activeTab === "profile" && (
          selectedCik ? (
            <CompanyProfilePage cik={selectedCik} />
          ) : (
            <div className="max-w-xl mx-auto my-20 text-center p-8 bg-white border border-slate-200 rounded-lg shadow-sm">
              <h2 className="text-lg font-bold text-slate-800">No Company Selected</h2>
              <p className="text-sm text-slate-500 mt-2">
                Please search for an SEC registrant or select one from the company database to inspect multi-modal forensic signals.
              </p>
              <button
                onClick={() => setActiveTab("search")}
                className="mt-4 px-4 py-2 bg-sky-600 text-white text-sm font-semibold rounded hover:bg-sky-700 transition"
              >
                Go to Company Search
              </button>
            </div>
          )
        )}
        {activeTab === "methodology" && <MethodologyPage />}
      </main>

      <footer className="border-t border-slate-200 bg-white py-6">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-xs text-slate-500 flex flex-col sm:flex-row justify-between items-center gap-2">
          <div>
            <span className="font-semibold text-slate-700">FinGuard-X</span> — Empirical Multi-Modal Accounting Anomaly Detection Platform
          </div>
          <div>
            Data sourced directly from SEC EDGAR (10-K filings) and SEC Accounting & Auditing Enforcement Releases (AAER).
          </div>
        </div>
      </footer>
    </div>
  );
};

export default App;
