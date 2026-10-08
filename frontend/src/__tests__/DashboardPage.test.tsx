import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { DashboardPage } from "../pages/DashboardPage";

// Mock fetch API globally
const mockStats = {
  database: {
    total_companies: 14841,
    total_filings: 128091,
    total_financial_facts: 4196717,
    total_sections: 128091,
  },
  cohort: {
    total_records: 1106,
    positive_records: 185,
    control_records: 921,
    unique_positives: 104,
    unique_controls: 697,
    pos_to_ctrl_ratio: "1 : 5",
  },
  risk_distribution: {
    Low: 450,
    Moderate: 420,
    High: 156,
    "Very High": 80,
  },
  coverage: {
    usable_graphs: 920,
    total_graphs: 1106,
    graph_usable_pct: 83.18,
    fncs_coverage_pct: 100.0,
  },
};

const mockResults = {
  models: [
    {
      key: "Model 1_Baseline",
      model_id: 1,
      model_name: "Model 1: Beneish M-Score Baseline",
      clf_type: "Rule-based Baseline",
      pr_auc: 0.165,
      pr_auc_ci: [0.165, 0.125, 0.215],
      roc_auc: 0.505,
      roc_auc_ci: [0.505, 0.45, 0.56],
      f1: 0.0755,
      f1_ci: [0.0755, 0.0, 0.16],
      balanced_acc: 0.501,
      balanced_acc_ci: [0.501, 0.47, 0.53],
      confusion_matrix: [[900, 21], [175, 10]],
    },
    {
      key: "Model 9_XGBoost",
      model_id: 9,
      model_name: "Model 9: Full Multimodal Fusion",
      clf_type: "XGBoost",
      pr_auc: 0.285,
      pr_auc_ci: [0.285, 0.21, 0.36],
      roc_auc: 0.635,
      roc_auc_ci: [0.635, 0.56, 0.71],
      f1: 0.325,
      f1_ci: [0.325, 0.24, 0.41],
      balanced_acc: 0.595,
      balanced_acc_ci: [0.595, 0.53, 0.66],
      confusion_matrix: [[840, 81], [115, 70]],
    },
  ],
  folds: {
    positives: [37, 37, 37, 37, 37],
    controls: [184, 184, 184, 184, 185],
  },
  paired_tests: {
    xgboost: {
      pr_auc_diff: { mean: 0.045, ci_95: [0.012, 0.082], p_value: 0.005 },
      roc_auc_diff: { mean: 0.052, ci_95: [0.015, 0.095], p_value: 0.008 },
    },
    logreg: {
      pr_auc_diff: { mean: 0.021, ci_95: [-0.005, 0.048], p_value: 0.082 },
      roc_auc_diff: { mean: 0.025, ci_95: [-0.008, 0.058], p_value: 0.075 },
    },
  },
  redundancy_report: {},
};

describe("DashboardPage Component Integration", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/api/dataset/stats")) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(mockStats),
          });
        }
        if (url.includes("/api/models/results")) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(mockResults),
          });
        }
        return Promise.reject(new Error(`Unhandled URL: ${url}`));
      })
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders live SEC cohort telemetry cards without hardcoded fallbacks", async () => {
    render(<DashboardPage />);

    // Wait for data to load
    await waitFor(() => {
      expect(screen.getByText("Platform Telemetry & Multi-Modal Ablation")).toBeInTheDocument();
    });

    // Check DB counts
    expect(screen.getByText("14,841")).toBeInTheDocument();
    expect(screen.getByText("1,106")).toBeInTheDocument();
    expect(screen.getByText(/185 Positives/)).toBeInTheDocument();
    expect(screen.getByText(/921 Controls/)).toBeInTheDocument();

    // Check Risk category buckets
    expect(screen.getByText("Low Risk (0–29)")).toBeInTheDocument();
    expect(screen.getByText("450")).toBeInTheDocument();
    expect(screen.getByText("Very High (80–100)")).toBeInTheDocument();
    expect(screen.getByText("80")).toBeInTheDocument();

    // Check Ablation table models
    expect(screen.getByText("Model 1: Beneish M-Score Baseline")).toBeInTheDocument();
    expect(screen.getByText("Model 9: Full Multimodal Fusion")).toBeInTheDocument();

    // Ground rule check: "fraud detected" must never be rendered as a definitive label
    const pageText = document.body.textContent || "";
    expect(pageText.toLowerCase()).not.toContain("fraud detected");
  });
});
