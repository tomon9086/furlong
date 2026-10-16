"""JRA 学習データの開催場拡張（4場 → 10場）の比較実験スクリプト。

2026-10-16 まで、1995〜2025年の JRA レースは東京・中山・中京・京都の4場しか
DB に無かった（別プロジェクトの設定由来。docs/todo.md の 1-1 参照）。残り6場
（札幌・函館・福島・新潟・阪神・小倉）を補完したことで、学習データがどう変わったか、
これまでの4場データでの判断（ADR）が前提として崩れていないかを確かめる。

比較するモデル:
    a: 4場のレースだけで学習（補完前の状態を再現）
    b: 10場すべてのレースで学習（補完後）

重要: 近走成績・騎手/調教師/血統の累積統計量（``compute_recent_stats``）は
DB にあるレースから計算されるため、4場モデルは4場のレースだけに絞ってから
特徴量計算をやり直す。先に10場で特徴量計算してから学習行だけ絞ると、
6場の実績が累積統計量経由で4場モデルにリークし、補完前の状態を再現できない
（``nar_data_volume_experiment`` と同じ考え方）。

評価:
    - 主検定: テスト期間の4場のレースで a と b をペアードbootstrapで比較する
      （同じレース集合で比べないと、6場を含むかどうかで難易度が変わってしまう）。
    - 参考: b の6場・10場全体での指標（a は6場を予測できる前提にないため比較なし）。
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from predictor import calibration, evaluation, model
from predictor.preprocessing import compute_recent_stats, split_by_date

logger = logging.getLogger(__name__)

_OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"

# 補完前に DB にあった4場
ORIGINAL_VENUES: list[str] = ["東京", "中山", "中京", "京都"]


def _train_and_predict(
    df: pd.DataFrame,
    val_date: "pd.Timestamp",
    test_date: "pd.Timestamp",
    half_life_days: float | None,
    label: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """特徴量計算・学習・較正・予測を行い、(テスト期間の行, 予測結果) を返す。"""
    logger.info(f"[{label}] 近走成績フィーチャーを計算中...（{len(df):,}行）")
    featured = compute_recent_stats(df)

    sub_train = featured[featured["date"] < val_date]
    sub_val = featured[(featured["date"] >= val_date) & (featured["date"] < test_date)]
    sub_test = featured[featured["date"] >= test_date]
    logger.info(
        f"[{label}] 学習{len(sub_train):,}行 / 較正{len(sub_val):,}行 / "
        f"テスト{len(sub_test):,}行"
    )

    models = model.train(sub_train, half_life_days=half_life_days)
    calibrated = calibration.calibrate_models(models, sub_val)
    pred_df = model.predict(calibrated, sub_test)
    return sub_test, pred_df


def run(
    df: pd.DataFrame,
    half_life_days: float | None = 1095.0,
    n_bootstrap: int = 10_000,
    random_state: int | None = 42,
) -> dict[str, pd.DataFrame]:
    """4場モデルと10場モデルを学習・評価する。

    Parameters
    ----------
    df : pd.DataFrame
        ``preprocess()`` 済み・``compute_recent_stats()`` 未適用の JRA 10場のデータ。
    half_life_days : float | None
        実運用（``train_mode`` のデフォルト）と同じ時間減衰ウェイトを適用する。

    Returns
    -------
    dict[str, pd.DataFrame]
        ``paired``: 4場のテストレースでのペアードbootstrap検定結果（a=4場, b=10場）
        ``reference``: 10場モデルの開催場グループ別の指標
    """
    # val/test の日付境界は10場データで決め、両モデル共通で固定する
    # （テスト対象期間を揃えるため）。
    _, val_df_full, test_df_full = split_by_date(df)
    val_date = val_df_full["date"].min()
    test_date = test_df_full["date"].min()
    logger.info(f"較正開始日 {val_date.date()} / テスト開始日 {test_date.date()}")

    df_a = df[df["venue"].isin(ORIGINAL_VENUES)].copy()
    test_a, pred_a = _train_and_predict(
        df_a, val_date, test_date, half_life_days, "4場"
    )
    test_b, pred_b = _train_and_predict(
        df, val_date, test_date, half_life_days, "10場"
    )

    logger.info("4場のテストレースでペアードbootstrap検定中...")
    paired = evaluation.paired_bootstrap_model_comparison(
        test_a, pred_a, pred_b, n_bootstrap=n_bootstrap, random_state=random_state
    )
    paired.attrs["label_a"] = "4場で学習"
    paired.attrs["label_b"] = "10場で学習"

    reference_rows = []
    groups = {
        "4場": test_b["venue"].isin(ORIGINAL_VENUES),
        "6場": ~test_b["venue"].isin(ORIGINAL_VENUES),
        "10場": pd.Series(True, index=test_b.index),
    }
    for name, mask in groups.items():
        sub_test = test_b[mask]
        metrics = evaluation.evaluate(sub_test, pred_b)
        reference_rows.append(
            {
                "開催場": name,
                "テストレース数": sub_test["race_id"].nunique(),
                **metrics,
            }
        )
    reference = pd.DataFrame(reference_rows).set_index("開催場")

    return {"paired": paired, "reference": reference}


def save_results(
    results: dict[str, pd.DataFrame], output_dir: Path = _OUTPUT_DIR
) -> list[Path]:
    """結果を CSV に保存し、保存先パスを返す。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    paths = []
    for name, frame in results.items():
        path = output_dir / f"venue_expansion_{name}_{timestamp}.csv"
        frame.to_csv(path)
        paths.append(path)
    return paths
