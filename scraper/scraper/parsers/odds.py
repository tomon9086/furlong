"""単勝オッズ JSON パーサー (race.netkeiba.com/api/api_get_jra_odds.html)."""

import json
import logging

from .base import BaseParser
from repository.models import PreRaceOddsRow

logger = logging.getLogger(__name__)


class OddsParser(BaseParser):
    """api_get_jra_odds.html の JSON レスポンスから単勝オッズを抽出するパーサー."""

    def parse(self, payload: str) -> list[PreRaceOddsRow]:
        """JSON レスポンス文字列を受け取り、馬番と単勝オッズの一覧を返す."""
        try:
            doc = json.loads(payload)
        except json.JSONDecodeError as e:
            raise ValueError(f"オッズ JSON のパースに失敗しました: {e}") from e

        status = doc.get("status")
        # "result" は確定オッズ、"middle" は発走前リアルタイムオッズ。どちらも有効。
        if status not in ("result", "middle"):
            reason = doc.get("reason", "")
            raise ValueError(
                f"オッズデータが取得できませんでした (status={status}, reason={reason})"
            )

        data = doc.get("data")
        if not isinstance(data, dict):
            raise ValueError("オッズデータが空です")

        # data.odds["1"] が単勝。キーは人気順、値は [単勝オッズ, _, 人気順, 馬番(0埋め2桁)]
        tan_odds = data.get("odds", {}).get("1")
        if not isinstance(tan_odds, dict) or not tan_odds:
            raise ValueError("単勝オッズデータ行が見つかりません")

        rows: list[PreRaceOddsRow] = []
        for entry in tan_odds.values():
            if not isinstance(entry, list) or len(entry) < 4:
                continue
            odds_text = str(entry[0]).strip()
            horse_num_raw = str(entry[3]).strip()
            if not odds_text or odds_text in ("---", "--"):
                continue
            if not horse_num_raw.isdigit():
                continue
            horse_number = str(int(horse_num_raw))
            rows.append({"馬番": horse_number, "単勝オッズ": odds_text})

        if not rows:
            raise ValueError("単勝オッズデータ行が見つかりません")

        return rows
