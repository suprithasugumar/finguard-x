"""Knowledge graph construction, related-party entity extraction, and topological feature engine (Novelty 2)."""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

logger = logging.getLogger("finguard.graph.knowledge_graph")

# Corporate Entity Patterns
ORG_SUFFIXES = {
    "inc",
    "inc.",
    "corp",
    "corp.",
    "corporation",
    "ltd",
    "ltd.",
    "limited",
    "co",
    "co.",
    "company",
    "holdings",
    "group",
    "enterprises",
    "associates",
    "llc",
    "llp",
    "lp",
    "partnership",
    "trust",
    "fund",
    "capital",
}
SHELL_PATTERNS = {
    "llc",
    "l.l.c.",
    "lp",
    "l.p.",
    "llp",
    "l.l.p.",
    "trust",
    "capital",
    "partners",
    "fund",
    "ventures",
    "management",
    "holdings",
    "advisors",
    "properties",
    "investments",
    "special purpose",
    "offshore",
    "cayman",
    "delaware",
    "nominee",
}
HONORIFICS = {
    "mr",
    "mr.",
    "ms",
    "ms.",
    "mrs",
    "mrs.",
    "dr",
    "dr.",
    "chairman",
    "ceo",
    "director",
    "officer",
    "president",
}

# Attempt to load spacy safely with fallback
_SPACY_NLP = None
try:
    import spacy

    try:
        _SPACY_NLP = spacy.load("en_core_web_sm", disable=["parser"])
    except Exception:
        try:
            _SPACY_NLP = spacy.blank("en")
        except Exception:
            _SPACY_NLP = None
except Exception:
    _SPACY_NLP = None


def normalize_entity_name(raw_name: str) -> str:
    """Normalize executive and corporate entity names for clean graph resolution."""
    name = raw_name.strip()
    name = re.sub(r"[,\.\(\)\"\':]", " ", name)
    words = [w for w in name.split() if w.lower() not in HONORIFICS and len(w) > 1]
    cleaned = " ".join(words)
    return cleaned.strip().title()


