import math

import numpy as np
import pytest


def test_chunking_and_dedupe():
    from app.ingestion.extract import PageText, chunk_pages

    pages = [PageText(page=1, text="Para one about land. " * 40 + "\n\n" + "Para two about water. " * 40), PageText(page=2, text="Para one about land. " * 40)]
    chunks = chunk_pages(pages)
    assert chunks and all(c.content for c in chunks)
    assert chunks[0].page_start == 1
    texts = [c.content for c in chunks]
    assert len(texts) == len(set(texts)), "duplicate units are removed"


def test_hashing_embeddings_are_deterministic_and_normalised():
    from app.ai.embeddings import HashingEmbeddings, cosine

    p = HashingEmbeddings(dim=256)
    a, b = p.embed_one("land records digitisation"), p.embed_one("land records digitisation")
    assert a == b and abs(math.sqrt(sum(x * x for x in a)) - 1.0) < 1e-6
    sim_related = cosine(p.embed_one("cadastral map digitisation"), p.embed_one("digitisation of cadastral maps"))
    sim_unrelated = cosine(p.embed_one("cadastral map digitisation"), p.embed_one("monsoon rainfall forecast"))
    assert sim_related > sim_unrelated


def test_rrf_fusion_prefers_items_in_both_lists():
    from app.search.service import SearchHit, reciprocal_rank_fusion

    kw = [SearchHit("document", "a", "A", None, 1.0, matched_by=["keyword"]), SearchHit("document", "b", "B", None, 0.5, matched_by=["keyword"])]
    vec = [SearchHit("document", "c", "C", None, 0.9, matched_by=["semantic"]), SearchHit("document", "b", "B", None, 0.8, matched_by=["semantic"])]
    fused = reciprocal_rank_fusion(kw, vec)
    assert fused[0].entity_id == "b" and set(fused[0].matched_by) == {"keyword", "semantic"}


def test_extractive_answerer_cites_only_passages():
    from app.ai.llm import ExtractiveAnswerer, Passage

    p = [Passage(1, "Drone surveys reduced boundary disputes by 22 percent in pilot districts.", "Doc", "p.1"), Passage(2, "The monsoon arrived late this year in several districts.", "Doc2", "p.3")]
    g = ExtractiveAnswerer().answer("How much did drone surveys reduce boundary disputes?", p)
    assert g.used_markers == [1] and "[1]" in g.answer and "[2]" not in g.answer
    g2 = ExtractiveAnswerer().answer("What is the price of gold?", p)
    assert g2.used_markers == [] and "does not contain" in g2.answer


def test_mime_sniffing_and_validation():
    from app.core.exceptions import ValidationFailed
    from app.storage.validation import sniff_mime, validate_upload

    assert sniff_mime(b"%PDF-1.4 rest", "x.pdf", None) == "application/pdf"
    assert sniff_mime(b"plain text content", "x.txt", "text/plain") == "text/plain"
    assert sniff_mime(b"a,b\n1,2\n", "x.csv", "text/csv") == "text/csv"
    with pytest.raises(ValidationFailed):
        validate_upload(b"MZ\x90\x00", "evil.exe", "application/octet-stream")


def test_password_policy_and_hashing():
    from app.core.exceptions import ValidationFailed
    from app.core.security import hash_password, validate_password_strength, verify_password

    assert validate_password_strength("short1") and validate_password_strength("nodigitsatall")
    assert validate_password_strength("Correct@2026x") is None
    h = hash_password("Correct@2026x")
    assert verify_password("Correct@2026x", h) and not verify_password("Wrong@2026x", h)
    long_pw = "x" * 100 + "1"
    assert verify_password(long_pw, hash_password(long_pw))


def test_spectral_indices_and_lulc():
    from app.gis.remote_sensing import SceneBands, change_detection, classify_lulc, ndbi, ndvi, ndwi

    red = np.array([[0.1, 0.4]]); nir = np.array([[0.7, 0.4]]); green = np.array([[0.3, 0.5]]); swir = np.array([[0.2, 0.6]])
    b = SceneBands(red=red, nir=nir, green=green, swir=swir, resolution_m=10)
    assert np.allclose(ndvi(b), [[0.75, 0.0]]) and np.allclose(ndwi(b), [[-0.4, 1 / 9]]) and np.allclose(ndbi(b), [[-5 / 9, 0.2]])
    cls, stats = classify_lulc(b)
    assert stats["classes"][cls[0, 0]] == "dense_vegetation" and stats["classes"][cls[0, 1]] == "built_up"
    ch = change_detection(b, SceneBands(red=nir, nir=red, green=green, swir=swir, resolution_m=10))
    assert ch["vegetation_loss_km2"] > 0


def test_analytics_procedures():
    from app.analytics.service import anomaly, descriptive, forecast, timeseries, trend

    rows = [{"year": 2000 + i, "value": 10 + 2 * i, "label": "A"} for i in range(8)]
    assert abs(trend(rows)["slope_per_year"] - 2) < 1e-9
    assert descriptive(rows)["n"] == 8 and descriptive(rows)["median"] == 17
    fc = forecast(rows, horizon=2)["forecast"]
    assert fc[0]["year"] == 2008 and abs(fc[0]["value"] - 26) < 0.5
    ts = timeseries(rows)
    assert ts["yoy_change_pct"][1] == 20.0 and ts["cagr_pct"] > 0
    an = anomaly(rows + [{"year": 2010, "value": 500, "label": "A"}])
    assert an["anomalies"][0]["value"] == 500


def test_token_helpers():
    from app.core.security import create_access_token, decode_token

    tok = create_access_token(subject="123e4567-e89b-12d3-a456-426614174000", extra={"pw": 1})
    payload = decode_token(tok)
    assert payload["sub"] == "123e4567-e89b-12d3-a456-426614174000" and payload["type"] == "access" and payload["jti"]
