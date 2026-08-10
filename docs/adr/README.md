# ADR（Architecture Decision Record）

モデル・特徴量・ハイパーパラメータに関する採否判断を記録する。`docs/experiments.md` の実験ログのうち、判定（採用/不採用）が出たものだけをここに昇格させる。生の測定値グリッド・所感の詳細は記録しない（必要なら `git log -p docs/experiments.md` で過去版を参照できる）。

## ファイル命名

`NNNN-短い-スラッグ.md`（NNNN は4桁連番、時系列順）

## テンプレート

```markdown
# ADR-NNNN: タイトル

- Status: Accepted / Rejected / Superseded by ADR-NNNN
- Date: YYYY-MM-DD

## Context
何を、なぜ検討したか（2〜4文）。

## Decision
何を決定したか（1〜3文）。

## Consequences
- 採否の根拠になった指標の変化（要点のみ）
- 副作用・トレードオフ
- フォローアップ（あれば）
```

## 運用ルール

- 実験を行い判定が出たら ADR を1本作成する。生データ・グリッド表は不要（`train.log` や CSV 出力を参照する形でよい）。
- 過去の決定を覆す場合は新しい ADR を作り、旧 ADR の Status を `Superseded by ADR-NNNN` に書き換える（削除しない）。
- 判定に至らなかった探索的な計測（グリッドサーチの様子見など）は ADR 化しない。`docs/experiments.md` にも残さず、必要なら `git log` から辿る。