class RelatedPartyGraphExtractor:
    """Extracts entities, relationships, and constructs NetworkX knowledge graphs from SEC 10-K disclosures."""

    def __init__(self):
        # Relationship extraction regexes
        self.person_officer_pattern = re.compile(
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b[^\.\n]{0,50}?(?:serves as|is (?:our|a|the)|Chief Executive|Executive Officer|Director|Chairman|Chief Technology Officer|Chief Financial Officer|founder|owner|partner)",
            re.IGNORECASE,
        )
        self.honorific_person_pattern = re.compile(
            r"(?:Mr\.|Ms\.|Mrs\.|Dr\.)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})",
            re.IGNORECASE,
        )
        self.comma_officer_pattern = re.compile(
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}),\s*(?:our\s+)?(?:Chief [A-Za-z]+ Officer|President|CEO|CFO|CTO|Executive Vice President|Director|Chairman|trustee)",
            re.IGNORECASE,
        )
        self.entity_pattern = re.compile(
            r"\b([A-Z][A-Za-z0-9\&\s]{2,45}?\s+(?:LLC|L\.L\.C\.|L\.P\.|LP|LLP|L\.L\.P\.|Inc\.|Inc|Corporation|Corp\.|Corp|Holdings|Partners|Trust|Fund|Capital))\b"
        )
        self.transaction_verbs = re.compile(
            r"\b(leased|purchased|sold|borrowed|loaned|paid|provided|invested|agreement with|consulting services|acquired|license agreement|royalty)\b",
            re.IGNORECASE,
        )

    def extract_graph(
        self,
        company_name: str,
        related_party_text: Optional[str],
        prior_graph: Optional[nx.Graph] = None,
    ) -> Tuple[nx.Graph, Dict[str, Any]]:
        """Construct knowledge graph and extract topological features."""
        G = nx.Graph()
        focal_node = normalize_entity_name(company_name or "Registrant")
        G.add_node(focal_node, type="FOCAL_COMPANY", label=focal_node)

        if not related_party_text or len(related_party_text.strip()) < 100:
            return G, self._empty_features(G)

        # 1. Entity extraction: Rule-based + spaCy NER (if available)
        persons = set()
        entities = set()

        # Rule-based regex matches
        for pat in [
            self.person_officer_pattern,
            self.honorific_person_pattern,
            self.comma_officer_pattern,
        ]:
            for match in pat.finditer(related_party_text):
                p_name = normalize_entity_name(match.group(1))
                if (
                    len(p_name.split()) >= 2
                    and len(p_name) > 4
                    and p_name.lower() != focal_node.lower()
                ):
                    persons.add(p_name)

        for match in self.entity_pattern.finditer(related_party_text):
            e_name = normalize_entity_name(match.group(1))
            if len(e_name) > 3 and e_name.lower() != focal_node.lower():
                entities.add(e_name)

        # spaCy NER extraction if model is available
        if _SPACY_NLP is not None:
            try:
                doc = _SPACY_NLP(related_party_text[:100000])
                for ent in doc.ents:
                    clean_ent = normalize_entity_name(ent.text)
                    if len(clean_ent) > 3 and clean_ent.lower() != focal_node.lower():
                        if ent.label_ == "PERSON" and len(clean_ent.split()) >= 2:
                            persons.add(clean_ent)
                        elif ent.label_ == "ORG" and any(
                            suf in ent.text.lower() for suf in ORG_SUFFIXES
                        ):
                            entities.add(clean_ent)
            except Exception as e:
                logger.debug(f"spaCy NER pass skipped: {e}")

        # Filter out common false positives
        STOP_ENTITIES = {
            "Company",
            "The Company",
            "Board Of Directors",
            "Audit Committee",
            "Stock Option",
            "Common Stock",
            "United States",
        }
        persons = {p for p in persons if p not in STOP_ENTITIES}
        entities = {e for e in entities if e not in STOP_ENTITIES and e not in persons}

        # Classify and add nodes
        for p in persons:
            G.add_node(p, type="PERSON", label=p)
            G.add_edge(focal_node, p, relation="OFFICER_OR_DIRECTOR", weight=1.0)

        for e in entities:
            # Classify shell vs standard corp
            is_shell = any(kw in e.lower() for kw in SHELL_PATTERNS)
            node_type = "SHELL_OR_HOLDING" if is_shell else "ORGANIZATION"
            G.add_node(e, type=node_type, label=e)
            G.add_edge(focal_node, e, relation="RELATED_ENTITY", weight=1.0)

        # Extract cross-edges between persons and related entities
        sentences = re.split(r"(?<=[.!?])\s+", related_party_text)
        evidence_edges = []
        for s in sentences:
            found_p = [p for p in persons if p.lower() in s.lower()]
            found_e = [e for e in entities if e.lower() in s.lower()]
            if found_p and found_e:
                for p in found_p:
                    for e in found_e:
                        G.add_edge(p, e, relation="AFFILIATION_OR_OWNERSHIP", weight=2.0)
                        evidence_edges.append(
                            {
                                "source": p,
                                "target": e,
                                "relation": "AFFILIATION_OR_OWNERSHIP",
                                "evidence_sentence": s.strip(),
                            }
                        )

        features = self._compute_graph_features(G, prior_graph, evidence_edges)
        return G, features

    def _compute_graph_features(
        self,
        G: nx.Graph,
        prior_graph: Optional[nx.Graph],
        evidence_edges: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Compute topological indices and YoY evolution."""
        num_nodes = G.number_of_nodes()
        num_edges = G.number_of_edges()

        # If only focal node exists, graph has zero meaningful connections
        if num_nodes <= 1:
            return self._empty_features(G)

        density = float(nx.density(G))
        degrees = [d for _, d in G.degree()]
        avg_degree = float(sum(degrees) / num_nodes) if num_nodes > 0 else 0.0

        # Entity type breakdowns
        node_types = nx.get_node_attributes(G, "type")
        num_officers = sum(1 for t in node_types.values() if t == "PERSON")
        num_entities = sum(1 for t in node_types.values() if t == "ORGANIZATION")
        num_shells = sum(1 for t in node_types.values() if t == "SHELL_OR_HOLDING")

        # Network structure
        cliques = list(nx.find_cliques(G))
        max_clique = max((len(c) for c in cliques), default=0)
        clustering = float(nx.average_clustering(G))

        betweenness = nx.betweenness_centrality(G)
        max_betweenness = float(max(betweenness.values(), default=0.0))

        # YoY Evolution
        if prior_graph and prior_graph.number_of_nodes() > 1:
            curr_nodes = set(G.nodes())
            prior_nodes = set(prior_graph.nodes())
            node_union = curr_nodes | prior_nodes
            node_churn = (
                1.0 - (len(curr_nodes & prior_nodes) / len(node_union)) if node_union else 0.0
            )

            curr_edges = {tuple(sorted(e)) for e in G.edges()}
            prior_edges = {tuple(sorted(e)) for e in prior_graph.edges()}
            edge_union = curr_edges | prior_edges
            edge_churn = (
                1.0 - (len(curr_edges & prior_edges) / len(edge_union)) if edge_union else 0.0
            )
        else:
            node_churn = 0.0
            edge_churn = 0.0

        # Novelty 2: Composite Graph Anomaly Score [0, 1]
        # High opacity: many shell/holding entities, high intermediary betweenness, high churn
        shell_ratio = num_shells / max(num_nodes - 1, 1)
        anomaly_score = float(
            0.35 * shell_ratio
            + 0.25 * min(max_betweenness * 2.0, 1.0)
            + 0.20 * node_churn
            + 0.20 * min(density * 2.0, 1.0)
        )
        anomaly_score = float(max(0.0, min(1.0, anomaly_score)))

        # Serializable Payload for UI
        payload = {
            "nodes": [
                {"id": n, "label": n, "type": G.nodes[n].get("type", "ENTITY")} for n in G.nodes()
            ],
            "edges": [
                {
                    "source": u,
                    "target": v,
                    "relation": G.edges[u, v].get("relation", "RELATED"),
                    "weight": G.edges[u, v].get("weight", 1.0),
                }
                for u, v in G.edges()
            ],
        }

        return {
            "graph_available": True,
            "graph_size": num_nodes,
            "num_nodes": num_nodes,
            "num_edges": num_edges,
            "density": density,
            "avg_degree": avg_degree,
            "num_officers": num_officers,
            "num_entities": num_entities,
            "num_undisclosed_or_shell": num_shells,
            "max_clique_size": max_clique,
            "clustering_coefficient": clustering,
            "betweenness_centrality_max": max_betweenness,
            "yoy_node_churn": node_churn,
            "yoy_edge_churn": edge_churn,
            "graph_anomaly_score": anomaly_score,
            "graph_payload": payload,
            "evidence_edges": evidence_edges[:5],
        }

    def _empty_features(self, G: nx.Graph) -> Dict[str, Any]:
        """Return zeroed features when graph is unavailable."""
        payload = {
            "nodes": [{"id": n, "label": n, "type": "FOCAL_COMPANY"} for n in G.nodes()],
            "edges": [],
        }
        return {
            "graph_available": False,
            "graph_size": 0,
            "num_nodes": 0,
            "num_edges": 0,
            "density": 0.0,
            "avg_degree": 0.0,
            "num_officers": 0,
            "num_entities": 0,
            "num_undisclosed_or_shell": 0,
            "max_clique_size": 0,
            "clustering_coefficient": 0.0,
            "betweenness_centrality_max": 0.0,
            "yoy_node_churn": 0.0,
            "yoy_edge_churn": 0.0,
            "graph_anomaly_score": 0.0,
            "graph_payload": payload,
            "evidence_edges": [],
        }
