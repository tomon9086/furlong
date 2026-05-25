"""単勝オッズHTMLパーサー (race.netkeiba.com/odds/)."""

import logging
import re

from .base import BaseParser
from repository.models import PreRaceOddsRow

logger = logging.getLogger(__name__)


class OddsParser(BaseParser):
    """単勝オッズページ (/odds/index.html?race_id=...) のHTMLパーサー."""

    def parse(self, html: str) -> list[PreRaceOddsRow]:
        """id="tr_N" 形式の行から馬番と単勝オッズを抽出する."""
        soup = self.parse_html(html)

        rows: list[PreRaceOddsRow] = []
        for tr in soup.find_all("tr", id=re.compile(r"^tr_\d+$")):
            row = self._parse_odds_row(tr)
            if row:
                rows.append(row)

        if not rows:
            raise ValueError("単勝オッズデータ行が見つかりません")

        return rows

    def _parse_odds_row(self, tr) -> PreRaceOddsRow | None:  # type: ignore[return]
        tr_id = tr.get("id", "")
        m = re.search(r"tr_(\d+)", tr_id)
        if not m:
            return None

        horse_num_str = m.group(1)
        horse_number = str(int(horse_num_str))

        # id="odds_N" セルからオッズ取得
        odds_td = tr.find("td", id=re.compile(rf"^odds_{re.escape(horse_num_str)}$"))
        if not odds_td:
            return None

        odds_text = odds_td.get_text(strip=True)
        if not odds_text or odds_text in ("---", "--", ""):
            return None

        return {"馬番": horse_number, "単勝オッズ": odds_text}
