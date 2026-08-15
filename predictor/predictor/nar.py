"""地方競馬（南関東4場）予想プログラム エントリーポイント

`main.py`（中央競馬用）と並走する別パイプライン。中央競馬モデルとは学習データ・
モデル保存先・出力先を分離する（docs/plan/regional-racing-model.md 参照）。

対象venue: 浦和・船橋・大井・川崎（`preprocessing.NAR_VENUES`）。帯広(ば)＝ばんえい競走は
別競技のため対象外。

v1スコープ: `class_level`/`class_change`/`grade` はNAR表記に対応した抽出ロジックが
まだ無いため特徴量から除外する（`docs/todo.md` にフォローアップを記録済み）。
回収率・Log Lossのチューニングはこのモジュールのスコープ外。パイプラインが最後まで
完走し、モデル保存・予測出力ができることを最小のゴールとする。
"""

import logging
import os
import sys

sys.stdout.reconfigure(line_buffering=True)

from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

_MODEL_DIR_REGIONAL = Path(__file__).parent.parent / "models_regional"
_OUTPUT_DIR_REGIONAL = Path("output/regional")

# NARのclass_level/class_change/gradeはJRA表記専用の抽出ロジックに依存しており、
# NARデータでは常にNaN/空になる（実害はないが特徴量重要度が汚れるため明示的に除外する）。
_NAR_EXCLUDED_FEATURE_COLUMNS = ["class_level", "class_change", "grade"]


def train_mode(
    walkforward: bool = True,
    half_life_days: float | None = 1095.0,
    tuned_params: dict | None = None,
) -> None:
    """学習モード: 南関東4場の全データを使ってモデルを学習し保存する。"""
    from predictor.preprocessing import (
        NAR_VENUES,
        compute_recent_stats,
        load_data,
        load_payoffs,
        preprocess,
        split_by_date,
    )

    logger.info("データを読み込み中...（対象venue: %s）", NAR_VENUES)
    raw = load_data(DATABASE_URL, venues=NAR_VENUES)

    logger.info("前処理中...")
    df = preprocess(raw)
    df = df.drop(columns=_NAR_EXCLUDED_FEATURE_COLUMNS, errors="ignore")

    logger.info("近走成績フィーチャーを計算中...")
    df = compute_recent_stats(df)

    logger.info("時系列分割中...")
    train_df, val_df, test_df = split_by_date(df)
    logger.info(
        f"  学習: {len(train_df):,} 行  バリデーション: {len(val_df):,} 行  テスト: {len(test_df):,} 行"
    )

    import pandas as pd

    from predictor import evaluation, model

    if half_life_days is not None:
        logger.info(
            f"モデルを学習中...（時間減衰ウェイト: half_life_days={half_life_days:.0f}）"
        )
    else:
        logger.info("モデルを学習中...")
    models = model.train(
        train_df,
        half_life_days=half_life_days,
        win_params=tuned_params,
        place_params=tuned_params,
    )

    logger.info("評価中（較正前）...")
    pred_df_raw = model.predict(models, test_df)
    metrics_raw = evaluation.evaluate(test_df, pred_df_raw)

    logger.info("確率較正中...")
    from predictor import calibration

    calibrated = calibration.calibrate_models(models, val_df)

    logger.info("評価中（較正後）...")
    pred_df = model.predict(calibrated, test_df)
    metrics = evaluation.evaluate(test_df, pred_df)

    logger.info("--- 評価結果 ---")
    for k, v in metrics.items():
        logger.info(f"  {k}: {v:.4f}")

    logger.info("--- Brier score 較正前後比較 ---")
    for key in ("win_brier", "place_brier"):
        before = metrics_raw[key]
        after = metrics[key]
        diff = after - before
        arrow = "↓改善" if diff < 0 else "↑悪化"
        logger.info(
            f"  {key}: 較正前 {before:.4f} → 較正後 {after:.4f}  ({diff:+.4f} {arrow})"
        )

    breakdown = evaluation.evaluate_by_popularity(test_df, pred_df)
    logger.info("--- 人気帯別 ---")
    logger.info(breakdown["popularity_tier"].to_string())
    logger.info("--- オッズ帯別 ---")
    logger.info(breakdown["odds_tier"].to_string())
    # grade は南関東4場では常に空文字（NAR向けのgrade抽出は未実装）のため
    # evaluate_by_grade は意味を持たず呼ばない。

    ev_analysis = evaluation.ev_filter_analysis(test_df, pred_df)
    logger.info(
        "--- 期待値フィルタ別（EV閾値 × 人気帯: 回収率, EV基準: 確定オッズ race_results.odds）---"
    )
    if isinstance(ev_analysis.index, pd.MultiIndex):
        for metric in ["回収率", "推奨数", "的中率", "カバレッジ"]:
            if metric in ev_analysis.columns:
                logger.info(f"\n{metric}:")
                logger.info(ev_analysis[metric].unstack("人気帯").to_string())
    else:
        logger.info(ev_analysis.to_string())

    logger.info("--- 回収率 Bootstrap 信頼区間（EV閾値 × 人気帯, 95%CI）---")
    boot_ci = evaluation.ev_filter_bootstrap_ci(test_df, pred_df)
    if not boot_ci.empty:
        logger.info(boot_ci.to_string())

    logger.info("払戻データを読み込み中...")
    test_race_ids = test_df["race_id"].unique().tolist()
    payoffs_df = load_payoffs(DATABASE_URL, test_race_ids)
    multi_bet = evaluation.multi_bet_recovery_analysis(test_df, pred_df, payoffs_df)
    logger.info("--- 券種別回収率（複勝・馬連・三連複, payoffs テーブル使用）---")
    if not multi_bet.empty:
        logger.info(multi_bet.to_string())
    else:
        logger.info("  払戻データなし（payoffs テーブルが空の可能性あり）")

    if walkforward:
        logger.info("--- Walk-forward（rolling）検証 ---")
        from predictor.preprocessing import walk_forward_splits

        wf_splits = walk_forward_splits(df, n_splits=5)
        for fold_idx, (wf_train, wf_test) in enumerate(wf_splits, start=1):
            wf_models = model.train(
                wf_train,
                half_life_days=half_life_days,
                win_params=tuned_params,
                place_params=tuned_params,
            )
            wf_calibrated = calibration.calibrate_models(wf_models, wf_test)
            wf_pred = model.predict(wf_calibrated, wf_test)
            wf_metrics = evaluation.evaluate(wf_test, wf_pred)
            logger.info(
                f"  フォールド {fold_idx}/{len(wf_splits)}: "
                f"学習 {len(wf_train):,} 行  テスト {len(wf_test):,} 行  "
                f"win_logloss={wf_metrics['win_logloss']:.4f}  "
                f"recovery_rate={wf_metrics['recovery_rate']:.4f}"
            )

    logger.info("モデルを保存中...")
    version_dir = model.save_models(models, model_dir=_MODEL_DIR_REGIONAL)
    model.save_calibrated_models(calibrated, version_dir)
    logger.info(f"完了 ({version_dir.name})")


