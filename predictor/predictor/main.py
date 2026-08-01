"""予想プログラムエントリーポイント"""

import logging
import os
import sys

sys.stdout.reconfigure(line_buffering=True)  # パイプ経由でも即時フラッシュ

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def _run_wf_fold(args: tuple) -> dict:
    """Walk-forward の1フォールドを実行するヘルパー（ProcessPoolExecutor 並列実行用）。"""
    fold_idx, wf_train, wf_test, half_life_days = args
    from predictor import calibration as _calib_mod
    from predictor import evaluation
    from predictor import model as _model

    wf_models = _model.train(wf_train, half_life_days=half_life_days)
    wf_calibrated = _calib_mod.calibrate_models(wf_models, wf_test)
    wf_pred = _model.predict(wf_calibrated, wf_test)
    wf_metrics = evaluation.evaluate(wf_test, wf_pred)
    return {
        "fold": fold_idx,
        "train_rows": len(wf_train),
        "test_rows": len(wf_test),
        "test_start": wf_test["date"].min(),
        "test_end": wf_test["date"].max(),
        **wf_metrics,
    }


def train_mode(
    walkforward: bool = True,
    half_life_days: float | None = None,
    use_embeddings: bool = False,
    embedding_pca_dim: int | None = None,
) -> None:
    """学習モード: 全データを使ってモデルを学習し保存する。

    Parameters
    ----------
    half_life_days : float | None
        指定した場合、レース日付からの経過日数に応じた指数減衰サンプルウェイト
        （半減期＝指定日数）を適用して学習する。``None``（デフォルト）の場合は
        従来どおり重みなしで学習する。
    use_embeddings : bool
        True の場合、学習済み Embedding（``python -m predictor.main
        train-embeddings`` で事前学習・保存したもの）を特徴量に追加する。
        Embedding は Walk-forward 検証には適用しない（学習期間の重なりによる
        情報リークを避けるため）。
    embedding_pca_dim : int | None
        指定した場合、Embedding を PCA でこの次元数に圧縮してから使用する。
    """
    from predictor.preprocessing import (
        compute_recent_stats,
        load_data,
        load_payoffs,
        preprocess,
        split_by_date,
    )

    logger.info("データを読み込み中...")
    raw = load_data(DATABASE_URL)

    logger.info("前処理中...")
    df = preprocess(raw)

    logger.info("近走成績フィーチャーを計算中...")
    df = compute_recent_stats(df)

    logger.info("時系列分割中...")
    train_df, val_df, test_df = split_by_date(df)
    logger.info(
        f"  学習: {len(train_df):,} 行  バリデーション: {len(val_df):,} 行  テスト: {len(test_df):,} 行"
    )

    import pandas as pd

    from predictor import evaluation, model

    embedding_cols: list[str] | None = None
    if use_embeddings:
        from predictor import embedding_features

        logger.info("学習済み Embedding を読み込み中...")
        embeddings = embedding_features.load_embeddings()
        if embedding_pca_dim is not None:
            embeddings = embedding_features.apply_pca(embeddings, embedding_pca_dim)
        train_df, embedding_cols = embedding_features.add_embedding_features(
            train_df, embeddings
        )
        val_df, _ = embedding_features.add_embedding_features(val_df, embeddings)
        test_df, _ = embedding_features.add_embedding_features(test_df, embeddings)
        logger.info(f"  追加した Embedding 特徴量: {len(embedding_cols)} 列")

    if half_life_days is not None:
        logger.info(
            f"モデルを学習中...（時間減衰ウェイト: half_life_days={half_life_days:.0f}）"
        )
    else:
        logger.info("モデルを学習中...")
    models = model.train(
        train_df,
        half_life_days=half_life_days,
        embedding_feature_columns=embedding_cols,
    )

    logger.info("評価中（較正前）...")
    pred_df_raw = model.predict(models, test_df)
    metrics_raw = evaluation.evaluate(test_df, pred_df_raw)
    calib_raw = evaluation.calibration_curve(test_df, pred_df_raw)
    bias_raw = evaluation.analyze_calibration_bias(calib_raw)

    logger.info("確率較正中...")
    from predictor import calibration

    calibrated = calibration.calibrate_models(models, val_df)

    logger.info("評価中（較正後）...")
    pred_df = model.predict(calibrated, test_df)
    metrics = evaluation.evaluate(test_df, pred_df)
    calib_after = evaluation.calibration_curve(test_df, pred_df)
    bias_after = evaluation.analyze_calibration_bias(calib_after)

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

    logger.info("--- calibration curve 較正前後比較（単勝）---")
    cc_win_raw = calib_raw["win"][
        ["bin_center", "mean_pred", "actual_rate", "count"]
    ].copy()
    cc_win_after = calib_after["win"][["mean_pred", "actual_rate"]].rename(
        columns={"mean_pred": "mean_pred_after", "actual_rate": "actual_rate_after"}
    )
    cc_win_cmp = pd.concat(
        [cc_win_raw.reset_index(drop=True), cc_win_after.reset_index(drop=True)], axis=1
    )
    logger.info(cc_win_cmp.to_string(index=False))

    logger.info("--- calibration curve 較正前後比較（複勝）---")
    cc_place_raw = calib_raw["place"][
        ["bin_center", "mean_pred", "actual_rate", "count"]
    ].copy()
    cc_place_after = calib_after["place"][["mean_pred", "actual_rate"]].rename(
        columns={"mean_pred": "mean_pred_after", "actual_rate": "actual_rate_after"}
    )
    cc_place_cmp = pd.concat(
        [cc_place_raw.reset_index(drop=True), cc_place_after.reset_index(drop=True)],
        axis=1,
    )
    logger.info(cc_place_cmp.to_string(index=False))

    logger.info("--- 較正バイアス分析（較正前）---")
    for key, b in bias_raw.items():
        label = "単勝" if key == "win" else "複勝"
        logger.info(f"  {label}: {b['summary']}")

    logger.info("--- 較正バイアス分析（較正後）---")
    for key, b in bias_after.items():
        label = "単勝" if key == "win" else "複勝"
        logger.info(f"  {label}: {b['summary']}")

    breakdown = evaluation.evaluate_by_popularity(test_df, pred_df)
    logger.info("--- 人気帯別 ---")
    logger.info(breakdown["popularity_tier"].to_string())
    logger.info("--- オッズ帯別 ---")
    logger.info(breakdown["odds_tier"].to_string())

    grade_breakdown = evaluation.evaluate_by_grade(test_df, pred_df)
    logger.info("--- グレード別 ---")
    logger.info(grade_breakdown.to_string())

    ev_analysis = evaluation.ev_filter_analysis(test_df, pred_df)
    logger.info(
        "--- 期待値フィルタ別（EV閘値 × 人気帯: 回収率, EV基準: 確定オッズ race_results.odds）---"
    )
    if isinstance(ev_analysis.index, pd.MultiIndex):
        for metric in ["回収率", "推奨数", "的中率", "カバレッジ"]:
            if metric in ev_analysis.columns:
                logger.info(f"\n{metric}:")
                logger.info(ev_analysis[metric].unstack("人気帯").to_string())
    else:
        logger.info(ev_analysis.to_string())

    logger.info("--- 回収率 Bootstrap 信頼区間（EV閘値 × 人気帯, 95%CI）---")
    boot_ci = evaluation.ev_filter_bootstrap_ci(test_df, pred_df)
    if not boot_ci.empty:
        logger.info(boot_ci.to_string())

    # フェーズ2: MC 単勝確率バックテスト
    logger.info("MC 単勝確率を算出中（n_iter=10,000, seed=42）...")
    pred_df_mc = evaluation.compute_mc_win_probs(pred_df, rng_seed=42)
    mc_diff = evaluation.mc_win_prob_comparison(pred_df_mc)
    logger.info("--- MC 単勝確率 vs 直接 win_prob（サニティチェック）---")
    for k, v in mc_diff.items():
        logger.info(f"  {k}: {v:.6f}")

    mc_ev_analysis = evaluation.mc_ev_filter_analysis(test_df, pred_df_mc)
    logger.info(
        "--- 期待値フィルタ別（MC単勝確率使用, EV基準: mc_win_prob × race_results.odds）---"
    )
    if isinstance(mc_ev_analysis.index, pd.MultiIndex):
        for metric in ["回収率", "推奨数", "的中率", "カバレッジ"]:
            if metric in mc_ev_analysis.columns:
                logger.info(f"\n{metric}:")
                logger.info(mc_ev_analysis[metric].unstack("人気帯").to_string())
    else:
        logger.info(mc_ev_analysis.to_string())

    logger.info("払戻データを読み込み中...")
    test_race_ids = test_df["race_id"].unique().tolist()
    payoffs_df = load_payoffs(DATABASE_URL, test_race_ids)
    multi_bet = evaluation.multi_bet_recovery_analysis(test_df, pred_df, payoffs_df)
    logger.info("--- 券種別回収率（複勝・馬連・三連複, payoffs テーブル使用）---")
    if not multi_bet.empty:
        logger.info(multi_bet.to_string())
    else:
        logger.info("  払戻データなし（payoffs テーブルが空の可能性あり）")

    logger.info("--- EV閘値 × 人気帯 × 券種 グリッド回収率 ---")
    ev_multi = evaluation.ev_multi_bet_grid(test_df, pred_df, payoffs_df)
    if not ev_multi.empty:
        logger.info(ev_multi["回収率"].unstack("券種").to_string())
        logger.info("\n推奨数:")
        logger.info(ev_multi["推奨数"].unstack("券種").to_string())
    else:
        logger.info("  データなし")

    logger.info("--- 馬連 Bootstrap 信頼区間（EV閘値 × 人気帯, 95%CI）---")
    quinella_ci = evaluation.ev_quinella_bootstrap_ci(
        test_df, pred_df, payoffs_df, random_state=42
    )
    if not quinella_ci.empty:
        logger.info(quinella_ci.to_string())
    else:
        logger.info("  データなし")

    logger.info("--- キャリブレーションカーブ（単勝・較正後）---")
    logger.info(calib_after["win"].to_string(index=False))
    logger.info("--- キャリブレーションカーブ（複勝・較正後）---")
    logger.info(calib_after["place"].to_string(index=False))

    if walkforward:
        logger.info("--- Walk-forward（rolling）検証 ---")
        from concurrent.futures import ProcessPoolExecutor

        from predictor.preprocessing import walk_forward_splits

        wf_splits = walk_forward_splits(df, n_splits=5)
        fold_args = [
            (fold_idx, wf_train, wf_test, half_life_days)
            for fold_idx, (wf_train, wf_test) in enumerate(wf_splits, start=1)
        ]
        n_workers = min(len(fold_args), os.cpu_count() or 1)
        logger.info(
            f"  {len(fold_args)} フォールドを並列実行中 (workers={n_workers})..."
        )
        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            fold_results = list(executor.map(_run_wf_fold, fold_args))
        fold_results.sort(key=lambda x: x["fold"])
        for r in fold_results:
            logger.info(
                f"  フォールド {r['fold']}/{len(wf_splits)}: "
                f"学習 {r['train_rows']:,} 行  "
                f"テスト {r['test_rows']:,} 行  "
                f"({r['test_start']} 〜 {r['test_end']})"
            )

        wf_summary = evaluation.walk_forward_summary(fold_results)
        logger.info(wf_summary.to_string())

    logger.info("モデルを保存中...")
    version_dir = model.save_models(models)
    model.save_calibrated_models(calibrated, version_dir)
    logger.info(f"完了 ({version_dir.name})")


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

    logger.info(f"レース {race_id} の予測を開始...")

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

    raw = load_predict_data(DATABASE_URL, race_id)
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
        raw = load_predict_data(DATABASE_URL, race_id)

    df = preprocess(raw, keep_null_position=True)

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
        models = model.load_calibrated_models()
    except FileNotFoundError:
        models = model.load_models()
    pred_df = model.predict(models, target)

    output.print_prediction(pred_df)
    output.save_output(
        pred_df,
        race_id,
        race_name=_race_name,
        race_number=_race_number,
        date=_race_date,
    )


