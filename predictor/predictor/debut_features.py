"""初出走・キャリアの浅い馬向けの特徴量。

gap-analysis で、モデルと市場の差は新馬戦・初出走の馬で最も大きかった（過去の成績が
無い馬について、モデルには材料がほとんど無い）。そこで、本人の成績が無くても
使える「身内・関係者の実績」を特徴量にする。

    dam_progeny_place_rate : 同じ母の他の産駒（兄・姉）のこれまでの3着内率
    dam_progeny_starts     : 同じ母の他の産駒のこれまでの出走数
    trainer_debut_place_rate : その調教師の管理馬のデビュー戦での3着内率
    sire_debut_place_rate  : 同じ父の産駒のデビュー戦での3着内率

いずれもそのレースの前日までのデータだけで計算する（同じ日のレースは含めない）。
少ない件数で極端な値にならないよう、全体の3着内率に向けて縮小する
（(3着内回数 + m × 全体の率) / (出走数 + m)、ADR-0028 と同じ考え方）。
デビュー戦は、データ上でその馬の最初の出走とする（1995年より前のデビューは区別できない）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DEBUT_COLUMNS = [
    "dam_progeny_place_rate",
    "dam_progeny_starts",
    "trainer_debut_place_rate",
    "sire_debut_place_rate",
]
SHRINKAGE = 20.0


def _prior_daily_cumsum(
    keys: pd.Series, dates: pd.Series, values: pd.Series
) -> np.ndarray:
    """各行について、同じキーの「前日まで」の values の合計（同じ日は含めない）。"""
    daily = (
        pd.DataFrame({"key": keys.to_numpy(), "date": dates.to_numpy(), "v": values})
        .groupby(["key", "date"], observed=True)["v"]
        .sum()
        .groupby(level="key", observed=True)
        .cumsum()
        .groupby(level="key", observed=True)
        .shift(1, fill_value=0.0)
    )
    index = pd.MultiIndex.from_arrays([keys.to_numpy(), dates.to_numpy()])
    return daily.reindex(index).to_numpy()


def add_debut_features(df: pd.DataFrame) -> pd.DataFrame:
    """初出走向けの特徴量を付けた df を返す。

    df は1頭1レースで、race_id・horse_id・dam・sire・trainer_id・date・
    is_placed を含む。
    """
    data = df.copy()
    placed = data["is_placed"].astype(float)
    starts = pd.Series(1.0, index=data.index)
    global_rate = float(placed.mean())

    # 本人のこれまでの出走数・3着内回数（同じ日に2回走ることはないので行単位でよい）
    order = data.sort_values(["date", "race_id"]).index
    by_horse = data.loc[order].groupby("horse_id", observed=True)
    own_starts = by_horse.cumcount().reindex(data.index).to_numpy(dtype=float)
    own_placed = (
        by_horse["is_placed"].cumsum().reindex(data.index).to_numpy(dtype=float)
        - placed.to_numpy()
    )

    # 母の他の産駒: 母全体の前日までの実績から本人の分を引く
    dam = data["dam"].astype(str).replace({"": np.nan, "nan": np.nan, "None": np.nan})
    dam_starts = _prior_daily_cumsum(dam.fillna("_unknown"), data["date"], starts)
    dam_placed = _prior_daily_cumsum(dam.fillna("_unknown"), data["date"], placed)
    sib_starts = np.clip(dam_starts - own_starts, 0, None)
    sib_placed = np.clip(dam_placed - own_placed, 0, None)
    sib_rate = (sib_placed + SHRINKAGE * global_rate) / (sib_starts + SHRINKAGE)
    data["dam_progeny_place_rate"] = np.where(dam.isna(), np.nan, sib_rate)
    data["dam_progeny_starts"] = np.where(dam.isna(), np.nan, sib_starts)

    # デビュー戦での実績（調教師・父ごと）
    is_debut = (own_starts == 0).astype(float)
    debut_placed = placed.to_numpy() * is_debut
    debut_rate = float(debut_placed.sum() / max(is_debut.sum(), 1))
    for col, key in (
        ("trainer_debut_place_rate", "trainer_id"),
        ("sire_debut_place_rate", "sire"),
    ):
        k = data[key].astype(str).fillna("_unknown")
        n = _prior_daily_cumsum(k, data["date"], pd.Series(is_debut, index=data.index))
        p = _prior_daily_cumsum(
            k, data["date"], pd.Series(debut_placed, index=data.index)
        )
        data[col] = (p + SHRINKAGE * debut_rate) / (n + SHRINKAGE)
    return data
