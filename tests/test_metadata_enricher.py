from paper_analyzer.data.schema import FetchedPaper
from paper_analyzer.ingestion import metadata_enricher
from paper_analyzer.ingestion.metadata_enricher import enrich_paper_metadata


def test_enrich_paper_metadata_fills_missing_fields(monkeypatch):
    paper = FetchedPaper(title="A reliable physics-informed neural network paper", abstract="")

    monkeypatch.setattr(
        metadata_enricher,
        "_lookup_openalex",
        lambda requests, paper, timeout: {
            "title": "A reliable physics-informed neural network paper",
            "doi": "https://doi.org/10.1/example",
            "authors": "Alice; Bob",
            "venue": "Journal X",
            "abstract": "A longer public abstract.",
        },
    )
    monkeypatch.setattr(metadata_enricher, "_lookup_crossref", lambda requests, paper, timeout: None)
    monkeypatch.setattr(metadata_enricher, "_lookup_semantic_scholar", lambda requests, paper, timeout: None)

    enriched = enrich_paper_metadata(paper)

    assert enriched.doi == "10.1/example"
    assert enriched.authors == "Alice; Bob"
    assert enriched.venue == "Journal X"
    assert enriched.abstract == "A longer public abstract."
    assert enriched.fetch_method == "email+openalex"


def test_enrich_paper_metadata_rejects_low_similarity_title(monkeypatch):
    paper = FetchedPaper(title="Original physics-informed paper title", abstract="")

    monkeypatch.setattr(
        metadata_enricher,
        "_lookup_openalex",
        lambda requests, paper, timeout: {
            "title": "Completely different biomedical article",
            "doi": "10.1/wrong",
            "authors": "Wrong Author",
            "venue": "Wrong Journal",
            "abstract": "Wrong abstract.",
        },
    )
    monkeypatch.setattr(metadata_enricher, "_lookup_crossref", lambda requests, paper, timeout: None)
    monkeypatch.setattr(metadata_enricher, "_lookup_semantic_scholar", lambda requests, paper, timeout: None)

    enriched = enrich_paper_metadata(paper)

    assert enriched.doi is None
    assert enriched.authors is None
    assert enriched.venue is None
    assert enriched.abstract == ""
    assert enriched.fetch_method == "email"


def test_enrich_paper_metadata_does_not_overwrite_existing_fields(monkeypatch):
    paper = FetchedPaper(
        title="Existing metadata paper",
        abstract="Short abstract",
        doi="10.1/existing",
        authors="Existing Author",
        venue="Existing Venue",
    )

    monkeypatch.setattr(
        metadata_enricher,
        "_lookup_openalex",
        lambda requests, paper, timeout: {
            "title": "Existing metadata paper",
            "doi": "10.1/existing",
            "authors": "New Author",
            "venue": "New Venue",
            "abstract": "A much longer abstract from a public metadata source.",
        },
    )
    monkeypatch.setattr(metadata_enricher, "_lookup_crossref", lambda requests, paper, timeout: None)
    monkeypatch.setattr(metadata_enricher, "_lookup_semantic_scholar", lambda requests, paper, timeout: None)

    enriched = enrich_paper_metadata(paper)

    assert enriched.doi == "10.1/existing"
    assert enriched.authors == "Existing Author"
    assert enriched.venue == "Existing Venue"
    assert enriched.abstract == "A much longer abstract from a public metadata source."
