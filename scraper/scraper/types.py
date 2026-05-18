"""型定義."""

from typing import TypedDict


class RaceInfo(TypedDict, total=False):
    """レースのメタ情報."""

    レース名: str
    R: str
    グレード: str
    日付: str
    開催: str
    コース種別: str
    距離: str
    回り: str
    天候: str
    馬場状態: str
    発走時刻: str


class RaceDetailRow(TypedDict, total=False):
    """レース詳細（結果）の1行（馬ごと）."""

    着順: str
    枠番: str
    馬番: str
    馬名: str
    馬ID: str
    性齢: str
    斤量: str
    騎手: str
    騎手ID: str
    タイム: str
    着差: str
    通過: str
    上り: str
    単勝オッズ: str
    人気: str
    馬体重: str
    調教師: str
    調教師ID: str
    馬主: str
    賞金: str


class PayoffRow(TypedDict, total=False):
    """払い戻し情報の1行."""

    券種: str
    組番: str
    払戻金: str
    人気: str
