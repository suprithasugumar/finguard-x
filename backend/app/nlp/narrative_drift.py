"""Narrative drift, sentence alignment, and linguistic feature extraction engine (Novelty 1)."""

import hashlib
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger("finguard.nlp.narrative_drift")

# Loughran-McDonald Lexicons (Curated Core Sets for SEC 10-K Filings)
LM_UNCERTAINTY = {
    "approximate",
    "approximately",
    "anticipate",
    "anticipated",
    "anticipating",
    "anticipates",
    "assume",
    "assumed",
    "assumes",
    "assuming",
    "assumption",
    "assumptions",
    "believe",
    "believed",
    "believes",
    "believing",
    "contingency",
    "contingencies",
    "contingent",
    "depend",
    "dependent",
    "depending",
    "depends",
    "estimate",
    "estimated",
    "estimates",
    "estimating",
    "estimation",
    "fluctuate",
    "fluctuated",
    "fluctuates",
    "fluctuating",
    "fluctuation",
    "fluctuations",
    "indefinite",
    "indefinitely",
    "likelihood",
    "probable",
    "probability",
    "renegotiate",
    "renegotiated",
    "risk",
    "risks",
    "uncertain",
    "uncertainly",
    "uncertainties",
    "uncertainty",
    "variability",
    "variable",
    "vary",
    "varying",
}

LM_NEGATIVE = {
    "abandon",
    "abandoned",
    "adverse",
    "adversely",
    "breach",
    "breached",
    "cancel",
    "cancelled",
    "cancelling",
    "closure",
    "closures",
    "decline",
    "declined",
    "declines",
    "declining",
    "default",
    "defaulted",
    "defaults",
    "deficit",
    "deficits",
    "delay",
    "delayed",
    "delays",
    "deteriorate",
    "deteriorated",
    "deteriorates",
    "deteriorating",
    "deterioration",
    "difficult",
    "difficulties",
    "difficulty",
    "discontinue",
    "discontinued",
    "disruption",
    "disruptions",
    "fail",
    "failed",
    "failing",
    "fails",
    "failure",
    "failures",
    "impair",
    "impaired",
    "impairment",
    "impairments",
    "inability",
    "investigation",
    "investigations",
    "lawsuit",
    "lawsuits",
    "liquidate",
    "liquidated",
    "liquidation",
    "litigation",
    "litigations",
    "loss",
    "losses",
    "penalty",
    "penalties",
    "restructure",
    "restructured",
    "restructuring",
    "restructurings",
    "terminate",
    "terminated",
    "terminates",
    "terminating",
    "termination",
    "terminations",
}

LM_FIN_UNCERTAINTY = {
    "covenant",
    "covenants",
    "credit",
    "default",
    "downgrade",
    "downgraded",
    "exposure",
    "exposures",
    "illiquid",
    "illiquidity",
    "insolvency",
    "insolvent",
    "liquidity",
    "margin",
    "maturities",
    "maturity",
    "refinance",
    "refinancing",
    "repayment",
    "solvency",
    "subordinated",
    "volatility",
    "volatile",
}

CONDITIONAL_WORDS = {
    "if",
    "could",
    "may",
    "might",
    "subject",
    "depending",
    "conditioned",
    "provided",
    "assuming",
    "contingent",
    "unless",
    "whenever",
}


def clean_sentences(text: str, max_sentences: int = 150) -> List[str]:
    """Split text into clean, non-trivial sentences (min 5 words, capped at max_sentences)."""
    if not text:
        return []
    # Clean text
    clean = re.sub(r"\s+", " ", text).strip()
    raw_sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", clean)
    valid = []
    for s in raw_sentences:
        s_clean = s.strip()
        words = s_clean.split()
        if len(words) >= 5 and any(c.isalpha() for c in s_clean):
            valid.append(s_clean)
            if len(valid) >= max_sentences:
                break
    return valid


