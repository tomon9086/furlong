"""scraper.parsers.race_detail の単体テスト."""

import pytest

from scraper.parsers.race_detail import RaceDetailParser


@pytest.fixture
def parser() -> RaceDetailParser:
    return RaceDetailParser()


# ──────────────────────────────────────────────
# _parse_condition_text
# ──────────────────────────────────────────────


class TestParseConditionText:
    def test_turf_right(self, parser: RaceDetailParser):
        text = "芝右1600m / 天候 : 晴 / 芝 : 良 / 発走 : 15:45"
        result = parser._parse_condition_text(text)
        assert result["コース種別"] == "芝"
        assert result["回り"] == "右"
        assert result["距離"] == "1600"
        assert result["天候"] == "晴"
        assert result["馬場状態"] == "良"
        assert result["発走時刻"] == "15:45"

    def test_dirt_left(self, parser: RaceDetailParser):
        text = "ダ左1200m / 天候 : 曇 / ダート : 稍重 / 発走 : 11:35"
        result = parser._parse_condition_text(text)
        assert result["コース種別"] == "ダート"
        assert result["回り"] == "左"
        assert result["距離"] == "1200"
        assert result["天候"] == "曇"
        assert result["馬場状態"] == "稍重"

    def test_obstacle_no_direction(self, parser: RaceDetailParser):
        """障害コースは回りなし。"""
        text = "障2500m / 天候 : 晴 / 障害 : 良 / 発走 : 13:00"
        result = parser._parse_condition_text(text)
        assert result["コース種別"] == "障害"
        assert result["距離"] == "2500"
        assert "回り" not in result

    def test_empty_string(self, parser: RaceDetailParser):
        assert parser._parse_condition_text("") == {}


# ──────────────────────────────────────────────
# parse (出走馬リスト抽出)
# ──────────────────────────────────────────────

_RACE_DETAIL_HTML = """
<html><body>
<table class="race_table_01">
  <tr>
    <th>着順</th><th>枠番</th><th>馬番</th><th>馬名</th>
    <th>性齢</th><th>斤量</th><th>騎手</th><th>タイム</th>
    <th>着差</th><th>通過</th><th>上り</th><th>単勝オッズ</th>
    <th>人気</th><th>馬体重</th><th>調教師</th>
  </tr>
  <tr>
    <td>1</td><td>1</td><td>3</td>
    <td><a href="/horse/2019100001">テストウマ</a></td>
    <td>牡4</td><td>57</td>
    <td><a href="/jockey/result/recent/01234/">テスト騎手</a></td>
    <td>1:33.4</td><td></td><td>04-04</td><td>34.5</td>
    <td>5.2</td><td>2</td><td>480(0)</td>
    <td><a href="/trainer/result/recent/56789/">テスト調教師</a></td>
  </tr>
</table>
</body></html>
"""


class TestRaceDetailParse:
    def test_returns_one_row(self, parser: RaceDetailParser):
        rows = parser.parse(_RACE_DETAIL_HTML)
        assert len(rows) == 1

    def test_horse_id_extracted(self, parser: RaceDetailParser):
        rows = parser.parse(_RACE_DETAIL_HTML)
        assert rows[0]["馬ID"] == "2019100001"

    def test_jockey_id_extracted(self, parser: RaceDetailParser):
        rows = parser.parse(_RACE_DETAIL_HTML)
        assert rows[0]["騎手ID"] == "01234"

    def test_trainer_id_extracted(self, parser: RaceDetailParser):
        rows = parser.parse(_RACE_DETAIL_HTML)
        assert rows[0]["調教師ID"] == "56789"

    def test_missing_table_raises(self, parser: RaceDetailParser):
        with pytest.raises(ValueError, match="レース結果テーブルが見つかりません"):
            parser.parse("<html><body></body></html>")
