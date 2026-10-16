"""scraper.parsers.odds の単体テスト."""

import json

import pytest

from scraper.parsers.odds import AllOddsParser


@pytest.fixture
def parser() -> AllOddsParser:
    return AllOddsParser()


def _payload(status: str = "result", odds: dict | None = None) -> str:
    """api_get_jra_odds.html (type=all) の応答を模した JSON を返す."""
    if odds is None:
        odds = {
            "1": {"1": ["4.0", "0.0", "1", "12"], "2": ["---", "0.0", "", "05"]},
            "2": {"1": ["1.2", "1.6", "1", "12"]},
            "5": {"1": ["3.2", "3.7", "1", "0712"]},
            "7": {"1": ["11.3", "0.0", "1", "030712"]},
            "8": {"1": ["53.9", "0.0", "1", "030712"]},
        }
    return json.dumps(
        {
            "status": status,
            "data": {"official_datetime": "2019-12-28 09:55:40", "odds": odds},
            "update_count": "",
            "reason": "",
        }
    )


class TestAllOddsParser:
    def test_status_and_official_datetime(self, parser: AllOddsParser):
        result = parser.parse(_payload())
        assert result.status == "result"
        assert result.official_datetime == "2019-12-28 09:55:40"

    def test_rows_cover_all_bet_types(self, parser: AllOddsParser):
        """三連単（8）を含む全券種の行を返す（final_odds への展開時に絞り込む）。"""
        result = parser.parse(_payload())
        assert {r["券種"] for r in result.rows} == {"1", "2", "5", "7", "8"}

    def test_row_fields(self, parser: AllOddsParser):
        result = parser.parse(_payload())
        wide = next(r for r in result.rows if r["券種"] == "5")
        assert wide == {
            "券種": "5",
            "組番": "0712",
            "オッズ": "3.2",
            "オッズ上限": "3.7",
            "人気": "1",
        }

    def test_keeps_unavailable_odds_as_text(self, parser: AllOddsParser):
        """取消馬などの "---" はパーサーでは捨てない。

        数値化できない行は、final_odds への保存時に除く。
        """
        result = parser.parse(_payload())
        assert any(r["オッズ"] == "---" for r in result.rows)

    def test_ng_status_returns_empty_rows(self, parser: AllOddsParser):
        """取得不可（2007年6月以前など）でも例外にせず status を返す。"""
        payload = json.dumps(
            {"status": "NG", "data": "", "reason": "empty free odds schedule"}
        )
        result = parser.parse(payload)
        assert result.status == "NG"
        assert result.official_datetime is None
        assert result.rows == []

    def test_invalid_json_raises(self, parser: AllOddsParser):
        with pytest.raises(ValueError):
            parser.parse("<html>not json</html>")
