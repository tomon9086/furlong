"""予想プログラムエントリーポイント"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]


def train_mode() -> None:
    """学習モード: 全データを使ってモデルを学習し保存する。"""
    import pandas as pd

    from predictor import evaluation, model
    from predictor.preprocessing import (
        compute_recent_stats,
        load_data,
        preprocess,
        split_by_date,
    )

    print("データを読み込み中...")
    raw = load_data(DATABASE_URL)

    print("前処理中...")
    df = preprocess(raw)

    print("近走成績フィーチャーを計算中...")
    df = compute_recent_stats(df)

    print("時系列分割中...")
    train_df, test_df = split_by_date(df)
    print(f"  学習: {len(train_df):,} 行  テスト: {len(test_df):,} 行")

    print("モデルを学習中...")
    models = model.train(train_df)

    print("評価中（較正前）...")
    pred_df_raw = model.predict(models, test_df)
    metrics_raw = evaluation.evaluate(test_df, pred_df_raw)
    calib_raw = evaluation.calibration_curve(test_df, pred_df_raw)
    bias_raw = evaluation.analyze_calibration_bias(calib_raw)

    print("確率較正中...")
    from predictor import calibration

    calibrated = calibration.calibrate_models(models, test_df)

    print("評価中（較正後）...")
    pred_df = model.predict(calibrated, test_df)
    metrics = evaluation.evaluate(test_df, pred_df)
    calib_after = evaluation.calibration_curve(test_df, pred_df)
    bias_after = evaluation.analyze_calibration_bias(calib_after)

    print("--- 評価結果 ---")
    for k, v in metrics.items():
        print(f"  {k}: {v:.4f}")

    print("--- Brier score 較正前後比較 ---")
    for key in ("win_brier", "place_brier"):
        before = metrics_raw[key]
        after = metrics[key]
        diff = after - before
        arrow = "↓改善" if diff < 0 else "↑悪化"
        print(f"  {key}: 較正前 {before:.4f} → 較正後 {after:.4f}  ({diff:+.4f} {arrow})")

    print("--- calibration curve 較正前後比較（単勝）---")
    cc_win_raw = calib_raw["win"][["bin_center", "mean_pred", "actual_rate", "count"]].copy()
    cc_win_after = calib_after["win"][["mean_pred", "actual_rate"]].rename(
        columns={"mean_pred": "mean_pred_after", "actual_rate": "actual_rate_after"}
    )
    cc_win_cmp = pd.concat([cc_win_raw.reset_index(drop=True), cc_win_after.reset_index(drop=True)], axis=1)
    print(cc_win_cmp.to_string(index=False))

    print("--- calibration curve 較正前後比較（複勝）---")
    cc_place_raw = calib_raw["place"][["bin_center", "mean_pred", "actual_rate", "count"]].copy()
    cc_place_after = calib_after["place"][["mean_pred", "actual_rate"]].rename(
        columns={"mean_pred": "mean_pred_after", "actual_rate": "actual_rate_after"}
    )
    cc_place_cmp = pd.concat([cc_place_raw.reset_index(drop=True), cc_place_after.reset_index(drop=True)], axis=1)
    print(cc_place_cmp.to_string(index=False))

    print("--- 較正バイアス分析（較正前）---")
    for key, b in bias_raw.items():
        label = "単勝" if key == "win" else "複勝"
        print(f"  {label}: {b['summary']}")

    print("--- 較正バイアス分析（較正後）---")
    for key, b in bias_after.items():
        label = "単勝" if key == "win" else "複勝"
        print(f"  {label}: {b['summary']}")

    breakdown = evaluation.evaluate_by_popularity(test_df, pred_df)
    print("--- 人気帯別 ---")
    print(breakdown["popularity_tier"].to_string())
    print("--- オッズ帯別 ---")
    print(breakdown["odds_tier"].to_string())

    grade_breakdown = evaluation.evaluate_by_grade(test_df, pred_df)
    print("--- グレード別 ---")
    print(grade_breakdown.to_string())

    ev_analysis = evaluation.ev_filter_analysis(test_df, pred_df)
    print("--- 期待値フィルタ別（EV基準: 確定オッズ race_results.odds）---")
    print(ev_analysis.to_string())

    print("--- キャリブレーションカーブ（単勝・較正後）---")
    print(calib_after["win"].to_string(index=False))
    print("--- キャリブレーションカーブ（複勝・較正後）---")
    print(calib_after["place"].to_string(index=False))

    print("モデルを保存中...")
    version_dir = model.save_models(models)
    model.save_calibrated_models(calibrated, version_dir)
    print(f"完了 ({version_dir.name})")


def predict_mode(race_id: str) -> None:
    """予測モード: 指定レースの予測を行い出力する。

    finishing_position IS NULL の出走馬データと各馬の過去成績のみを取得し、
    全データロードを行わない。
    """
    from predictor import model, output
    from predictor.preprocessing import (
        load_predict_data,
        preprocess,
    )

    print(f"レース {race_id} の予測を開始...")
    raw = load_predict_data(DATABASE_URL, race_id)
    if raw.empty:
        print(f"レース {race_id} の出走馬データが見つかりません")
        answer = input("出馬表を取得しますか？ Y/n: ").strip().lower()
        if answer in ("", "y"):
            import subprocess

            result = subprocess.run(
                [sys.executable, "-m", "scraper.main", "shutuba", race_id],
                cwd=None,
            )
            if result.returncode != 0:
                print("出馬表の取得に失敗しました", file=sys.stderr)
                sys.exit(1)
            raw = load_predict_data(DATABASE_URL, race_id)
            if raw.empty:
                print(
                    f"レース {race_id} の出走馬データが見つかりません", file=sys.stderr
                )
                sys.exit(1)
        else:
            sys.exit(1)

    df = preprocess(raw, keep_null_position=True)

    target = df[(df["race_id"] == race_id) & df["finishing_position"].isna()]
    if target.empty:
        print(f"レース {race_id} の予測対象行が見つかりません", file=sys.stderr)
        sys.exit(1)

    try:
        models = model.load_calibrated_models()
    except FileNotFoundError:
        models = model.load_models()
    pred_df = model.predict(models, target)

    output.print_prediction(pred_df)
    output.save_csv(pred_df, race_id)


def main() -> None:
    if len(sys.argv) < 2:
        print("使い方: python -m predictor.main train | predict <race_id>")
        sys.exit(1)

    command = sys.argv[1]

    if command == "train":
        train_mode()
    elif command == "predict":
        if len(sys.argv) < 3:
            print("使い方: python -m predictor.main predict <race_id>")
            sys.exit(1)
        predict_mode(sys.argv[2])
    else:
        print(f"不明なコマンド: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
