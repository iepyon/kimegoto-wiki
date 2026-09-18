# OpenSpec 連携（第2次・規約のみ）

**この文書に書かれた仕組みはまだ実装されていない。** 規約を先に確定させ、
実装は次期に回す。

---

## 位置づけ

```
LLM Wiki（カード） ──▶ OpenSpec ──▶ ソースコード ──▶ デプロイ
```

**一方通行。逆流させない。** 実装の都合を知見層に混ぜると、コードの寿命に
知見が引きずられる。OpenSpec 側の変更をカードへ反映する仕組みは作らない。

---

## 相手の実態

OpenSpec は Fission-AI/OpenSpec（MIT, `@fission-ai/openspec`）。
Thoughtworks Technology Radar Vol.34 (2026-04) で Tools / Assess。

```
openspec/
├── config.yaml                          # プロジェクト文脈（project.md ではない）
├── specs/<capability>/spec.md           # 現在の正
└── changes/<change-name>/
    ├── proposal.md                      # Why / What Changes / Capabilities / Impact
    ├── design.md
    ├── tasks.md                         # チェックボックスで進捗管理
    └── specs/<capability>/spec.md        # デルタ
```

spec の見出しは `## Purpose` / `## Requirements` / `### Requirement: <一文>` /
`#### Scenario: <題>`（本文は `- **WHEN** …` / `- **THEN** …`）。
デルタは `## ADDED / MODIFIED / REMOVED Requirements` で、
**MODIFIED は差分ではなく置換後の全文**を書く運用。

構造見出しと SHALL / MUST は英語のまま、本文は日本語、が既存プロジェクトの運用。

---

## `derived_from` は我々の自前規約

OpenSpec の README を確認した結果、**YAML フロントマターもトレーサビリティ欄も
存在しない**（"Plain Markdown — requirements with concrete scenarios, no special
syntax to learn"）。

したがって `derived_from: [DEC-014, CON-007]` は **OpenSpec の機能ではなく
我々の規約**であり、OpenSpec 側では検証されない。

- 置き場所は `proposal.md` の**冒頭行**（唯一の理由記述枠がそこ）
- 検証は我々の側で行う（下記）

---

## 生成するもの

`giji openspec --change <name>` が、指定した決定群から `proposal.md` の下書きを出す。

| OpenSpec の節 | 材料 |
|---|---|
| 冒頭行 | `derived_from: [DEC-NNN, CON-NNN]` |
| `## Why` | DEC の `なぜ` と `受容した不利`、CON の `内容` |
| `## What Changes` | DEC の `title` 群 |
| `## Impact` | 空（人間が書く） |

**`なぜ` が空欄の決定からは Why を書かない。** 空欄のまま出し、人間に埋めさせる。
ここで合成すると、この仕組みの意味が全部なくなる。

---

## 検証するもの

`giji openspec --check` が、我々の側だけで検査する。

| チェック | 別 | 内容 |
|---|---|---|
| `openspec-ref` | error | `derived_from` が指すカードが実在しない |
| `openspec-superseded` | error | `status: 覆された` の DEC を引いている proposal がある |
| `openspec-why` | warning | 引いている DEC の `なぜ` がすべて未記入 |

---

## やらないこと

### 未解決 Q の流し込み

GitHub Spec Kit の `[NEEDS CLARIFICATION]` マーカーは我々の Q と同一概念だが、
**OpenSpec にはこの受け口が無い**。`design.md` に「未解決の問い」節を自前で設ける
案はあるが、OpenSpec の構造を勝手に拡張することになるので採らない。

### 逆流

OpenSpec の change が archive に入ったことを検知して DEC の status を変える、
といった仕組みは作らない。一方通行を守る。

### CON の `種類: property` を constitution.md に置く

Spec Kit の `constitution.md` は「変わりにくい環境の事実」の置き場として適合するが、
OpenSpec には対応物が無い（`config.yaml` の `context` が近いが性質が違う）。
OpenSpec を使っている以上、この案は採れない。

---

## 指標

README の判定基準に「OpenSpec が `derived_from` で引いた DEC の数」が
上乗せ層の本命指標として置かれている。`views/metrics.md` はこれを出すが、
**第2次までは常に 0**。それでよい。
