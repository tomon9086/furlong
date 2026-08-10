# ADR-0026: 通算出走数（career_starts_prior）は追加しない

- Status: Rejected
- Date: 2026-08-03

## Context

バッチ4の4案（[ADR-0025](./0025-batch4-candidates-rejected.md)）が全て不採用だった後、「成績ではなく経験値」という新しい軸として、その馬が当該レースより前に何戦してきたか（`groupby("horse_id").cumcount()`）を追加できないか検証した。比較対象は[ADR-0024](./0024-days-since-last-race-accepted.md)採用後のbaseline。

## Decision

不採用とする。

## Consequences

- Log Lossの変化は±0.0001でノイズレベル、win_accuracy -0.10pt、recovery_rate -0.58ptとともに悪化。[ADR-0025](./0025-batch4-candidates-rejected.md)と同じパターン。
- 既存の `age`・近走成績系フィーチャーと組み合わせれば同等の情報がすでにモデルから引き出せていた可能性。