def tune_mode(n_trials: int = 30) -> None:
    """Optuna で LightGBM パラメータと half_life_days を最適化する。"""
    from predictor import tuning
    from predictor.preprocessing import compute_recent_stats, load_data, preprocess

    logger.info("データを読み込み中...")
    raw = load_data(DATABASE_URL)
    df = preprocess(raw)

    logger.info("近走成績フィーチャーを計算中...")
    df = compute_recent_stats(df)

    logger.info(f"Optuna チューニングを実行中...（n_trials={n_trials}）")
    study = tuning.run_tuning(df, n_trials=n_trials)

    logger.info("--- 最良パラメータ ---")
    for k, v in study.best_params.items():
        logger.info(f"  {k}: {v}")
    logger.info(f"最良スコア（walk-forward平均win_logloss）: {study.best_value:.4f}")
    logger.info(
        "  （参考）対応する回収率: "
        f"{study.best_trial.user_attrs['recovery_rate']:.4f}"
    )

    logger.info("--- 上位トライアル（win_logloss順、参考の回収率つき） ---")
    for t in tuning.top_trials(study, n=5):
        logger.info(
            f"  #{t['number']}: win_logloss={t['win_logloss']:.4f}, "
            f"recovery_rate={t['recovery_rate']:.4f}, params={t['params']}"
        )


