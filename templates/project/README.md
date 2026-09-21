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
    unknown-terms.yaml         # Pass 2 の出力（未知語リスト）
    extraction-notes.yaml      # Pass 3 の欠落ガードの理由
    promote-candidates.yaml    # Pass 4 の出力（承認後は破棄可）
decisions/ questions/ actions/     # フロー層
constraints/ assumptions/ terms/   # ストック層（昇格承認を経たものだけ）
views/                             # 生成物
```

## 文字起こしの書式

機械は `transcript.md` を読まない（正規化前なので引用の照合先にもしない）。
それでも **Pass 1 の入力としての最低限の約束**は要る。ここがぶれると、
`segments.yaml` の `時刻` も LOG の「確定した事実」の出典も安定しない。

```
# MTG-20260918 定例WG（第3回）

- 日時: 2026-09-18 14:00-14:52
- 会議体: 定例WG
- 出席: 顧客PM, 開発リーダ, 開発メンバー
- 話者分離: 役割ラベル付き自動出力（未修正）

---

[00:21:10] 顧客PM: えーと、ADに繋ぐのは、まあVPNが固定IPなんで厳しいですね
[00:21:44] (沈黙 約6秒)
```

- 話者は**役割ラベル**で書く（個人名にしない）。`role-mapping.yaml` の key と表記を揃える
- 各行の頭に `[HH:MM:SS]`。Pass 1 の論点の境界と、LOG の出典の粒度がこれで決まる
- 沈黙は `[HH:MM:SS] (沈黙 約N秒)`。**沈黙は却下のシグナルで、Pass 3 が読む**
- フィラーも言い直しもそのまま残す。削るのは Pass 2 の仕事

`transcript.md` と `logs/` は**一度コミットしたら書き換えない**。
LOG はすべての引用の照合先で、ここを直せると引用検証が意味を失う。