class EmbeddingCache:
    """MiniLM sentence embedding cache with in-memory hashing."""

    def __init__(self, cache_dir: Optional[Path] = None):
        from backend.app.core.config import get_settings

        settings = get_settings()
        self.cache_dir = cache_dir or (settings.CACHE_DIR / "embeddings")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._model = None
        self._mem_cache: Dict[str, np.ndarray] = {}

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
            except Exception as e:
                logger.warning(f"Could not load SentenceTransformer: {e}")
                self._model = False
        return self._model

    def embed_sentences(self, sentences: List[str]) -> np.ndarray:
        """Embed list of sentences using cached all-MiniLM-L6-v2."""
        if not sentences:
            return np.empty((0, 384), dtype=np.float32)

        model = self._get_model()
        if not model:
            # Fallback dense character n-gram hashing embedding if model unavailable
            return self._fallback_hash_embed(sentences)

        embeddings = []
        to_encode = []
        to_encode_indices = []

        for i, s in enumerate(sentences):
            h = hashlib.sha256(s.encode("utf-8")).hexdigest()
            if h in self._mem_cache:
                embeddings.append((i, self._mem_cache[h]))
                continue
            to_encode.append(s)
            to_encode_indices.append(i)

        if to_encode:
            encoded = model.encode(
                to_encode, batch_size=128, show_progress_bar=False, normalize_embeddings=True
            )
            for s, idx, vec in zip(to_encode, to_encode_indices, encoded):
                h = hashlib.sha256(s.encode("utf-8")).hexdigest()
                self._mem_cache[h] = vec
                embeddings.append((idx, vec))

        embeddings.sort(key=lambda x: x[0])
        return np.array([x[1] for x in embeddings], dtype=np.float32)

    def _fallback_hash_embed(self, sentences: List[str]) -> np.ndarray:
        """Deterministic dense projection fallback (384-dim) for testing environments."""
        vecs = []
        for s in sentences:
            words = s.lower().split()
            v = np.zeros(384, dtype=np.float32)
            for w in words:
                idx = int(hashlib.md5(w.encode("utf-8")).hexdigest(), 16) % 384
                v[idx] += 1.0
            norm = np.linalg.norm(v)
            if norm > 0:
                v = v / norm
            vecs.append(v)
        return np.array(vecs, dtype=np.float32)


