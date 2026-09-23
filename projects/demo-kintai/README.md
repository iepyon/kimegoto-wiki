# 勤怠・経費システム改修（C社 / 検証用の架空案件）

**この案件のデータはすべて架空です。** 議題（AGD）を含めてキットを端から端まで通すために、
`templates/project` から新規に起こした検証用の案件です。実在の顧客・案件とは関係がありません。

- 顧客: C社 ／ 自社: D社 ／ 会議体: 定例WG（隔週）
- 会議3本（`MTG-20260826` / `MTG-20260909` / `MTG-20260923`）
- 通した記録と、そこで見つかった問題は `docs/dryrun-20260923.md`
- 確認②（なぜ・範囲・担当期限・昇格・議題の締め）は人間が答えた言葉だけを書いた

規約はキットのルート（`CLAUDE.md` / `decision-guide.md` / `ontology.yaml`）に従う。

## 議題の流れ

| 議題 | 第1回 08/26 | 第2回 09/09 | 第3回 09/23 |
|---|---|---|---|
| AGD-001 経費精算の承認段数 | 扱った（DEC-001） | 扱った（DEC-004）→ 決着 | — |
| AGD-002 打刻の方式 | 扱ったが結論なし（Q-002） | 扱った（DEC-005、営業は保留） | 扱った（DEC-007）→ 決着 |
| AGD-003 旧システムの移行範囲 | 扱えず | 扱った（DEC-006） | 扱った → 決着（Q-005 は未決のまま） |
| AGD-004 締めの分割 | 会議中に起票・扱った | 扱ったが結論なし（Q-007） | 扱えず（開いたまま） |
| AGD-005 有給申請の取り込み | — | — | 起票して扱った（DEC-008）→ 決着 |

## ディレクトリ

```
meetings/MTG-YYYYMMDD/
    transcript.md              # 文字起こし原本（不変層・保管のみ）
    segments.yaml              # Pass 1 の出力（議題の紐づけを含む）
    logs/LOG-YYYYMMDD-NN.md    # 不変層・すべての引用の照合先
    unknown-terms.yaml         # Pass 2 の出力
    extraction-notes.yaml      # Pass 3 の欠落ガードの理由
    promote-candidates.yaml    # Pass 4 の出力
agenda/                            # 議題（DEC / Q / ACT の親）
decisions/ questions/ actions/     # フロー層
constraints/ assumptions/ terms/   # ストック層（昇格承認を経たものだけ）
views/                             # 生成物
```
