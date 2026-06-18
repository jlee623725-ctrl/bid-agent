"""Tests for tool functions — runs against the real SQLite database."""

import pytest

from agent.tools_bidding import get_notice_detail, query_trends, search_notices
from agent.tools_company import find_competitors, get_company_profile, search_companies
from agent.tools_legal import get_article, search_laws


class TestBiddingTools:
    def test_search_notices_returns_list_with_fields(self):
        results = search_notices("公告", limit=5)
        assert isinstance(results, list)
        assert len(results) > 0
        assert len(results) <= 5
        for r in results:
            assert "notice_id" in r
            assert "notice_content" in r
            assert "successful_bidder" in r

    def test_search_notices_no_results(self):
        results = search_notices("XYZZY_PLACEHOLDER_NOMATCH", limit=5)
        assert results == []

    def test_query_trends_returns_structure(self):
        result = query_trends("建筑", months=12)
        assert isinstance(result, dict)
        assert "total_amount" in result
        assert "count" in result
        assert "top_winners" in result
        assert isinstance(result["total_amount"], (int, float))
        assert isinstance(result["count"], int)
        assert isinstance(result["top_winners"], list)

    def test_get_notice_detail_found(self):
        result = get_notice_detail(1)
        assert "error" not in result
        assert result.get("notice_id") == "1"

    def test_get_notice_detail_not_found(self):
        result = get_notice_detail(999999)
        assert "error" in result


class TestCompanyTools:
    def test_search_companies_by_city(self):
        results = search_companies(city="合肥", limit=5)
        assert isinstance(results, list)
        assert len(results) > 0
        assert len(results) <= 5
        for r in results:
            assert "company_name" in r
            assert "registered_capital_value" in r

    def test_search_companies_by_city_and_industry(self):
        results = search_companies(city="合肥", industry="房地产", limit=5)
        assert isinstance(results, list)
        for r in results:
            assert "合肥" in r.get("city", "")

    def test_search_companies_min_capital_filters(self):
        results = search_companies(city="合肥", min_capital=50_000_000, limit=20)
        for r in results:
            assert r["registered_capital_value"] >= 50_000_000

    def test_get_company_profile_found(self):
        # Use a company name from the actual data
        results = search_companies(city="合肥", limit=1)
        if results:
            name = results[0]["company_name"]
            profile = get_company_profile(name)
            assert "error" not in profile
            assert "company_name" in profile
            assert "bidding_records" in profile
            assert "peer_count" in profile
            assert isinstance(profile["bidding_records"], list)
            assert isinstance(profile["peer_count"], int)

    def test_get_company_profile_not_found(self):
        profile = get_company_profile("不存在的企业名称XYZ123")
        assert "error" in profile

    def test_find_competitors_returns_list(self):
        # Find a company first, then check competitors
        results = search_companies(city="合肥", limit=1)
        if results:
            name = results[0]["company_name"]
            competitors = find_competitors(name, limit=5)
            assert isinstance(competitors, list)
            if len(competitors) > 0 and "error" not in competitors[0]:
                # Verify sorted by capital descending
                caps = [c.get("registered_capital_value", 0) for c in competitors]
                assert caps == sorted(caps, reverse=True)

    def test_find_competitors_not_found(self):
        competitors = find_competitors("不存在的企业名称XYZ123")
        assert len(competitors) > 0
        assert "error" in competitors[0]


class TestLegalTools:
    def test_search_laws_returns_list_with_fields(self):
        results = search_laws("招标", limit=3)
        assert isinstance(results, list)
        assert len(results) > 0
        assert len(results) <= 3
        for r in results:
            assert "document_title" in r
            assert "content" in r

    def test_search_laws_content_matches_keyword(self):
        results = search_laws("投标", limit=5)
        for r in results:
            content = (r.get("content") or "") + (r.get("document_title") or "")
            assert "投标" in content

    def test_search_laws_no_results(self):
        results = search_laws("XYZZY_NOMATCH_LEGAL")
        assert results == []

    def test_get_article_not_found_returns_error(self):
        result = get_article("不存在的法律名称", "999")
        assert "error" in result
