# Obsidian 対応

**状態: A・B・C とも実装済み。**

| 案 | 状態 |
|---|---|
| A. ビューの ID をリンクにする | 実装済み（`gen_views._link`） |
| B. カードの参照フィールドをリンクで書く | 実装済み（`tools/links.py`、`kime links`、lint `ref-unlinked`） |
| C. 事故防止の設定を置く | 実装済み（`templates/obsidian/` を `setup.sh` が写す） |

GitHub 上で `[[ ]]` が素の文字として見えるのは許容する（決定済み）。

前提: **vault は案件ごと**（`projects/<slug>` を vault として開く）。案件をまたぐと
`DEC-001` が複数あり、`[[DEC-001]]` が曖昧になるため。

---

## 何がリンクになるか

| どこ | 書き方 | 例 |
|---|---|---|
| ビュー（`views/*.md`）のカード ID | `[[ID]]` | `\| [[DEC-001]] \| …` |
| カードの参照フィールド（`ontology.yaml` で ref / ref-list） | `"[[ID]]"`（クォート必須） | `議題: "[[AGD-001]]"`、`derived_from: ["[[LOG-20260826-01]]"]` |
| 会議（`meeting` / `予定会議`）、`segments.yaml` などの中間ファイル | 素の ID のまま | 会議はファイルではなくディレクトリで、リンク先が無い |

効くもの: バックリンクとグラフ。DEC → LOG（根拠）、DEC/Q/ACT → AGD（議題）、
CON/ASM → DEC（影響先）が線になる。CLAUDE.md の「リンクは片方向」はそのまま保たれ、
逆方向は Obsidian のバックリンクが `wiki.children_of` などの逆引きの役をする。

## 仕組み

- **読むときに剥がす。** `cards.parse_card` が `links.normalize` で素の ID に戻す。`wiki.*`・lint・
  議事録・アジェンダの材料は素の ID しか見ないので、顧客提出版に `[[ ]]` は漏れない
- **機械が書く。** `kime new`（`derive.py`）と `kime update` は参照をリンクで書く。
  `kime update --set 議題=AGD-001` のように素の ID で渡してもリンクにする
- **lint は保険。** 素の ID で書かれた参照は warning `ref-unlinked`。`kime links --fix` が
  値を変えずに書き直す（Pass 3 の後に `verify-quotes --fix` と並べて回す）。
  読みは両方の書式を受けるので error にはしない
- **LOG は触らない。** 不変層で、持つ参照も会議だけなので対象にならない
- Obsidian の Properties で編集すると配列がブロック形式（`  - "[[…]]"`）に書き直される。
  `kime update` はキーの下のブロックごと置き換えるので、取り残しは出ない
- クォートを忘れた `議題: [[AGD-001]]` は YAML では入れ子の配列になるが、読みで剥がす（lint は拾う）

---

## 共有の Obsidian 設定（C）

`.obsidian/` を gitignore している方針（個人設定を持ち込まない）は変えず、
`templates/obsidian/` に置いたものを `sh tools/setup.sh <案件名>` が
`projects/<案件名>/.obsidian/` へ写す。既に `.obsidian/` があれば触らない。

置く設定は事故防止のものに限る（いまは下表の1行目だけ）。

| 設定 | 値 | 理由 |
|---|---|---|
| ファイル名変更時に内部リンクを自動更新 | オフ | `ID = ファイル名 = id` の三者一致が崩れる。改名は ID の付け替えで、欠番規約に反する |
| 除外ファイル | 置かない | `views/` を除外すると検索・グラフでの二重表示は減るが、ビューからカードへのリンクの起点も見えにくくなる。個人で設定する |

---

## Obsidian から編集するときのリスク

- **不変層を守るのは pre-commit と CI だけになる。** PreToolUse フックは Claude Code の
  編集しか止めない。Obsidian で LOG や `transcript.md` を書き換えても、コミット時に門で止まる
  だけで、ファイル自体は変わってしまう。LOG を開いて Properties を触らない、を運用で伝える
- **Properties UI で編集すると frontmatter が書き直されることがある。**
  `代替案` のような入れ子のリストは Properties で扱えず、他の項目を UI で触ると
  直列化し直される可能性がある。`miniyaml` は知らない構文で例外を出す（フェイルクローズ）ので
  黙って壊れはしないが、lint の error として返ってくる。DEC はソース表示で編集するのが安全
- **ビューは手で編集しない**規約は Obsidian でも同じ。Stop フックは Claude Code のターン終わりにしか
  動かないので、Obsidian だけで作業した日は `kime views` を手で回す。素の ID で参照を書いたなら
  `kime links --fix` も
