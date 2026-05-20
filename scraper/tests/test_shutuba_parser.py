"""scraper.parsers.shutuba の単体テスト."""

import pytest

from scraper.parsers.shutuba import ShutsubaParser


@pytest.fixture
def parser() -> ShutsubaParser:
    return ShutsubaParser()


# ──────────────────────────────────────────────
# parse (出走馬リスト抽出)
# ──────────────────────────────────────────────

_SHUTUBA_HTML = """
<html><body>
<table class="Shutuba_Table">
  <tr class="HorseList" id="tr_01">
    <td class="Waku"><span>1</span></td>
    <td class="Umaban">1</td>
    <td class="HorseName"><a href="/horse/2019105806">テストウマA</a></td>
    <td class="Barei">牡4</td>
    <td class="Kingairyo">57.0</td>
    <td class="Jockey"><a href="/jockey/result/recent/01234/">テスト騎手A</a></td>
    <td class="Trainer"><a href="/trainer/result/recent/56789/">テスト調教師A</a></td>
    <td class="Odds">5.2</td>
    <td class="Popular">2</td>
  </tr>
  <tr class="HorseList" id="tr_02">
    <td class="Waku"><span>1</span></td>
    <td class="Umaban">2</td>
    <td class="HorseName"><a href="/horse/2020100002">テストウマB</a></td>
    <td class="Barei">牝3</td>
    <td class="Kingairyo">54.0</td>
    <td class="Jockey"><a href="/jockey/result/recent/09876/">テスト騎手B</a></td>
    <td class="Trainer"><a href="/trainer/result/recent/43210/">テスト調教師B</a></td>
    <td class="Odds">12.4</td>
    <td class="Popular">5</td>
  </tr>
</table>
</body></html>
"""

_SHUTUBA_NO_UMABAN_HTML = """
<html><body>
<table class="Shutuba_Table">
  <tr class="HorseList" id="tr_03">
    <td class="HorseName"><a href="/horse/2019100003">枠順未確定ウマ</a></td>
    <td class="Barei">牡5</td>
    <td class="Kingairyo">57.0</td>
    <td class="Jockey"><a href="/jockey/result/recent/11111/">テスト騎手C</a></td>
    <td class="Trainer"><a href="/trainer/result/recent/22222/">テスト調教師C</a></td>
  </tr>
</table>
</body></html>
"""


class TestShutubaParse:
    def test_returns_two_rows(self, parser: ShutsubaParser):
        rows = parser.parse(_SHUTUBA_HTML)
        assert len(rows) == 2

    def test_horse_id_extracted(self, parser: ShutsubaParser):
        rows = parser.parse(_SHUTUBA_HTML)
        assert rows[0]["馬ID"] == "2019105806"
        assert rows[1]["馬ID"] == "2020100002"

    def test_umaban_extracted(self, parser: ShutsubaParser):
        rows = parser.parse(_SHUTUBA_HTML)
        assert rows[0]["馬番"] == "1"
        assert rows[1]["馬番"] == "2"

    def test_jockey_id_extracted(self, parser: ShutsubaParser):
        rows = parser.parse(_SHUTUBA_HTML)
        assert rows[0]["騎手ID"] == "01234"
        assert rows[1]["騎手ID"] == "09876"

    def test_trainer_id_extracted(self, parser: ShutsubaParser):
        rows = parser.parse(_SHUTUBA_HTML)
        assert rows[0]["調教師ID"] == "56789"
        assert rows[1]["調教師ID"] == "43210"

    def test_odds_extracted(self, parser: ShutsubaParser):
        rows = parser.parse(_SHUTUBA_HTML)
        assert rows[0]["単勝オッズ"] == "5.2"

    def test_umaban_from_tr_id_when_no_umaban_td(self, parser: ShutsubaParser):
        """Umaban クラスの td がないとき tr の id="tr_XX" から馬番を取得する."""
        rows = parser.parse(_SHUTUBA_NO_UMABAN_HTML)
        assert len(rows) == 1
        assert rows[0]["馬番"] == "3"

    def test_empty_html_raises(self, parser: ShutsubaParser):
        with pytest.raises(ValueError, match="出馬表にデータ行が見つかりません"):
            parser.parse("<html><body></body></html>")


# ──────────────────────────────────────────────
# parse_race_info (レースメタ情報抽出)
# ──────────────────────────────────────────────

_RACE_INFO_HTML = """
<html><body>
<h1 class="RaceName">テストレース</h1>
<div class="RaceData01">
  <span>15:45発走</span>
  <span>芝右1600m</span>
  <span>天候:晴</span>
  <span>馬場:良</span>
</div>
<div class="RaceData02">
  <ul>
    <li>2026年5月20日</li>
    <li>1回東京3日目</li>
    <li>11R</li>
  </ul>
</div>
</body></html>
"""


class TestParseRaceInfo:
    def test_race_name(self, parser: ShutsubaParser):
        info = parser.parse_race_info(_RACE_INFO_HTML)
        assert info["レース名"] == "テストレース"

    def test_course_type(self, parser: ShutsubaParser):
        info = parser.parse_race_info(_RACE_INFO_HTML)
        assert info["コース種別"] == "芝"

    def test_distance(self, parser: ShutsubaParser):
        info = parser.parse_race_info(_RACE_INFO_HTML)
        assert info["距離"] == "1600"

    def test_direction(self, parser: ShutsubaParser):
        info = parser.parse_race_info(_RACE_INFO_HTML)
        assert info["回り"] == "右"

    def test_start_time(self, parser: ShutsubaParser):
        info = parser.parse_race_info(_RACE_INFO_HTML)
        assert info["発走時刻"] == "15:45"

    def test_date(self, parser: ShutsubaParser):
        info = parser.parse_race_info(_RACE_INFO_HTML)
        assert info["日付"] == "2026/05/20"

    def test_venue(self, parser: ShutsubaParser):
        info = parser.parse_race_info(_RACE_INFO_HTML)
        assert info["開催"] == "東京"

    def test_race_number(self, parser: ShutsubaParser):
        info = parser.parse_race_info(_RACE_INFO_HTML)
        assert info["R"] == "11"

    def test_empty_html_returns_empty(self, parser: ShutsubaParser):
        info = parser.parse_race_info("<html><body></body></html>")
        assert info == {}
