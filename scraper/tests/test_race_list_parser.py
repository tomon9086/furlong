"""scraper.parsers.race_list の単体テスト."""

import pytest

from scraper.parsers.race_list import RaceListParser


@pytest.fixture
def parser() -> RaceListParser:
    return RaceListParser()


# ──────────────────────────────────────────────
# parse_total_pages
# ──────────────────────────────────────────────


class TestParseTotalPages:
    def test_multi_page_page1(self, parser: RaceListParser):
        """1ページ目のサマリー(1,717件中1~100件目)から総ページ数を計算する。

        実際のページ送りリンクは class="pager" の外(li要素)にあり、
        pager div は件数サマリーのテキストしか持たないため、リンク走査ではなく
        このテキストから件数を読み取る必要がある。
        """
        html = '<html><body><div class="pager">1,717件中1~100件目</div></body></html>'
        assert parser.parse_total_pages(html) == 18

    def test_multi_page_page2(self, parser: RaceListParser):
        """2ページ目以降でも開始・終了番号から1ページあたり件数を正しく算出する。"""
        html = '<html><body><div class="pager">1,717件中101~200件目</div></body></html>'
        assert parser.parse_total_pages(html) == 18

    def test_single_page(self, parser: RaceListParser):
        html = '<html><body><div class="pager">45件中1~45件目</div></body></html>'
        assert parser.parse_total_pages(html) == 1

    def test_no_pager(self, parser: RaceListParser):
        html = "<html><body><p>no pager here</p></body></html>"
        assert parser.parse_total_pages(html) == 1

    def test_unparseable_pager_text(self, parser: RaceListParser):
        html = '<html><body><div class="pager">不明なフォーマット</div></body></html>'
        assert parser.parse_total_pages(html) == 1
