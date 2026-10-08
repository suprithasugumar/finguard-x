"""Unit tests for FilingTextExtractor and NarrativeDriftAnalyzer (Sprint A2 & A3)."""

from backend.app.ingest.text_extractor import FilingTextExtractor
from backend.app.nlp.narrative_drift import (
    NarrativeDriftAnalyzer,
    clean_sentences,
)


def test_text_extractor_html_cleaning():
    """Verify HTML cleaning preserves structure and removes scripts/styles."""
    raw_html = """
    <html>
        <head><style>body { color: red; }</style></head>
        <body>
            <script>console.log("ignore me");</script>
            <h1>Item 1. Business</h1>
            <p>Our company designs aerospace components and electronic subsystems.</p>
        </body>
    </html>
    """
    clean = FilingTextExtractor.html_to_clean_text(raw_html)
    assert "console.log" not in clean
    assert "color: red" not in clean
    assert "Our company designs aerospace components" in clean


def test_text_extractor_section_extraction():
    """Verify robust extraction of Item 7 MD&A and Item 1A Risk Factors."""
    sample_filing = """
    ITEM 1. BUSINESS
    Business details here.

    ITEM 1A. RISK FACTORS
    Our operations are subject to substantial supply chain volatility and geopolitical disruption across global distribution hubs.
    We may experience delayed component deliveries from international vendors, leading to assembly bottlenecks and customer order cancellations.
    Such events could adversely impact our financial condition, operating results, liquidity reserves, and overall commercial trajectory.
    In addition, changes in foreign exchange rates and interest rate environments could impair operating margins across regional subsidiaries.
    Cybersecurity threats and potential data breaches could result in operational disruption and substantial reputational damage.
    Regulatory compliance changes in international jurisdictions could increase operating expenditures and limit market expansion.
    Competition from legacy aerospace manufacturers and low-cost alternative providers could erode market share and gross margins.
    Fluctuations in aviation fuel prices and commercial air travel passenger miles may suppress fleet renewal and spare parts procurement.
    Failure to attract and retain highly skilled aerospace engineering talent could delay program milestones and product development cycles.
    Unforeseen labor disputes, work stoppages, or union contract renegotiations could temporarily halt production at critical manufacturing facilities.

    ITEM 1B. UNRESOLVED STAFF COMMENTS
    None.

    ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION AND RESULTS OF OPERATIONS
    Revenues increased 12% driven by higher commercial aviation flight hours and aftermarket demand across domestic and European routes.
    Operating margins expanded 140 basis points due to operational efficiencies, volume leverage, and disciplined headcount management.
    Free cash flow generation remained strong throughout the fiscal period, allowing continued reinvestment into next-generation avionics platforms.
    We believe our available liquidity, cash equivalents, and revolving credit facility are sufficient to meet foreseeable capital expenditures and operational requirements over the next twelve months.
    Cost of sales increased modestly due to raw material inflation, though productivity initiatives partially offset these cost pressures.
    Research and development expenditures rose in accordance with our planned multi-year technology roadmap.
    Working capital management improved through optimized inventory turnover and enhanced collections across trade receivables.
    Net income attributable to common shareholders reflected strong underlying execution across all operating reporting segments.

    ITEM 7A. QUANTITATIVE AND QUALITATIVE DISCLOSURES ABOUT MARKET RISK
    Interest rate risk is managed via floating-to-fixed swaps.
    """
    extractor = FilingTextExtractor()
    sections = extractor.extract_sections(sample_filing)

    # MD&A verification
    assert "mda" in sections
    assert sections["mda"]["status"] == "success"
    assert "Revenues increased 12%" in sections["mda"]["text"]
    assert "ITEM 7A" not in sections["mda"]["text"]

    # Risk factors verification
    assert "risk_factors" in sections
    assert sections["risk_factors"]["status"] == "success"
    assert "supply chain volatility" in sections["risk_factors"]["text"]
    assert "ITEM 1B" not in sections["risk_factors"]["text"]

    # Missing section verification
    assert sections["related_party"]["status"] == "not_found"
    assert sections["related_party"]["text"] is None


def test_clean_sentences_and_filters():
    """Verify sentence splitting ignores trivial lines and enforces minimum word counts."""
    text = "Short. 12345. A valid financial sentence describing full annual revenues and cash flows. Another legitimate sentence detailing corporate liabilities and capital leases."
    sentences = clean_sentences(text)
    assert len(sentences) == 2
    assert "A valid financial sentence" in sentences[0]
    assert "Another legitimate sentence" in sentences[1]


def test_narrative_drift_identical_text():
    """Verify identical text between year t and t-1 yields near-zero drift score."""
    mda_text = (
        "Revenues increased 12% driven by higher commercial aviation flight hours and aftermarket demand. "
        "Operating margins expanded 140 basis points due to operational efficiencies and volume leverage. "
        "Free cash flow generation remained strong throughout the fiscal period. "
        "We believe our available liquidity is sufficient to meet foreseeable capital expenditures."
    )
    analyzer = NarrativeDriftAnalyzer()
    res = analyzer.analyze_drift(curr_text=mda_text, prior_text=mda_text)

    assert res["narrative_drift_score"] is not None
    assert res["narrative_drift_score"] < 0.05
    assert res["doc_embedding_cosine_drift"] < 0.02
    assert res["vocab_jaccard_distance"] == 0.0


def test_narrative_drift_divergent_text_and_snippets():
    """Verify substantial narrative changes produce detectable drift and evidence snippets."""
    prior_text = (
        "Revenues grew rapidly across our retail segments with strong domestic consumer spending. "
        "Store expansion continued according to plan with fifty new storefronts opened. "
        "Supply chains operated without meaningful interruption across all major regional warehouses."
    )
    curr_text = (
        "Revenues experienced severe contraction due to sudden macro weakness and declining store traffic. "
        "We initiated an aggressive restructuring plan to close sixty underperforming locations. "
        "Severe component shortages and freight delays significantly increased cost of goods sold."
    )
    analyzer = NarrativeDriftAnalyzer()
    res = analyzer.analyze_drift(curr_text=curr_text, prior_text=prior_text)

    assert res["narrative_drift_score"] is not None
    assert 0.0 <= res["narrative_drift_score"] <= 1.0
    assert res["vocab_jaccard_distance"] > 0.4

    # Evidence snippets
    snippets = res["drift_evidence_snippets"]
    assert len(snippets) > 0
    assert "current_sentence" in snippets[0]
    assert "nearest_prior_sentence" in snippets[0]
    assert "cosine_similarity" in snippets[0]
    assert snippets[0]["cosine_similarity"] <= 1.0


def test_linguistic_features_calculation():
    """Verify Loughran-McDonald uncertainty, negative sentiment, and readability metrics."""
    text = (
        "We believe there is substantial uncertainty regarding future litigation outcomes. "
        "The adverse judgment may impair our ability to refinance existing debt maturities. "
        "If renegotiation fails, our default risk could materially increase depending on market conditions."
    )
    analyzer = NarrativeDriftAnalyzer()
    res = analyzer.analyze_drift(curr_text=text, prior_text=None)

    assert res["uncertainty_rate"] > 0.0
    assert res["negative_sentiment_rate"] > 0.0
    assert res["financial_uncertainty_rate"] > 0.0
    assert res["conditional_language_rate"] > 0.0
    assert res["readability_fog_index"] > 10.0
