import React from "react";
import { ShieldAlert, BarChart3, Search, Building2 } from "lucide-react";

interface NavbarProps {
  activeTab: "dashboard" | "search" | "profile";
  setActiveTab: (tab: "dashboard" | "search" | "profile") => void;
  selectedCik: string | null;
}

export const Navbar: React.FC<NavbarProps> = ({ activeTab, setActiveTab, selectedCik }) => {
  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center space-x-3 cursor-pointer" onClick={() => setActiveTab("dashboard")}>
          <div className="w-9 h-9 rounded-lg bg-sky-700 flex items-center justify-center text-white font-bold text-lg shadow-sm">
            F
          </div>
          <div>
            <span className="text-xl font-bold tracking-tight text-slate-900">FinGuard<span className="text-sky-600">-X</span></span>
            <span className="ml-2 text-xs font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
              Forensic Risk Platform
            </span>
          </div>
        </div>

        <nav className="flex space-x-1">
          <button
            onClick={() => setActiveTab("dashboard")}
            className={`px-3.5 py-2 rounded-md text-sm font-medium flex items-center space-x-2 transition-colors ${
              activeTab === "dashboard"
                ? "bg-sky-50 text-sky-700 font-semibold"
                : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
            }`}
          >
            <BarChart3 className="w-4 h-4" />
            <span>Dashboard & Ablation</span>
          </button>

          <button
            onClick={() => setActiveTab("search")}
            className={`px-3.5 py-2 rounded-md text-sm font-medium flex items-center space-x-2 transition-colors ${
              activeTab === "search"
                ? "bg-sky-50 text-sky-700 font-semibold"
                : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
            }`}
          >
            <Search className="w-4 h-4" />
            <span>Company Search</span>
          </button>

          <button
            onClick={() => setActiveTab("profile")}
            disabled={!selectedCik}
            className={`px-3.5 py-2 rounded-md text-sm font-medium flex items-center space-x-2 transition-colors ${
              !selectedCik
                ? "text-slate-300 cursor-not-allowed"
                : activeTab === "profile"
                ? "bg-sky-50 text-sky-700 font-semibold"
                : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
            }`}
          >
            <Building2 className="w-4 h-4" />
            <span>Company Risk Profile</span>
          </button>
        </nav>

        <div className="flex items-center space-x-2">
          <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
            SEC EDGAR Connected
          </span>
        </div>
      </div>
    </header>
  );
};
