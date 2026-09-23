# CLAUDE.md

会議の文字起こしからカードを抽出し、カードから議事録をレンダリングするキット。
**カードが唯一の真実で、議事録はその射影。**

**このファイルには、ここにしか無い規約だけを書く。** 型・フィールド・語彙・閾値の
正本は `ontology.yaml`、何を DEC とするかの正本は `decision-guide.md`、抽出の
各パスの手順と判定基準の正本は `.claude/skills/<名前>/SKILL.md`、本文の節構成の正本は
`templates/card/`。そちらにある
内容をここへ写さない（写した瞬間に多重管理とドリフトが始まる）。

---

## 3つの層

| 層 | 場所 | 誰が触るか |
|---|---|---|
| **不変層** | `projects/<slug>/meetings/*/transcript.md`、`meetings/*/logs/LOG-*.md` | 生成は Pass 1–2。**一度コミットしたら書き換えない。** PreToolUse フックが止める |
| **記録層** | `projects/<slug>/` のカード群 | 規約に従って作成・更新する |
| **設定層** | `ontology.yaml`、`.claude/skills/`、`templates/`、`decision-guide.md` | 人間が合意のうえで変える |
| **案件の設定** | `projects/<slug>/role-mapping.yaml` | 案件ごとに持つ。キットのルートにフォールバックしない |
| **生成物** | `projects/<slug>/views/*.md`、`schema.md` の `<!-- generated -->` ブロック | **手で編集しない。** 再生成で消える |

LOG を不変層に入れているのは、そこが**すべての引用の照合先**だから。
LOG を直せるなら「カードに合うように記録のほうを変える」ことができてしまい、
引用検証という唯一の機械的な真偽判定が意味を失う。

---

## 絶対に守る3つのルール

### 1. `なぜ` と却下理由を書かない

文字起こしを渡せば、もっともらしい理由はいくらでも合成できる。しかも一見正しいので
人間が通してしまう。**これがこの仕組みの最大の失敗モード。**

人間が実際に言った言葉だけを書く。書けない場合は `記録なし` を入れる。
**空欄は情報であり、埋めるべき穴ではない。**

対象: DEC の `なぜ` / `受容した不利` / `確認方法` / `作らない`、
`代替案[].却下理由`、ACT の `担当` / `期限`。

### 2. 迷ったら DEC ではなく Q に落とす

誤起票の害が非対称。嘘の DEC は半年後まで残るが、余分な Q は次回定例で消える。

- 決定権のない役割の発言だけでは DEC を起票しない（`role-mapping.yaml` を見る）
- 「前向きに検討します」「持ち帰ります」「調整します」は必ず Q

### 3. 承認ワークフローを足さない

リーダのレビューを必須にするとリーダがボトルネックになり、3週間で止まる。
矛盾検出が効き始めるまでは承認ゼロで回す。

---

## ID

`ID = ファイル名 = frontmatter の id` を三者一致させる。採番は型ごとの最大値+1。
**取り下げた番号は欠番のまま残し、再利用しない**（同じ ID が別のものを指すと、
過去の議事録が嘘になる）。`giji new` が採番する。

プロジェクト接頭辞は付けない。1案件1ディレクトリなので衝突しない。

---

## カードと会議は多対多

1枚の DEC / Q / ACT が複数の会議に現れるのは**正常**（会議をまたいで更新された
ということ）。逆に1つの会議からは何枚ものカードが生える。

だから**カードに `meeting` フィールドを持たせない。** 持たせると2回目の更新で
1つしか書けず、嘘になる。会議は `derived_from` の LOG を辿って得る
（`wiki.meetings_of(card)`）。

`初出` / `最終言及` は、この多対多を日付に射影したもの。

---

## スキル共通の規約

1. **閾値・語彙・フィールド一覧をスキルに書かない。** 正本は `ontology.yaml`。
   スキルは手順だけを持つ。
2. **各パスの責務を越えない。** Pass 3 は CON / ASM / TERM を作らない。
   Pass 4 はカードを作らない（候補を出すだけ）。
3. **Pass 3 は必ず1論点ずつ処理する。** 全論点を一度に渡すとコンテキストが伸び、
   逐語引用が要約され始める。引用が崩れると検証機構が死ぬ。
4. **人間の判断を代行しない。** 昇格の承認、`なぜ` の記入、ACT の担当・期限は
   人間が決める。`AskUserQuestion` で聞き、返ってきた言葉をそのまま書く。
5. **一意に決まるものはスキルに書かせない。道具にやらせる。**
   導出フィールド（`種別` / `所在` / `硬度` / `担当` / `会議体`）は `giji new`、
   範囲の問いは `giji scope-questions`、未知語の計数は `giji unknown-terms`、
   議事録の節構成は `giji minutes-input` が出す。
   **機械が書き、lint は保険として残す**（逆にすると、食い違いを直すのが人間の仕事になる）。
6. **非対話実行では、機械的に定まるものだけを反映してよい。**
   解釈を要するもの（`なぜ`、却下理由、昇格の可否、`範囲` の判定）は必ず対話で確認する。

---

## コマンド

```bash
sh tools/setup.sh [案件名]                     # 初回。門を立てて一度通す
python3 tools/giji.py                          # サブコマンド一覧
python3 tools/giji.py lint                     # 整合性検査（error 0 が不変条件）
python3 tools/giji.py verify-quotes --fix      # 引用不一致を「推測」に降格
python3 tools/giji.py scope-questions --meeting MTG-... [--write]  # 範囲の問いを定型で起票
python3 tools/giji.py unknown-terms --meeting MTG-...              # 未知語の候補を拾う
python3 tools/giji.py views                    # ビュー再生成
python3 tools/giji.py agenda                   # 次回アジェンダ
python3 tools/giji.py review --meeting MTG-...   # 確認②のチェックリスト
python3 tools/giji.py minutes-input --meeting MTG-... [--edition customer]
python3 tools/giji.py promote-input --meeting MTG-...
python3 tools/giji.py new decision --title "..." --from-log LOG-... --role 顧客PM --write
python3 tools/giji.py issue --act ACT-008 --repo owner/repo   # --create で起票
python3 tools/giji.py schema --check --check-samples --check-templates
python3 -m unittest discover -s tests
```

対象の案件は `.env` の `CURRENT_PROJECT`、または `--root` で指定する。

---

## warning 0 を目指さない

`act-overdue`、`q-stale`、`why-missing` は**真の未達を映す計器**であって、
消すものではない。warning を消すためにカードを書き換えるのは本末転倒。
**error 0 だけが不変条件。**

同じ理由で、引用一致率を品質指標にしない。あれはグラウンディングの健全性チェックで
あって、議事録の品質指標ではない。
