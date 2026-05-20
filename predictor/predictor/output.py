"""予測結果の出力モジュール"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

_OUTPUT_DIR = Path("output")
_EV_THRESHOLD = 1.5


def _mark_recommended(pred_df: pd.DataFrame) -> pd.DataFrame:
    """推奨買い目フラグを付与する。

    - 単勝: win_prob 上位1頭 かつ EV（win_prob × odds）> _EV_THRESHOLD
    - 複勝: place_prob 上位3頭
    """
    df = pred_df.copy()

    if "odds" in df.columns:
        df["odds"] = pd.to_numeric(df["odds"], errors="coerce")
        df["ev"] = df["win_prob"] * df["odds"]

    win_top_idx = df.groupby("race_id")["win_prob"].idxmax()
    df["recommended_win"] = False
    if "ev" in df.columns:
        valid_win_idx = [i for i in win_top_idx if df.loc[i, "ev"] > _EV_THRESHOLD]
    else:
        valid_win_idx = list(win_top_idx)
    df.loc[valid_win_idx, "recommended_win"] = True

    place_rank = df.groupby("race_id")["place_prob"].rank(ascending=False, method="min")
    df["recommended_place"] = place_rank <= 3

    df["recommended"] = df["recommended_win"] | df["recommended_place"]

    return df


def print_prediction(pred_df: pd.DataFrame) -> None:
    """予測結果を標準出力に表示する。"""
    df = _mark_recommended(pred_df)
    display_cols = [
        "horse_number",
        "win_prob",
        "place_prob",
        "predicted_rank",
        "recommended",
    ]
    if "horse_name" in df.columns:
        display_cols.insert(1, "horse_name")
    if "ev" in df.columns:
        display_cols.insert(display_cols.index("recommended"), "ev")

    for race_id, group in df.groupby("race_id"):
        group = group.sort_values("predicted_rank")
        print(f"\n=== レース {race_id} ===")
        print(group[display_cols].to_string(index=False))

        win_horses = group[group["recommended_win"]]
        place_horses = group[group["recommended_place"]]

        print("\n  推奨買い目:")
        if win_horses.empty:
            print(f"    単勝 : (EV しきい値 {_EV_THRESHOLD} 未達・推奨なし)")
        else:
            print(f"    単勝 : {win_horses['horse_number'].tolist()}")
        print(f"    複勝 : {place_horses['horse_number'].tolist()}")
        if len(place_horses) >= 2:
            top2 = place_horses.nsmallest(2, "predicted_rank")["horse_number"].tolist()
            print(f"    馬連  : {top2[0]}-{top2[1]}")
        if len(place_horses) >= 3:
            top3 = place_horses.nsmallest(3, "predicted_rank")["horse_number"].tolist()
            print(f"    三連複: {top3[0]}-{top3[1]}-{top3[2]}")


def save_csv(
    pred_df: pd.DataFrame, race_id: str, output_dir: Path = _OUTPUT_DIR
) -> None:
    """予測結果を CSV ファイルに保存する。"""
    df = _mark_recommended(pred_df)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"prediction_{race_id}.csv"
    df.sort_values(["race_id", "predicted_rank"]).to_csv(path, index=False)
    print(f"CSV 保存: {path}")
