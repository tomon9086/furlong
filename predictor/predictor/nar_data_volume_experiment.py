"""地方競馬モデルの学習データ量（年数）比較実験スクリプト。

30年分の遡及スクレイピングに投資する価値があるか判断する材料として、
学習データを直近N年に絞った場合に性能がどう変化するかを比較する。

重要: 近走成績・騎手/調教師/血統の累積統計量（``compute_recent_stats``）は
「その時点で遡れる範囲」に依存するため、学習期間を絞り込んだ**あとで**
特徴量計算をやり直す必要がある。先に全期間で特徴量計算してから学習行だけ
絞ると、「本来スクレイピングできていないはずの古い期間」の情報が
累積統計量経由でリークし、データ量を絞った効果が正しく測れない
（例: 騎手の通算勝率が、実際には無いはずの古い年代の実績まで含んで
計算されてしまう）。
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

# None = 学習データの全期間を使う。
DEFAULT_YEARS_OPTIONS: list[int | None] = [2, 4, 6, 8, None]


def _train_and_predict_for_years(
    df: pd.DataFrame,
    years: int | None,
    val_date: "pd.Timestamp",
    test_date: "pd.Timestamp",
    half_life_days: float | None,
) -> tuple[str, "pd.Timestamp", int, pd.DataFrame, pd.DataFrame]:
    """指定年数に学習データを絞り込み、特徴量再計算・学習・予測までを行う。

    Returns
    -------
    (label, train_start, train_rows, sub_test, pred_df)
        sub_test はテスト期間の行（``evaluation`` 関数が要求する形）、
        pred_df は ``model.predict`` の出力。
    """
    if years is None:
        train_start = df["date"].min()
        label = "全期間"
    else:
        train_start = val_date - pd.Timedelta(days=365 * years)
        label = f"{years}年"

    # 学習開始日以降（test期間まで含む）だけを残してから特徴量を計算し直す。
    # こうすることで、累積統計量が train_start より前の情報を含まなくなる。
    sub_df = df[df["date"] >= train_start].copy()
    featured = compute_recent_stats(sub_df)

    sub_train = featured[featured["date"] < val_date]
    sub_val = featured[(featured["date"] >= val_date) & (featured["date"] < test_date)]
    sub_test = featured[featured["date"] >= test_date]

    logger.info(
        f"学習中: 学習期間={label}（学習開始 {train_start.date()}、"
        f"学習{len(sub_train):,}行）"
    )
    models = model.train(sub_train, half_life_days=half_life_days)
    calibrated = calibration.calibrate_models(models, sub_val)
    pred_df = model.predict(calibrated, sub_test)

    return label, train_start, len(sub_train), sub_test, pred_df


def run_comparison(
    df: pd.DataFrame,
    years_options: list[int | None] | None = None,
    half_life_days: float | None = 1095.0,
) -> pd.DataFrame:
    """学習データを直近N年に絞った場合の性能を比較する。

    Parameters
    ----------
    df : pd.DataFrame
        ``preprocess()`` 済み・``compute_recent_stats()`` 未適用の生データ。
        年数オプションごとに、学習開始日以降の行だけを残してから
        ``compute_recent_stats`` をやり直す。
    years_options : list[int | None] | None
        学習データを絞る年数のリスト。``None`` は学習データ全期間を使う。
    half_life_days : float | None
        実運用（``nar.py`` のデフォルト）と同じ時間減衰ウェイトを適用する。
    """
    if years_options is None:
        years_options = DEFAULT_YEARS_OPTIONS

    # val/test の日付境界は全パターン共通で固定する（テスト対象レースを揃えるため）。
    _, val_df_full, test_df_full = split_by_date(df)
    val_date = val_df_full["date"].min()
    test_date = test_df_full["date"].min()

    rows = []
    for years in years_options:
        label, train_start, train_rows, sub_test, pred_df = _train_and_predict_for_years(
            df, years, val_date, test_date, half_life_days
        )
        metrics = evaluation.evaluate(sub_test, pred_df)
        rows.append(
            {
                "学習期間": label,
                "学習開始日": train_start.date(),
                "学習行数": train_rows,
                "テスト行数": len(sub_test),
                **metrics,
            }
        )

    return pd.DataFrame(rows).set_index("学習期間")


def significance_test(
    df: pd.DataFrame,
    years_a: int | None,
    years_b: int | None,
    half_life_days: float | None = 1095.0,
    n_bootstrap: int = 10_000,
    random_state: int | None = 42,
) -> pd.DataFrame:
    """2つの学習期間（例: 2年 vs 全期間）の性能差をペアードbootstrapで検定する。

    ``evaluation.paired_bootstrap_model_comparison`` を再利用する（dam特徴量の
    要否検証等で使われた手法と同じ）。sub_test はどちらの学習期間でも同じ
    テスト対象レース（race_id・horse_number・is_win・odds等）を指すため、
    どちらか一方（a側）を検定用の test_df として使えばよい。
    """
    _, val_df_full, test_df_full = split_by_date(df)
    val_date = val_df_full["date"].min()
    test_date = test_df_full["date"].min()

    label_a, _, _, test_a, pred_a = _train_and_predict_for_years(
        df, years_a, val_date, test_date, half_life_days
    )
    label_b, _, _, _test_b, pred_b = _train_and_predict_for_years(
        df, years_b, val_date, test_date, half_life_days
    )

    logger.info(f"有意差検定: {label_a}（a） vs {label_b}（b）")
    result = evaluation.paired_bootstrap_model_comparison(
        test_a, pred_a, pred_b, n_bootstrap=n_bootstrap, random_state=random_state
    )
    result.attrs["label_a"] = label_a
    result.attrs["label_b"] = label_b
    return result


def save_comparison(df: pd.DataFrame, output_dir: Path = _OUTPUT_DIR) -> Path:
    """比較結果を CSV に保存し、保存先パスを返す。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"nar_data_volume_comparison_{timestamp}.csv"
    df.to_csv(path)
    return path
