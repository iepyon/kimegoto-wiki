# 社内ナレッジ検索基盤（A社 / 動作確認用の仮想案件）

**この案件のデータはすべて架空です。** キットを端から端まで通すために作った検証用の
案件で、実在の顧客・案件とは関係がありません。

- 顧客: A社 ／ 自社: B社 ／ 会議体: 定例WG（隔週）
- 会議5本（`MTG-20260717` 〜 `MTG-20260911`）
- 通した記録と、そこで見つかった問題は `docs/dryrun-20260918.md`

規約はキットのルート（`CLAUDE.md` / `decision-guide.md` / `ontology.yaml`）に従う。

## ディレクトリ

```
meetings/MTG-YYYYMMDD/
    transcript.md              # 文字起こし原本（不変層・保管のみ）
    segments.yaml              # Pass 1 の出力
    logs/LOG-YYYYMMDD-NN.md    # 不変層・すべての引用の照合先
    unknown-terms.yaml         # Pass 2 の出力
    promote-candidates.yaml    # Pass 4 の出力（承認後は破棄可）
decisions/ questions/ actions/     # フロー層
constraints/ assumptions/ terms/   # ストック層（昇格承認を経たものだけ）
views/                             # 生成物
```
