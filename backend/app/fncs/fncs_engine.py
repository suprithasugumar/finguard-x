"""Financial-Narrative Contradiction Score (FNCS) Engine (Novelty 1 / Novelty 3)."""
import logging
import re
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

LM_POSITIVE = {
    "benefit", "benefits", "profitable", "profitability", "gain", "gains",
    "growth", "grow", "grown", "grew", "improve", "improved", "improves",
    "improving", "improvement", "positive", "success", "successful", "successfully",
    "strength", "strong", "stronger", "strongest", "achieve", "achieved",
    "exceed", "exceeded", "favorable", "favorably", "outperform", "outperformed",
    "opportunity", "opportunities", "efficient", "efficiency", "innovative", "innovation",
    "expanded", "expansion", "record", "rebound", "solid", "healthy",
}


def compute_lm_tone(sentence: str) -> Tuple[float, int, int, int]:
    """Compute Loughran-McDonald tone score in [-1.0, 1.0] for a single sentence."""
    tokens = [w.strip(".,;:!?\"'()[]{}") for w in sentence.lower().split()]
    pos = sum(1 for t in tokens if t in LM_POSITIVE)
    neg = sum(1 for t in tokens if t in LM_NEGATIVE)
    unc = sum(1 for t in tokens if t in LM_UNCERTAINTY or t in LM_FIN_UNCERTAINTY or t in CONDITIONAL_WORDS)

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

    def __init__(self, prototypes_path: Optional[Path] = None, embedding_cache: Optional[EmbeddingCache] = None):
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

        category_scores: Dict[str, float] = {}
        category_evidence: Dict[str, Any] = {}
        explanation_sentences: List[str] = []

        weighted_contradiction = 0.0
        total_weight = 0.0

        for cat_key, cat_data in self.categories_config.items():
            weight = float(cat_data.get("weight", 0.14))
            total_weight += weight
            cat_name = cat_data.get("name", cat_key)

            # A. Numeric Signal: tanh(z_score) in [-1.0, 1.0]
            z_val = category_z_scores.get(cat_key, 0.0)
            n_c = float(np.tanh(z_val))

            # B. Text Tone & Semantic Retrieval
            proto_embeds = self._prototype_embeddings.get(cat_key)
            t_c = 0.0
            w_c = 0.0
            top_sentence = ""
            top_sim = 0.0
            top_pos, top_neg, top_unc = 0, 0, 0

            if sentence_embeds is not None and len(sentence_embeds) > 0 and proto_embeds is not None:
                # Cosine similarities matrix: (num_sentences, num_prototypes)
                sim_matrix = np.dot(sentence_embeds, proto_embeds.T)
                max_sim_per_sentence = np.max(sim_matrix, axis=1)

                # Filter sentences by relevance threshold (cosine sim >= 0.32)
                relevant_indices = np.where(max_sim_per_sentence >= 0.32)[0]
                if len(relevant_indices) > 0:
                    # Sort by relevance descending
                    sorted_rel = relevant_indices[np.argsort(-max_sim_per_sentence[relevant_indices])][:4]
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
            # Gap d_c = text_tone - numeric_signal
            # If text is glowing/optimistic (t_c > 0) while numbers are deteriorating (n_c < 0), contradiction is severe
            d_c = t_c - n_c
            tolerance = 0.15

            if d_c > tolerance:
                # Narrative more positive than numbers: higher penalty
                x_c = w_c * min(1.0, (d_c - tolerance) * 1.25)
            elif d_c < -tolerance:
                # Narrative more negative than numbers (unusual / conservative): lower penalty
                x_c = w_c * min(1.0, (abs(d_c) - tolerance) * 0.4)
            else:
                x_c = 0.0

            x_c = float(max(0.0, min(1.0, x_c)))
            category_scores[cat_key] = x_c
            weighted_contradiction += weight * x_c

            # Record category evidence
            category_evidence[cat_key] = {
                "name": cat_name,
                "weight": weight,
                "numeric_signal_nc": round(n_c, 4),
                "numeric_z_score": round(z_val, 4),
                "text_tone_tc": round(t_c, 4),
                "presence_weight_wc": round(w_c, 4),
                "contradiction_xc": round(x_c, 4),
                "retrieved_sentence": top_sentence,
                "top_similarity": round(top_sim, 4),
                "sentiment_counts": {"pos": top_pos, "neg": top_neg, "unc": top_unc},
            }

            # D. Template-based Explanation Sentence
            if x_c >= 0.25 and top_sentence:
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
        comp_contradiction = float(weighted_contradiction / max(total_weight, 1e-6))
        comp_contradiction = float(max(0.0, min(1.0, comp_contradiction)))

        # Primary FNCS Index: 1.0 = consistent, 0.0 = severe contradiction
        fncs_score = float(max(0.0, min(1.0, 1.0 - comp_contradiction)))

        if not explanation_sentences:
            explanation_sentences.append(
                f"Financial narrative alignment index is {fncs_score:.2f}. "
                "Disclosed qualitative commentary generally corresponds with quantitative operating performance."
            )

        return {
            "cat1_revenue_recognition": category_scores.get("revenue_recognition", 0.0),
            "cat2_inventory_valuation": category_scores.get("inventory_valuation", 0.0),
            "cat3_reserve_manipulation": category_scores.get("reserve_manipulation", 0.0),
            "cat4_capitalized_expenses": category_scores.get("capitalized_expenses", 0.0),
            "cat5_related_party": category_scores.get("related_party", 0.0),
            "cat6_governance_executive": category_scores.get("governance_executive", 0.0),
            "cat7_going_concern": category_scores.get("going_concern", 0.0),
            "contradiction_score": comp_contradiction,
            "fncs_score": fncs_score,
            "fncs_evidence": category_evidence,
            "explanation_sentences": explanation_sentences[:4],
        }