def compare_half_life_mode() -> None:
    """half_life_days の比較実験を実行し、結果を CSV に保存する。"""
    from predictor import half_life_experiment
    from predictor.preprocessing import (
        compute_recent_stats,
        load_data,
        preprocess,
        split_by_date,
    )

    logger.info("データを読み込み中...")
    raw = load_data(DATABASE_URL)
    df = preprocess(raw)

    logger.info("近走成績フィーチャーを計算中...")
    df = compute_recent_stats(df)

    logger.info("時系列分割中...")
    train_df, val_df, test_df = split_by_date(df)

    logger.info("half_life_days 比較実験を実行中...")
    result = half_life_experiment.run_comparison(train_df, val_df, test_df)

    logger.info("--- half_life_days 比較結果 ---")
    logger.info(result.to_string())

    path = half_life_experiment.save_comparison(result)
    logger.info(f"結果を保存しました: {path}")


def train_embeddings_mode() -> None:
    """騎手ID・調教師ID・血統IDの Embedding を PyTorch で学習し保存する。

    val/test への情報リークを避けるため、時系列分割の train 部分のみで学習する。
    """
    from predictor import embedding
    from predictor.preprocessing import load_data, preprocess, split_by_date

    logger.info("データを読み込み中...")
    raw = load_data(DATABASE_URL)
    df = preprocess(raw)

    logger.info("時系列分割中（Embedding は train 部分のみで学習しリークを防ぐ）...")
    train_df, _val_df, _test_df = split_by_date(df)
    logger.info(f"  Embedding 学習データ: {len(train_df):,} 行")

    logger.info("Embedding を学習中...")
    embeddings = embedding.train_embeddings(train_df)

    version_dir = embedding.save_embeddings(embeddings)
    logger.info(f"完了 ({version_dir.name})")


