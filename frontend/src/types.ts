export interface CompanySearchItem {
  cik: string;
  ticker: string;
  name: string;
  sic: string;
  sic_description: string;
  latest_year: number;
  has_aaer_positive: boolean;
  latest_risk_score: number;
  latest_risk_category: string;
  review_priority_label: string;
}

export interface CompanyRiskResponse {
  company: {
    cik: string;
    ticker: string;
    name: string;
    sic: string;
    sic_description: string;
    exchange: string;
  };
  available_years: number[];
  selected_year: number;
  risk: {
    fraud_probability: number;
    risk_score: number;
    risk_category: string;
    review_priority_label: string;
    modality_breakdown: Record<string, { risk_share_pct: number; shap_sum: number }>;
    top_factors: Array<{
      rank: number;
      feature_name: string;
      human_name: string;
      modality: string;
      raw_value: number;
      shap_value: number;
      risk_contribution_pct: number;
      plain_language: string;
    }>;
    plain_language_summary: string;
  };
}

export interface CompanyFinancialsResponse {
  selected_year: {
    fiscal_year: number;
    accession_number: string;
    beneish: {
      m_score: number | null;
      flag_178: boolean | null;
      flag_222: boolean | null;
      dsri: number | null;
      gmi: number | null;
      aqi: number | null;
      sgi: number | null;
      depi: number | null;
      sgai: number | null;
      lvgi: number | null;
      tata: number | null;
    };
    ratios: Record<string, number | null>;
  };
  history: Array<any>;
}

export interface DriftSnippet {
  current_sentence: string;
  prior_sentence?: string;
  min_similarity?: number;
  drift_distance?: number;
}

export interface CompanyNarrativeResponse {
  selected_year: {
    fiscal_year: number;
    accession_number: string;
    narrative_drift_score: number | null;
    doc_embedding_cosine_drift: number | null;
    vocab_jaccard_distance: number | null;
    uncertainty_rate: number | null;
    negative_sentiment_rate: number | null;
    financial_uncertainty_rate: number | null;
    avg_sentence_length: number | null;
    readability_fog_index: number | null;
    drift_evidence_snippets: DriftSnippet[];
  } | null;
  history: Array<any>;
}

export interface GraphNode {
  id: string;
  label: string;
  type: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: string;
  weight?: number;
}

export interface CompanyGraphResponse {
  selected_year: {
    fiscal_year: number;
    accession_number: string;
    graph_available: boolean;
    graph_size: number;
    num_nodes: number;
    num_edges: number;
    density: number;
    avg_degree: number;
    num_officers: number;
    num_entities: number;
    num_undisclosed_or_shell: number;
    max_clique_size: number;
    clustering_coefficient: number;
    betweenness_centrality_max: number;
    yoy_node_churn: number;
    yoy_edge_churn: number;
    graph_anomaly_score: number;
    graph_payload: {
      nodes: GraphNode[];
      edges: GraphEdge[];
    };
    evidence_edges: Array<{
      source: string;
      target: string;
      relation: string;
      evidence_sentence: string;
    }>;
  } | null;
  history: Array<any>;
}

export interface CompanyExplanationResponse {
  fiscal_year: number;
  accession_number: string;
  fraud_probability: number;
  risk_score: number;
  risk_category: string;
  review_priority_label: string;
  modality_breakdown: Record<string, { risk_share_pct: number; shap_sum: number }>;
  top_factors: Array<any>;
  plain_language_summary: string;
  evidence_snippets: DriftSnippet[];
  evidence_edges: Array<any>;
  fncs?: {
    fncs_score: number | null;
    contradiction_score: number | null;
    explanation_sentences: string[];
    categories: Record<string, any>;
  };
}

export interface ModelResultItem {
  key: string;
  model_id: number;
  model_name: string;
  clf_type: string;
  pr_auc: number;
  pr_auc_ci: [number, number, number];
  roc_auc: number;
  roc_auc_ci: [number, number, number];
  f1: number;
  f1_ci: [number, number, number];
  balanced_acc: number;
  balanced_acc_ci: [number, number, number];
  confusion_matrix: number[][];
}

export interface ModelResultsResponse {
  models: ModelResultItem[];
  folds: {
    positives: number[];
    controls: number[];
  };
  paired_tests: {
    xgboost: {
      pr_auc_diff: { mean: number; ci_95: [number, number]; p_value: number };
      roc_auc_diff: { mean: number; ci_95: [number, number]; p_value: number };
    };
    logreg: {
      pr_auc_diff: { mean: number; ci_95: [number, number]; p_value: number };
      roc_auc_diff: { mean: number; ci_95: [number, number]; p_value: number };
    };
  };
  redundancy_report: {
    fncs_alone: Record<string, any>;
    correlations: Record<string, any>;
    permutation_importance: Record<string, number>;
  };
}

export interface DatasetStatsResponse {
  database: {
    total_companies: number;
    total_filings: number;
    total_financial_facts: number;
    total_sections: number;
  };
  cohort: {
    total_records: number;
    positive_records: number;
    control_records: number;
    unique_positives: number;
    unique_controls: number;
    pos_to_ctrl_ratio: string;
  };

  risk_distribution: Record<string, number>;
  coverage: {
    usable_graphs: number;
    total_graphs: number;
    graph_usable_pct: number;
    fncs_coverage_pct: number;
  };
}
