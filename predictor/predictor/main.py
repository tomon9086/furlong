"""予想プログラムエントリーポイント"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]


def train_mode() -> None:
    """学習モード: 全データを使ってモデルを学習し保存する。"""
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

    print("評価中...")
    pred_df = model.predict(models, test_df)
    metrics = evaluation.evaluate(test_df, pred_df)
    print("--- 評価結果 ---")
    for k, v in metrics.items():
        print(f"  {k}: {v:.4f}")

    print("モデルを保存中...")
    version_dir = model.save_models(models)
    print(f"完了 ({version_dir.name})")


def predict_mode(race_id: str) -> None:
    """予測モード: 指定レースの予測を行い出力する。

    NOTE: 現在は全データをロードして対象レースを抽出する実装。
    パフォーマンス改善は SQL ウィンドウ関数による絞り込みで対応予定。
    """
    from predictor import model, output
    from predictor.preprocessing import (
        compute_recent_stats,
        load_data,
        preprocess,
    )

    print(f"レース {race_id} の予測を開始...")
    raw = load_data(DATABASE_URL)
    df = preprocess(raw)
    df = compute_recent_stats(df)

    target = df[df["race_id"] == race_id]
    if target.empty:
        print(f"レース {race_id} が見つかりません", file=sys.stderr)
        sys.exit(1)

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

