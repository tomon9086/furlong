"""scraper.parsers.horse の単体テスト."""

import pytest

from scraper.parsers.horse import HorseParser


@pytest.fixture
def parser() -> HorseParser:
    return HorseParser()


# ──────────────────────────────────────────────
# parse_pedigree / _parse_blood_table
# ──────────────────────────────────────────────

# 3代血統表相当（父・母は rowspan=2、祖父母は rowspan なし）。
# 旧仕様（netkeiba の馬詳細ページにインラインで表示されていた頃）の形。
_PEDIGREE_3GEN_HTML = """
<html><body>
<table class="blood_table">
<tr>
  <td rowspan="2"><a href="/horse/sire/">父ウマ</a></td>
  <td><a href="/horse/ff/">父父ウマ</a></td>
</tr>
<tr>
  <td><a href="/horse/fm/">父母ウマ</a></td>
</tr>
<tr>
  <td rowspan="2"><a href="/horse/dam/">母ウマ</a></td>
  <td><a href="/horse/mf/">母父ウマ</a></td>
</tr>
<tr>
  <td><a href="/horse/mm/">母母ウマ</a></td>
</tr>
</table>
</body></html>
"""

# より深い世代（父・母は rowspan=4）の血統表。
# 現行の /horse/ped/{horse_id}/ ページ（5代血統表）はこの形の拡張版。
_PEDIGREE_DEEPER_HTML = """
<html><body>
<table class="blood_table detail">
<tr>
  <td rowspan="4"><a href="/horse/sire/">父ウマ</a></td>
  <td rowspan="2"><a href="/horse/ff/">父父ウマ</a></td>
  <td><a href="/horse/fff/">父父父ウマ</a></td>
</tr>
<tr>
  <td><a href="/horse/ffm/">父父母ウマ</a></td>
</tr>
<tr>
  <td rowspan="2"><a href="/horse/fm/">父母ウマ</a></td>
  <td><a href="/horse/fmf/">父母父ウマ</a></td>
</tr>
<tr>
  <td><a href="/horse/fmm/">父母母ウマ</a></td>
</tr>
<tr>
  <td rowspan="4"><a href="/horse/dam/">母ウマ</a></td>
  <td rowspan="2"><a href="/horse/mf/">母父ウマ</a></td>
  <td><a href="/horse/mff/">母父父ウマ</a></td>
</tr>
<tr>
  <td><a href="/horse/mfm/">母父母ウマ</a></td>
</tr>
<tr>
  <td rowspan="2"><a href="/horse/mm/">母母ウマ</a></td>
  <td><a href="/horse/mmf/">母母父ウマ</a></td>
</tr>
<tr>
  <td><a href="/horse/mmm/">母母母ウマ</a></td>
</tr>
</table>
</body></html>
"""

_NO_BLOOD_TABLE_HTML = """
<html><body>
<table class="db_prof_table"><tr><th>馬名</th><td>テストウマ</td></tr></table>
</body></html>
"""


class TestParsePedigree:
    def test_3_generation_table(self, parser: HorseParser):
        """3代血統表（父・母が rowspan=2）から父・母・母父を正しく抽出すること。"""
        result = parser.parse_pedigree(_PEDIGREE_3GEN_HTML)
        assert result == {
            "父": "父ウマ",
            "母": "母ウマ",
            "母父": "母父ウマ",
        }

    def test_deeper_generation_table(self, parser: HorseParser):
        """父・母が rowspan=4 のより深い血統表でも、世代を正しく特定できること。

        （固定インデックス [0], [1] で取っていた旧ロジックでは、[1] が
        父父ウマ（父の父）を指してしまい母を取り違えるバグがあった）
        """
        result = parser.parse_pedigree(_PEDIGREE_DEEPER_HTML)
        assert result == {
            "父": "父ウマ",
            "母": "母ウマ",
            "母父": "母父ウマ",
        }

    def test_no_blood_table_returns_empty(self, parser: HorseParser):
        """血統テーブルが存在しないページでは空 dict を返すこと。"""
        result = parser.parse_pedigree(_NO_BLOOD_TABLE_HTML)
        assert result == {}