def similar_embeddings_mode(category: str, id_value: str, top_n: int = 10) -> None:
    """学習済み Embedding から、指定 ID にコサイン類似度が近い上位 N 件を表示する。"""
    from predictor import embedding_features

    logger.info(f"学習済み Embedding を読み込み中...（category={category}）")
    embeddings = embedding_features.load_embeddings()
    if category not in embeddings:
        logger.error(f"不明なカテゴリ: {category}（選択肢: {list(embeddings.keys())}）")
        sys.exit(1)

    table = embeddings[category]
    if id_value not in table:
        logger.error(f"ID が見つかりません: {id_value}")
        sys.exit(1)

    import numpy as np

    target = table[id_value]
    target_norm = target / np.linalg.norm(target)

    similarities = []
    for other_id, vec in table.items():
        if other_id in (id_value, "__mean__"):
            continue
        vec_norm = vec / np.linalg.norm(vec)
        similarities.append((other_id, float(np.dot(target_norm, vec_norm))))

    similarities.sort(key=lambda x: x[1], reverse=True)

    logger.info(
        f"--- {id_value} にコサイン類似度が近い上位 {top_n} 件（category={category}）---"
    )
    for other_id, sim in similarities[:top_n]:
        logger.info(f"  {other_id}: {sim:.4f}")


