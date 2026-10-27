"""Financial-Narrative Contradiction Score (FNCS) Engine (Novelty 1 / Novelty 3)."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import yaml

from backend.app.nlp.narrative_drift import (
    CONDITIONAL_WORDS,
    LM_FIN_UNCERTAINTY,
    LM_NEGATIVE,
    LM_UNCERTAINTY,
    EmbeddingCache,
    clean_sentences,
)

logger = logging.getLogger("finguard.fncs.engine")

# Comprehensive Loughran-McDonald Lexicon + Financial Sentiment Directionals
LM_POSITIVE = {
    "able", "abundance", "abundant", "acclaim", "accomplish", "accomplished", "accomplishes",
    "accomplishing", "accomplishment", "accomplishments", "achieve", "achieved", "achieves",
    "achieving", "achievement", "achievements", "adequately", "advancement", "advancements",
    "advances", "advancing", "advantageous", "advantageously", "advantages", "alliance",
    "alliances", "assure", "assured", "assures", "assuring", "attainable", "attractive",
    "attractively", "beneficial", "beneficially", "benefit", "benefited", "benefiting", "benefits",
    "best", "better", "bolster", "bolstered", "bolstering", "bolsters", "boom", "booming",
    "boost", "boosted", "boosting", "boosts", "breakthrough", "breakthroughs", "brilliant",
    "collaborate", "collaborated", "collaborates", "collaborating", "collaboration",
    "collaborations", "collaborative", "conducive", "confident", "constructive", "constructively",
    "creative", "creatively", "creativity", "dependable", "desirable", "desired", "distinctive",
    "distinctively", "distinguish", "distinguished", "distinguishes", "distinguishing",
    "diversify", "diversified", "diversifies", "diversifying", "diversification", "earnings",
    "ease", "easy", "easily", "effective", "effectively", "effectiveness", "efficiencies",
    "efficiency", "efficient", "efficiently", "empower", "empowered", "empowering", "empowers",
    "enable", "enabled", "enables", "enabling", "enhance", "enhanced", "enhancement",
    "enhancements", "enhances", "enhancing", "enjoy", "enjoyed", "enjoying", "enjoys",
    "enthusiastic", "enthusiastically", "enthusiasm", "excel", "excelled", "excelling", "excels",
    "excellence", "excellent", "exceed", "exceeded", "exceeding", "exceeds", "exceptional",
    "exceptionally", "exclusive", "exclusively", "exclusivity", "exemplary", "expand", "expanded",
    "expanding", "expands", "expansion", "expansions", "expansive", "expedite", "expedited",
    "favorable", "favorably", "favored", "favoring", "favorite", "favorites", "flexibility",
    "flexible", "flourish", "flourished", "flourishing", "flourishes", "gain", "gained",
    "gaining", "gains", "generate", "generated", "generates", "generating", "good", "great",
    "greater", "greatest", "greatly", "greatness", "grow", "growing", "grown", "grows",
    "growth", "growths", "grew", "happy", "happily", "healthy", "highest", "honor",
    "honorable", "honored", "ideal", "ideally", "impressive", "impressively", "improve",
    "improved", "improvement", "improvements", "improves", "improving", "incredible",
    "innovate", "innovated", "innovates", "innovating", "innovation", "innovations", "innovative",
    "innovatively", "insight", "insightful", "inspiration", "inspire", "inspired", "integrity",
    "leadership", "leading", "loyal", "loyalty", "lucrative", "merit", "milestone", "milestones",
    "modernize", "modernized", "modernizes", "momentum", "outperform", "outperformed",
    "outperforming", "outperforms", "overcome", "paramount", "partner", "partnered",
    "partnering", "partners", "partnership", "partnerships", "perfect", "perfected", "perfectly",
    "phenomenal", "pioneer", "pioneered", "pioneering", "popular", "positive", "positively",
    "premiere", "prestigious", "proactive", "productive", "productively", "productivity",
    "profitable", "profit", "profitability", "profits", "profited", "profiting", "progress",
    "progressed", "progresses", "progressing", "progression", "progressive", "prosper",
    "prospered", "prospering", "prospers", "prosperity", "prosperous", "rebound", "rebounded",
    "rebounding", "rebounds", "record", "records", "recover", "recovered", "recovering",
    "recovers", "recovery", "reliable", "reliably", "resolve", "resolved", "resolves",
    "respect", "respected", "reward", "rewarded", "rewarding", "rewards", "robust",
    "robustness", "safe", "safer", "safest", "safely", "safety", "satisfactory", "satisfied",
    "satisfies", "satisfying", "solid", "solidly", "solidity", "sound", "soundly", "soundness",
    "spectacular", "stability", "stable", "stabilize", "stabilized", "stabilizes", "stabilizing",
    "steady", "stimulate", "stimulated", "stimulates", "strength", "strengthen", "strengthened",
    "strengthening", "strengthens", "strengths", "strong", "stronger", "strongest", "strongly",
    "succeed", "succeeded", "succeeding", "succeeds", "success", "successes", "successful",
    "successfully", "superior", "surpass", "surpassed", "surpasses", "surpassing", "sustain",
    "sustained", "sustaining", "sustains", "sustainable", "thrive", "thrived", "thrives",
    "thriving", "trust", "trusted", "trustworthy", "unmatched", "unparalleled", "upbeat",
    "valuable", "value", "values", "win", "winner", "winners", "winning", "wins", "worth",
    # Financial Directional Positive Words
    "increase", "increased", "increases", "increasing", "higher", "rise", "rose", "rising",
    "risen", "surplus", "accretive", "upside"
}

LM_NEGATIVE_EXPANDED = {
    "abandon", "abandoned", "abandoning", "abandonment", "adverse", "adversely", "adversity",
    "affect", "affected", "against", "aggravate", "aggravated", "aggravating", "aggressive",
    "alert", "allege", "alleged", "allegation", "allegations", "ambiguous", "anomalous",
    "anomaly", "anomalies", "anticompetitive", "antitrust", "arrest", "arrested", "assault",
    "avert", "averted", "avoid", "avoided", "avoiding", "avoids", "awkward", "backdate",
    "backdated", "backslide", "bailout", "bankrupt", "bankruptcy", "bankruptcies", "barrier",
    "barriers", "betray", "blame", "blamed", "boycott", "breach", "breached", "breaches",
    "breaching", "break", "breakage", "breakdown", "breakdowns", "bribe", "bribery", "cancel",
    "cancelled", "cancelling", "cancellation", "cancellations", "cancels", "careless",
    "catastrophe", "catastrophic", "caution", "cautionary", "cease", "ceased", "ceases",
    "ceasing", "censure", "censured", "challenge", "challenged", "challenges", "challenging",
    "circumvent", "close", "closed", "closure", "closures", "collude", "collusion", "collapse",
    "collapsed", "collapsing", "complication", "complications", "complain", "complaint",
    "complaints", "compromise", "compromised", "concern", "concerned", "concerns", "concerning",
    "condemn", "confine", "conflict", "conflicts", "conflicting", "confront", "confronted",
    "constraint", "constraints", "contagion", "contend", "contentious", "costly", "crash",
    "crashed", "criminal", "crisis", "crises", "critical", "criticize", "criticized",
    "curtail", "curtailed", "curtailment", "cut", "cuts", "cutting", "damage", "damages",
    "damaged", "damaging", "danger", "dangerous", "deadlock", "decline", "declined",
    "declines", "declining", "default", "defaulted", "defaulting", "defaults", "defeat",
    "defect", "defective", "deficiency", "deficiencies", "deficient", "deficit", "deficits",
    "defraud", "defrauded", "degrade", "degraded", "delay", "delayed", "delaying", "delays",
    "delinquent", "delinquency", "demise", "deny", "denied", "denies", "deplete", "depleted",
    "depress", "depressed", "depression", "deprive", "deprived", "derail", "derailed",
    "destroy", "destroyed", "destroying", "destruction", "destructive", "deteriorate",
    "deteriorated", "deteriorates", "deteriorating", "deterioration", "deteriorations",
    "detract", "detriment", "detrimental", "difficult", "difficulties", "difficulty",
    "diminish", "diminished", "diminishes", "diminishing", "disadvantage", "disadvantaged",
    "disaster", "disastrous", "disclaim", "disclaimer", "disclose", "discontinued",
    "discontinuance", "discontinue", "discrepancy", "discrepancies", "dismiss", "dismissed",
    "disorder", "dispute", "disputes", "disputed", "disrupt", "disrupted", "disrupting",
    "disruption", "disruptions", "disruptive", "dissatisfied", "dissolve", "dissolved",
    "distortion", "distress", "distressed", "divest", "divestiture", "divestitures",
    "doubt", "doubtful", "downside", "downturn", "downturns", "drop", "dropped", "dropping",
    "drops", "dwindle", "dwindled", "embarrass", "encumber", "encumbrance", "enforce",
    "enforcement", "erroneous", "error", "errors", "escalate", "evade", "evasion", "excess",
    "excessive", "excessively", "exclude", "exclusion", "expire", "expired", "exposure",
    "exposures", "fail", "failed", "failing", "fails", "failure", "failures", "fall",
    "fallen", "falling", "falls", "fell", "false", "falsify", "fault", "faulty", "fear",
    "fears", "freeze", "friction", "grievance", "halt", "halted", "halting", "hamper",
    "hampered", "hard", "hardship", "hardships", "harm", "harmed", "harmful", "harsh",
    "hazard", "hazardous", "hinder", "hindrance", "hostile", "illicit", "impair", "impaired",
    "impairing", "impairment", "impairments", "impairs", "impede", "impediment", "inability",
    "inadequate", "inadequately", "inappropriate", "incident", "indictment", "ineffective",
    "inefficiency", "inefficiencies", "infringe", "infringement", "injunction", "injury",
    "insolvent", "insolvency", "investigation", "investigations", "jeopardize", "lawsuit",
    "lawsuits", "liquidate", "liquidated", "liquidating", "liquidation", "liquidations",
    "litigate", "litigated", "litigating", "litigation", "litigations", "litigant", "loss",
    "losses", "lost", "lose", "losing", "malfeasance", "malpractice", "misappropriate",
    "mislead", "misleading", "misstatement", "misstatements", "negative", "negatively",
    "negligence", "obstacle", "obstacles", "oppose", "outflow", "outflows", "overdue",
    "overstate", "overstated", "overstatement", "pain", "penalize", "penalized", "penalty",
    "penalties", "peril", "plead", "pleaded", "precarious", "prevent", "prevented", "punitive",
    "recall", "recalled", "recession", "recessionary", "reduction", "reductions", "restructure",
    "restructured", "restructuring", "restructurings", "risk", "risks", "risky", "sanction",
    "sanctions", "scandal", "scrutiny", "severe", "severely", "severity", "shortage",
    "shortfall", "shortfalls", "shrink", "shrinkage", "shrinking", "shrank", "shrunk",
    "shutdown", "slowdown", "slowdowns", "sluggish", "slump", "stagnant", "stagnation",
    "strain", "strained", "stress", "stressed", "strike", "strikes", "subpoena", "suffer",
    "suffered", "suffering", "suffers", "suspend", "suspended", "suspension", "tarnish",
    "terminate", "terminated", "terminates", "terminating", "termination", "terminations",
    "threat", "threaten", "threatened", "threatening", "threats", "trouble", "troubled",
    "turbulent", "turbulence", "unable", "unattractive", "uncertain", "uncertainty",
    "uncertainties", "unclear", "uncollectible", "uncollectable", "unfavorable", "unfavorably",
    "unforeseen", "unmitigated", "unprofitable", "unstable", "unsettled", "vulnerable",
    "vulnerability", "vulnerabilities", "warn", "warned", "warning", "warnings", "waste",
    "weaken", "weakened", "weakening", "weakens", "weakness", "weaknesses", "windup",
    "write-down", "writedown", "writedowns", "write-off", "writeoff", "writeoffs",
    # Financial Directional Negative Words
    "decrease", "decreased", "decreases", "decreasing", "lower", "lowest", "contract",
    "contracted", "contracting", "contraction", "underperform", "underperformed"
}


def compute_lm_tone(sentence: str) -> Tuple[float, int, int, int]:
    """Compute Loughran-McDonald tone score in [-1.0, 1.0] for a single sentence."""
    tokens = [w.strip(".,;:!?\"'()[]{}") for w in sentence.lower().split()]
    pos = sum(1 for t in tokens if t in LM_POSITIVE)
    neg = sum(1 for t in tokens if t in LM_NEGATIVE_EXPANDED)
    unc = sum(
        1
        for t in tokens
        if t in LM_UNCERTAINTY or t in LM_FIN_UNCERTAINTY or t in CONDITIONAL_WORDS
    )

    total_sentiment = pos + neg + unc
    if total_sentiment == 0:
        return 0.0, 0, 0, 0

    raw_tone = (pos - neg) / float(pos + neg + unc)
    # Apply hedging/uncertainty discount if positive but heavily hedged
    if raw_tone > 0 and unc > 0:
        discount = max(0.5, 1.0 - 0.15 * unc)
        raw_tone *= discount

    bounded_tone = float(max(-1.0, min(1.0, raw_tone)))
    return bounded_tone, pos, neg, unc


class FNCSEngine:
    """Computes cross-modal financial-narrative contradiction scores across 7 accounting deception categories."""

    def __init__(
        self,
        prototypes_path: Optional[Path] = None,
        embedding_cache: Optional[EmbeddingCache] = None,
    ):
        if prototypes_path is None:
            prototypes_path = Path(__file__).parent / "prototypes.yaml"

        with open(prototypes_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        self.categories_config = config.get("categories", {})
        self.embedding_cache = embedding_cache or EmbeddingCache()
        self._prototype_embeddings: Dict[str, np.ndarray] = {}
        self._precompute_prototypes()

    def _precompute_prototypes(self):
        """Precompute MiniLM embeddings for the versioned category prototype sentences."""
        for cat_key, cat_data in self.categories_config.items():
            protos = cat_data.get("prototypes", [])
            if protos:
                embeds = self.embedding_cache.embed_sentences(protos)
                # Normalize embeddings for fast cosine similarity
                norms = np.linalg.norm(embeds, axis=1, keepdims=True) + 1e-9
                self._prototype_embeddings[cat_key] = embeds / norms
                logger.debug(f"Precomputed {len(protos)} prototype embeddings for {cat_key}")

    def score_company_year(
        self,
        numeric_signals: Dict[str, float],
        mda_text: Optional[str],
        category_z_scores: Dict[str, float],
    ) -> Dict[str, Any]:
        """Compute 7 category contradiction scores, composite FNCS, and plain-language explanations."""
        # 1. Parse text sentences
        sentences = clean_sentences(mda_text or "", max_sentences=100) if mda_text else []
        sentence_embeds = None
        if sentences:
            raw_embeds = self.embedding_cache.embed_sentences(sentences)
            norms = np.linalg.norm(raw_embeds, axis=1, keepdims=True) + 1e-9
            sentence_embeds = raw_embeds / norms

        category_scores: Dict[str, Optional[float]] = {}
        category_statuses: Dict[str, str] = {}
        category_evidence: Dict[str, Any] = {}
        explanation_sentences: List[str] = []

        weighted_contradiction = 0.0
        total_eval_weight = 0.0

        for cat_key, cat_data in self.categories_config.items():
            weight = float(cat_data.get("weight", 0.14))
            cat_name = cat_data.get("name", cat_key)

            # A. Numeric Signal: tanh(z_score) in [-1.0, 1.0]
            z_val = category_z_scores.get(cat_key, 0.0)
            n_c = float(np.tanh(z_val))

            # B. Text Tone & Semantic Retrieval
            proto_embeds = self._prototype_embeddings.get(cat_key)
            t_c: Optional[float] = None
            w_c: Optional[float] = None
            x_c: Optional[float] = None
            top_sentence = ""
            top_sim = 0.0
            top_pos, top_neg, top_unc = 0, 0, 0
            status = "no_mda"

            if sentence_embeds is None or len(sentence_embeds) == 0:
                status = "no_mda"
            elif proto_embeds is None:
                status = "no_prototypes"
            else:
                # Cosine similarities matrix: (num_sentences, num_prototypes)
                sim_matrix = np.dot(sentence_embeds, proto_embeds.T)
                max_sim_per_sentence = np.max(sim_matrix, axis=1)

                # Filter sentences by relevance threshold (cosine sim >= 0.32)
                relevant_indices = np.where(max_sim_per_sentence >= 0.32)[0]
                if len(relevant_indices) == 0:
                    status = "below_similarity_threshold"
                else:
                    status = "ok"
                    # Sort by relevance descending
                    sorted_rel = relevant_indices[
                        np.argsort(-max_sim_per_sentence[relevant_indices])
                    ][:4]
                    tones = []
                    sim_weights = []

                    for idx in sorted_rel:
                        sent = sentences[idx]
                        sim = float(max_sim_per_sentence[idx])
                        tone, pos, neg, unc = compute_lm_tone(sent)
                        tones.append(tone)
                        sim_weights.append(sim)

                    # Top sentence evidence
                    best_idx = sorted_rel[0]
                    top_sentence = sentences[best_idx]
                    top_sim = float(max_sim_per_sentence[best_idx])
                    _, top_pos, top_neg, top_unc = compute_lm_tone(top_sentence)

                    # Similarity-weighted mean tone
                    w_arr = np.array(sim_weights)
                    t_c = float(np.sum(np.array(tones) * w_arr) / np.sum(w_arr))
                    w_c = float(min(1.0, top_sim * 1.5))

                    # C. Contradiction Gap & Score
                    d_c = t_c - n_c
                    tolerance = 0.15

                    if d_c > tolerance:
                        x_c = w_c * min(1.0, (d_c - tolerance) * 1.25)
                    elif d_c < -tolerance:
                        x_c = w_c * min(1.0, (abs(d_c) - tolerance) * 0.4)
                    else:
                        x_c = 0.0

                    x_c = float(max(0.0, min(1.0, x_c)))
                    weighted_contradiction += weight * x_c
                    total_eval_weight += weight

            category_scores[cat_key] = x_c
            category_statuses[cat_key] = status

            # Record category evidence
            category_evidence[cat_key] = {
                "name": cat_name,
                "weight": weight,
                "status": status,
                "numeric_signal_nc": round(n_c, 4),
                "numeric_z_score": round(z_val, 4),
                "text_tone_tc": round(t_c, 4) if t_c is not None else None,
                "presence_weight_wc": round(w_c, 4) if w_c is not None else None,
                "contradiction_xc": round(x_c, 4) if x_c is not None else None,
                "retrieved_sentence": top_sentence,
                "top_similarity": round(top_sim, 4),
                "sentiment_counts": {"pos": top_pos, "neg": top_neg, "unc": top_unc},
            }

            # D. Template-based Explanation Sentence
            if x_c is not None and x_c >= 0.25 and top_sentence and t_c is not None:
                num_desc = "deteriorated significantly" if n_c < -0.4 else "showed weakness"
                tone_desc = "strongly optimistic" if t_c > 0.4 else "favorable"
                expl = (
                    f"Potential contradiction detected in {cat_name}: "
                    f"MD&A disclosure tone is {tone_desc} ({t_c:+.2f}) whereas quantitative indicators "
                    f"{num_desc} (signal {n_c:+.2f}). "
                    f'Supporting disclosure: "{top_sentence[:180]}..."'
                )
                explanation_sentences.append(expl)

        # Composite Contradiction Score [0.0, 1.0]
        if total_eval_weight > 0:
            comp_contradiction = float(weighted_contradiction / total_eval_weight)
            comp_contradiction = float(max(0.0, min(1.0, comp_contradiction)))
            fncs_score = float(max(0.0, min(1.0, 1.0 - comp_contradiction)))
        else:
            comp_contradiction = None
            fncs_score = None

        if not explanation_sentences:
            if fncs_score is not None:
                explanation_sentences.append(
                    f"Financial narrative alignment index is {fncs_score:.2f}. "
                    "Disclosed qualitative commentary corresponds with quantitative operating performance."
                )
            else:
                explanation_sentences.append(
                    "Narrative alignment not computable: MD&A section missing or no category disclosure met the relevance threshold."
                )

        return {
            "cat_growth": category_scores.get("growth"),
            "cat_profitability": category_scores.get("profitability"),
            "cat_liquidity": category_scores.get("liquidity"),
            "cat_demand": category_scores.get("demand"),
            "cat_cash_flow": category_scores.get("cash_flow"),
            "cat_risk": category_scores.get("risk"),
            "cat_outlook": category_scores.get("outlook"),
            "category_statuses": category_statuses,
            # Maintain legacy aliases temporarily as None or values to prevent KeyError
            "cat1_revenue_recognition": None,
            "cat2_inventory_valuation": None,
            "cat3_reserve_manipulation": None,
            "cat4_capitalized_expenses": None,
            "cat5_related_party": None,
            "cat6_governance_executive": None,
            "cat7_going_concern": None,
            "contradiction_score": comp_contradiction,
            "fncs_score": fncs_score,
            "fncs_evidence": category_evidence,
            "explanation_sentences": explanation_sentences[:4],
        }