def predict_mode(race_id: str) -> None:
    """予測モード: 指定レースの予測を行い出力する。"""
    from predictor import model, output
    from predictor.preprocessing import NAR_VENUES, load_predict_data, preprocess

    logger.info(f"レース {race_id} の予測を開始...（地方競馬モデル）")

    import subprocess

    logger.info(f"レース {race_id} の最新出馬表を取得中...")
    result = subprocess.run(
        [sys.executable, "-m", "scraper.main", "shutuba", race_id],
        cwd=None,
    )
    if result.returncode != 0:
        logger.warning(
            f"警告: レース {race_id} の出馬表取得に失敗しました。DB の既存データで続行します。"
        )

    raw = load_predict_data(DATABASE_URL, race_id, venues=NAR_VENUES)
    if raw.empty:
        logger.error(f"レース {race_id} の出走馬データが見つかりません")
        sys.exit(1)

    logger.info(f"レース {race_id} の最新オッズを取得中...")
    result = subprocess.run(
        [sys.executable, "-m", "scraper.main", "odds", race_id],
        cwd=None,
    )
    if result.returncode != 0:
        logger.warning(
            f"警告: レース {race_id} の最新オッズ取得に失敗しました。DB の既存オッズで予測を続行します。"
        )
    else:
        raw = load_predict_data(DATABASE_URL, race_id, venues=NAR_VENUES)

    df = preprocess(raw, keep_null_position=True)
    df = df.drop(columns=_NAR_EXCLUDED_FEATURE_COLUMNS, errors="ignore")

    _raw_row = raw.iloc[0]
    _race_name = (
        str(_raw_row["race_name"])
        if "race_name" in raw.columns and _raw_row["race_name"] is not None
        else None
    )
    _race_number = (
        str(_raw_row["race_number"])
        if "race_number" in raw.columns and _raw_row["race_number"] is not None
        else None
    )
    _race_date = (
        str(_raw_row["date"])
        if "date" in raw.columns and _raw_row["date"] is not None
        else None
    )

    target = df[(df["race_id"] == race_id) & df["finishing_position"].isna()]
    if target.empty:
        logger.error(f"レース {race_id} の予測対象行が見つかりません")
        sys.exit(1)

    try:
        models = model.load_calibrated_models(model_dir=_MODEL_DIR_REGIONAL)
    except FileNotFoundError:
        models = model.load_models(model_dir=_MODEL_DIR_REGIONAL)
    pred_df = model.predict(models, target)

    output.print_prediction(pred_df)
    logger.warning(
        "注意: 単勝/複勝の推奨閾値（output.STRATEGIES）は中央競馬データでの"
        "bootstrap CI検証に基づく値をそのまま使っています。地方競馬での妥当性は未検証のため、"
        "参考表示にとどめてください。"
    )
    output.save_output(
        pred_df,
        race_id,
        race_name=_race_name,
        race_number=_race_number,
        date=_race_date,
        output_dir=_OUTPUT_DIR_REGIONAL,
    )


def main() -> None:
    if len(sys.argv) < 2:
        logger.error(
            "使い方: python -m predictor.nar "
            "train [--no-walkforward] [--half-life-days N|none] "
            "| predict <race_id>"
        )
        sys.exit(1)

    command = sys.argv[1]

    if command == "train":
        walkforward = "--no-walkforward" not in sys.argv
        half_life_days = 1095.0
        if "--half-life-days" in sys.argv:
            idx = sys.argv.index("--half-life-days")
            value = sys.argv[idx + 1]
            half_life_days = None if value.lower() == "none" else float(value)
        train_mode(walkforward=walkforward, half_life_days=half_life_days)
    elif command == "predict":
        if len(sys.argv) < 3:
            logger.error("使い方: python -m predictor.nar predict <race_id>")
            sys.exit(1)
        predict_mode(sys.argv[2])
    else:
        logger.error(f"不明なコマンド: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