def _parse_half_life_days(argv: list[str]) -> float | None:
    """``--half-life-days N`` を argv から取り出す（未指定なら None）。"""
    if "--half-life-days" not in argv:
        return None
    idx = argv.index("--half-life-days")
    try:
        return float(argv[idx + 1])
    except (IndexError, ValueError):
        logger.error(
            "--half-life-days には数値を指定してください（例: --half-life-days 1095）"
        )
        sys.exit(1)


def main() -> None:
    if len(sys.argv) < 2:
        logger.error(
            "使い方: python -m predictor.main "
            "train [--no-walkforward] [--half-life-days N] "
            "[--use-embeddings] [--embedding-pca-dim N] "
            "| predict <race_id> | tune [--n-trials N] | compare-half-life "
            "| train-embeddings | similar-embeddings <category> <id> [--top-n N]"
        )
        sys.exit(1)

    command = sys.argv[1]

    if command == "train":
        walkforward = "--no-walkforward" not in sys.argv
        half_life_days = _parse_half_life_days(sys.argv)
        use_embeddings = "--use-embeddings" in sys.argv
        embedding_pca_dim = None
        if "--embedding-pca-dim" in sys.argv:
            idx = sys.argv.index("--embedding-pca-dim")
            embedding_pca_dim = int(sys.argv[idx + 1])
        train_mode(
            walkforward=walkforward,
            half_life_days=half_life_days,
            use_embeddings=use_embeddings,
            embedding_pca_dim=embedding_pca_dim,
        )
    elif command == "predict":
        if len(sys.argv) < 3:
            logger.error("使い方: python -m predictor.main predict <race_id>")
            sys.exit(1)
        predict_mode(sys.argv[2])
    elif command == "tune":
        n_trials = 30
        if "--n-trials" in sys.argv:
            idx = sys.argv.index("--n-trials")
            n_trials = int(sys.argv[idx + 1])
        tune_mode(n_trials=n_trials)
    elif command == "compare-half-life":
        compare_half_life_mode()
    elif command == "train-embeddings":
        train_embeddings_mode()
    elif command == "similar-embeddings":
        if len(sys.argv) < 4:
            logger.error(
                "使い方: python -m predictor.main "
                "similar-embeddings <category> <id> [--top-n N]"
            )
            sys.exit(1)
        top_n = 10
        if "--top-n" in sys.argv:
            idx = sys.argv.index("--top-n")
            top_n = int(sys.argv[idx + 1])
        similar_embeddings_mode(sys.argv[2], sys.argv[3], top_n=top_n)
    else:
        logger.error(f"不明なコマンド: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
