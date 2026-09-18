# <案件名>

会議の記録。カードが唯一の真実で、議事録はその射影。

## 最初にやること

1. `role-mapping.yaml` を実際の役割ラベル・社名・会議体名で埋める
   - 話者分離が出力する役割ラベルを key にする（表記を合わせる）
   - 各役割の `決定権` と `決定の種別` が抽出の精度を決める
2. `decision-guide.md`（キットのルート）をチームで読み、境界例をすり合わせる
3. 既存の用語集があれば `terms/` に移す（`正式` だけでよい）

## ディレクトリ

```
meetings/MTG-YYYYMMDD/
    transcript.md              # 文字起こし原本（不変層・保管のみ）
    segments.yaml              # Pass 1 の出力
    logs/LOG-YYYYMMDD-NN.md    # 不変層・すべての引用の照合先
    promote-candidates.yaml    # Pass 4 の出力（承認後は破棄可）
decisions/ questions/ actions/     # フロー層
constraints/ assumptions/ terms/   # ストック層（昇格承認を経たものだけ）
views/                             # 生成物
```

`transcript.md` と `logs/` は**一度コミットしたら書き換えない**。
LOG はすべての引用の照合先で、ここを直せると引用検証が意味を失う。
