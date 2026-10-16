"""オッズ JSON パーサー (race.netkeiba.com/api/api_get_jra_odds.html)."""

import json
import logging
from typing import NamedTuple

from .base import BaseParser
from repository.models import OddsRow, PreRaceOddsRow

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
        # "result" は確定オッズ、"middle" は発走前リアルタイムオッズ、"yoso" は予想オッズ。いずれも有効。
        if status not in ("result", "middle", "yoso"):
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


class AllOddsResult(NamedTuple):
    """AllOddsParser.parse() の戻り値."""

    status: str
    official_datetime: str | None
    rows: list[OddsRow]


class AllOddsParser(BaseParser):
    """オッズ API (type=all) の JSON レスポンスから全券種のオッズを抽出するパーサー.

    ``data.odds`` のキーは券種（1=単勝 2=複勝 3=枠連 4=馬連 5=ワイド 6=馬単
    7=三連複 8=三連単）、値は人気順をキーにした
    ``[オッズ, オッズ上限(複勝・ワイドのみ。他は "0.0"), 人気, 組番]`` の dict。
    """

    def parse(self, payload: str) -> AllOddsResult:
        """JSON レスポンス文字列を受け取り、status・確定時刻・全券種のオッズ行を返す.

        取得できない（status=NG など）場合も例外にせず、rows を空にして status を返す。
        取得不可のレースを呼び出し側で記録し、再取得の対象から外せるようにするため。
        """
        try:
            doc = json.loads(payload)
        except json.JSONDecodeError as e:
            raise ValueError(f"オッズ JSON のパースに失敗しました: {e}") from e

        status = str(doc.get("status") or "")
        data = doc.get("data")
        if not isinstance(data, dict):
            return AllOddsResult(status, None, [])

        official_datetime = data.get("official_datetime") or None
        odds_by_type = data.get("odds")
        if not isinstance(odds_by_type, dict):
            return AllOddsResult(status, official_datetime, [])

        rows: list[OddsRow] = []
        for bet_type, entries in odds_by_type.items():
            if not isinstance(entries, dict):
                continue
            for entry in entries.values():
                if not isinstance(entry, list) or len(entry) < 4:
                    continue
                combination = str(entry[3]).strip()
                if not combination.isdigit():
                    continue
                rows.append(
                    {
                        "券種": str(bet_type),
                        "組番": combination,
                        "オッズ": str(entry[0]).strip(),
                        "オッズ上限": str(entry[1]).strip(),
                        "人気": str(entry[2]).strip(),
                    }
                )

        return AllOddsResult(status, official_datetime, rows)