class NarrativeDriftAnalyzer:
    """Computes bidirectional best-match sentence drift, evidence snippets, and supporting NLP features."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.embed_cache = EmbeddingCache(cache_dir)

    def analyze_drift(
        self,
        curr_text: str,
        prior_text: Optional[str] = None,
        source_location: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compute full narrative drift and supporting linguistic metrics."""
        curr_sentences = clean_sentences(curr_text)
        words = re.findall(r"\b[A-Za-z0-9\$\%]+\b", curr_text.lower())

        # 1. Supporting Linguistic Features
        ling_features = self._compute_linguistic_features(curr_text, curr_sentences, words)

        # If no prior text, drift is undefined
        if not prior_text or not prior_text.strip():
            return {
                "narrative_drift_score": None,
                "doc_embedding_cosine_drift": None,
                "vocab_jaccard_distance": None,
                "drift_evidence_snippets": [],
                **ling_features,
            }

        prior_sentences = clean_sentences(prior_text)
        prior_words = re.findall(r"\b[A-Za-z0-9\$\%]+\b", prior_text.lower())

        # Vocabulary Jaccard Distance
        curr_vocab = set(words)
        prior_vocab = set(prior_words)
        union_v = curr_vocab | prior_vocab
        if union_v:
            vocab_jaccard = 1.0 - (len(curr_vocab & prior_vocab) / len(union_v))
        else:
            vocab_jaccard = None

        # 2. Embedding Drift Computation
        curr_embeds = self.embed_cache.embed_sentences(curr_sentences)
        prior_embeds = self.embed_cache.embed_sentences(prior_sentences)

        if len(curr_embeds) == 0 or len(prior_embeds) == 0:
            return {
                "narrative_drift_score": None,
                "doc_embedding_cosine_drift": None,
                "vocab_jaccard_distance": vocab_jaccard,
                "drift_evidence_snippets": [],
                **ling_features,
            }

        # Pairwise cosine similarity matrix: (N_curr, M_prior)
        # Embeddings are normalized, so dot product = cosine similarity
        sim_matrix = np.dot(curr_embeds, prior_embeds.T)

        # Forward best-match: for each current sentence, max sim in prior
        forward_best = np.max(sim_matrix, axis=1)  # shape (N_curr,)
        forward_best_idx = np.argmax(sim_matrix, axis=1)

        # Backward best-match: for each prior sentence, max sim in current
        backward_best = np.max(sim_matrix, axis=0)  # shape (M_prior,)

        mean_forward = float(np.mean(forward_best))
        mean_backward = float(np.mean(backward_best))
        symmetrized_alignment = (mean_forward + mean_backward) / 2.0
        narrative_drift_score = float(np.clip(1.0 - symmetrized_alignment, 0.0, 1.0))

        # Document-Level Mean Embedding Drift
        mean_curr = np.mean(curr_embeds, axis=0)
        mean_prior = np.mean(prior_embeds, axis=0)
        norm_c = np.linalg.norm(mean_curr)
        norm_p = np.linalg.norm(mean_prior)
        if norm_c > 0 and norm_p > 0:
            doc_cos = float(np.dot(mean_curr, mean_prior) / (norm_c * norm_p))
            doc_drift = float(np.clip(1.0 - doc_cos, 0.0, 1.0))
        else:
            doc_drift = None

        # 3. Evidence Snippets: Top-3 lowest similarity current sentences
        lowest_indices = np.argsort(forward_best)[:3]
        evidence_snippets = []
        for idx in lowest_indices:
            evidence_snippets.append(
                {
                    "current_sentence": curr_sentences[idx],
                    "nearest_prior_sentence": prior_sentences[forward_best_idx[idx]],
                    "cosine_similarity": float(forward_best[idx]),
                    "source_location": source_location or "Item 7 MD&A",
                }
            )

        return {
            "narrative_drift_score": narrative_drift_score,
            "doc_embedding_cosine_drift": doc_drift,
            "vocab_jaccard_distance": vocab_jaccard,
            "drift_evidence_snippets": evidence_snippets,
            **ling_features,
        }

    def _compute_linguistic_features(
        self, text: str, sentences: List[str], words: List[str]
    ) -> Dict[str, Any]:
        """Compute supporting linguistic features: readability, sentiment, uncertainty, etc."""
        total_words = len(words)
        total_sentences = max(len(sentences), 1)

        if total_words == 0:
            return {
                "uncertainty_rate": None,
                "negative_sentiment_rate": None,
                "financial_uncertainty_rate": None,
                "avg_sentence_length": None,
                "readability_fog_index": None,
                "conditional_language_rate": None,
                "passive_voice_rate": None,
                "numeric_density": None,
            }

        # Rates
        unc_count = sum(1 for w in words if w in LM_UNCERTAINTY)
        neg_count = sum(1 for w in words if w in LM_NEGATIVE)
        fin_unc_count = sum(1 for w in words if w in LM_FIN_UNCERTAINTY)
        cond_count = sum(1 for w in words if w in CONDITIONAL_WORDS)
        num_count = sum(1 for w in words if any(c.isdigit() for c in w))

        # Passive voice heuristic
        passive_matches = len(
            re.findall(r"\b(?:is|are|was|were|be|been|being)\s+\w+ed\b", text, re.IGNORECASE)
        )

        # Readability (Gunning Fog Index)
        try:
            import textstat

            fog = float(textstat.gunning_fog(text))
        except Exception:
            # Fallback Fog index formula
            complex_words = sum(1 for w in words if len(w) >= 8)
            asl = total_words / total_sentences
            pcw = (complex_words / total_words) * 100.0
            fog = 0.4 * (asl + pcw)

        return {
            "uncertainty_rate": unc_count / total_words,
            "negative_sentiment_rate": neg_count / total_words,
            "financial_uncertainty_rate": fin_unc_count / total_words,
            "avg_sentence_length": total_words / total_sentences,
            "readability_fog_index": float(fog),
            "conditional_language_rate": cond_count / total_words,
            "passive_voice_rate": passive_matches / total_sentences,
            "numeric_density": num_count / total_words,
        }
