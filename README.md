# kimegoto — 決め事を記録するキット

会議の文字起こしから、**決定事項（DEC）・未決事項（Q）・アクション（ACT）** をカードとして
抜き出し、そのカードから議事録と次回アジェンダを作る。
**カードが唯一の真実で、議事録はその射影。**

名前は「決め事（きめごと）」から。CLI は `kime`（`python3 tools/kime.py`）。

対象: 1チーム・1プロジェクト。2週に1回の定例会議。
人間の作業: 会議当日の確認 25分。

この README は使い方のチュートリアル。なぜこの形にしたのか、何を期待してよいか、
3ヶ月後に何を見るかは [`docs/design.md`](docs/design.md) にある。

---

## 1サイクルの流れ

```
 ① 会議の前   アジェンダを出す               「次回のアジェンダを出して」
      │
   （会議）
      │
 ② 会議の後   文字起こしを取り込む           transcript.md を置く
              → 論点に分ける（Pass 1）       「文字起こしを論点に分けて」
              → LOG にする（Pass 2）         「LOG を作って」
      │
 ③ 記録       DEC / Q / ACT を抽出（Pass 3） 「決定事項を抽出して」
      │
 ④ 確認       なぜ・担当・期限を人間が入れる  「25分の確認を始めて」
      │
 ⑤ 出力       議事録を出す                   「議事録を出して」
      └──────▶ 未決の Q と未完了の ACT が、次回の ① に戻ってくる
```

Claude Code に話し言葉で頼めば、対応するスキル（`.claude/skills/`）が動く。
スキルを直接呼ぶなら `/segment` `/log-cards` `/extract` `/review` `/minutes` `/lint` `/issue`。

以下の例は、同梱のデモ案件 `projects/demo-kb`（5回分の会議を記録済み）を使う。

---

## 0. 最初に一度だけ：セットアップ

```sh
sh tools/setup.sh demo-kb        # 門（pre-commit）を立て、.env に対象案件を書く
```

**これを飛ばすと `.githooks/pre-commit` は動かない。** clone しただけでは git は
`.githooks` を見に行かない。

自分の案件を始めるときは、雛形をコピーしてから同じコマンドを打つ。

```sh
cp -r templates/project projects/<案件名>
sh tools/setup.sh <案件名>
```

そのあと **`projects/<案件名>/role-mapping.yaml` を埋める**。話者の役割ラベル
（顧客PM、開発リーダなど）ごとに、社名・決定権・決定の種別を書く。
決定権の無い役割の発言だけでは DEC にならないので、ここが抽出の精度を決める。
何を DEC とするかの境界は [`decision-guide.md`](decision-guide.md) で、チームで先にすり合わせておく。

---

## ① 会議の前：アジェンダを出す

> 「次回のアジェンダを出して」「持ち越しを確認したい」「次の会議でこれを決めたい」

アジェンダは**議題（AGD）** を骨組みにした、カードの射影。決定・未決・アクションは
どれかの議題にぶら下がり、議題は決着するまで次回へ持ち越される。

```sh
python3 tools/kime.py agenda-input --meeting MTG-20260925   # 次の会議。まだ無くてよい
```

議題ごとに次の形で出る（例）。

```
## 議題

### AGD-003 帳票のPDF出力を今期に入れるかを決めたい
- 提起者: 顧客PM（2026-09-11）
- 状態: 継続（持ち越し：MTG-20260911 で扱ったが結論なし）
#### これまでの決定
（なし）
#### 未決の問い
##### Q-021 PDF出力の追加費用をどう扱うか
#### 未完了のアクション
- ACT-030 PDF出力の追加見積を提示する
```

- 冒頭は理由が未記入の決定。続いて未完了のアクション、議題、議題に紐づかない未決の問いが並ぶ
- **その場で決めたいことが出たら、アジェンダに書き足さずに議題を起票する**:

  ```sh
  python3 tools/kime.py new agenda --title "検索結果の画面にプレビューを出すかを決めたい" \
      --role 顧客PM --meeting MTG-20260925 --write
  ```

  文言は提起者の言葉のまま。議題を起票すれば次の `agenda-input` に載り、会議の後は
  Pass 1 で論点に結ばれて、そこから生えた決定・未決・アクションに `議題` が写る
- **結論が出なかった議題は、開いたまま次回へ持ち越す。** 議題そのものを未決の問い（Q）に
  言い換えない。Q になるのは「決めるのに足りないもの」（誰の何を待っているか）が発言に
  出たときだけ。予定したのに扱えなかった議題は「扱えず」と出る
- 扱った議題の `未着手 → 継続` と `予定会議` の追記は、Pass 1 の後に
  `kime agenda-sync --meeting MTG-... --write` が書き戻す
- 決着したかは確認②で人が決める（`kime review` の 2-5。`決着候補` の目安が出る）
- 機械的な一覧は `python3 tools/kime.py agenda`（`views/agenda-next.md`）。Stop フックが
  ターンの終わりに作り直すので、頼み忘れても最新版がある

---

## ② 会議の後：文字起こしを取り込む

### 置き場所と形式

`projects/<案件名>/meetings/MTG-YYYYMMDD/transcript.md` に置く。

```markdown
# MTG-20260925 定例WG（第6回）

- 日時: 2026-09-25 14:00-15:00
- 会議体: 定例WG
- 出席: 発注元, 顧客PM, 開発リーダ, 開発メンバー

---

[00:00:20] 顧客PM: 始めます。
[00:01:10] 開発リーダ: 宿題の見積ですが…
```

- 話者は**役割ラベル**で書き、`role-mapping.yaml` の key と表記を合わせる
- 音声認識の出力をチャットに貼って「この形式で取り込んで」と頼んでもよい
- **一度コミットした文字起こしと LOG は書き換えない。** すべての引用の照合先なので、
  PreToolUse フックが編集を止める

### 論点に分ける（Pass 1）

> 「MTG-20260925 の文字起こしを論点に分けて」

`segments.yaml` ができる。論点の粒度を**人間がここで確認する**（10行ほどなので安く直せる）。

```yaml
segments:
  - seq: 2
    title: 全社展開の想定規模
    種別: 議論
    時刻: "00:03:15 - 00:12:30"
```

### LOG にする（Pass 2）

> 「LOG を作って」

論点ごとに `logs/LOG-20260925-NN.md` ができる。発言は逐語のまま残し、言い換えない。
あわせて、用語集に無い言葉を `unknown-terms.yaml` に拾う。

---

## ③ 決定事項・未決事項・アクションを記録する（Pass 3）

> 「MTG-20260925 の Pass 3 を回して」「決定事項を抽出して」

論点を**1つずつ**処理して、3種類のカードを起こす。

| 型 | 置き場所 | 例 |
|---|---|---|
| **DEC** 決定事項 | `decisions/DEC-016.md` | 全社展開に向けた構成見直しは今回のスコープに含めない |
| **Q** 未決事項 | `questions/Q-NNN.md` | 「持ち帰ります」「前向きに検討します」と言われたもの |
| **ACT** アクション | `actions/ACT-014.md` | 図面PDF対応の追加見積を提示する |

このときの約束ごと:

- **`なぜ` と却下理由は、人が実際に言った言葉だけを書く。** 無ければ `記録なし`。
  もっともらしい理由の合成が、この仕組みの最大の失敗モード
- **迷ったら DEC ではなく Q に落とす。** 嘘の DEC は半年残るが、余分な Q は次回定例で消える
- ACT の担当と期限は、発言に無ければ空欄のまま（空欄が正常な出力）
- カードには LOG からの逐語引用を付ける。抽出のあとに照合する

```sh
python3 tools/kime.py scope-questions --meeting MTG-20260925 --write  # 範囲の問いを定型で起票
python3 tools/kime.py verify-quotes --fix   # 引用を LOG と照合し、不一致は「推測」に降格
python3 tools/kime.py lint                  # error 0 を確認
```

同じ DEC / Q / ACT が複数の会議に出てくるのは正常。新しいカードを作らず、既存のカードを更新する。

---

## ④ 確認する：空欄を人間が埋める（25分）

> 「25分の確認を始めて」「担当と期限を入れたい」

**会議当日か翌日に固定する。** 2週間空けると却下理由は思い出せない。
Claude が1件ずつ質問し、返ってきた言葉をそのままカードに書く。

```
DEC-016「全社展開に向けた構成見直しは今回のスコープに含めない」
  → なぜそう決めたか、会議で出た言葉はありますか？（なければ「記録なし」）
ACT-014「図面PDF対応の追加見積を提示する」
  → 担当と期限は？
```

| | 内容 | 目安 |
|---|---|---|
| 2-0 | `範囲: 判定保留` の DEC を見る（受託開発では最優先） | 3分 |
| 2-1 | 拾い漏れの疑い（`review_required`）と `信頼度: 推測` を確認 | 4分 |
| 2-2 | DEC の `なぜ` を1行書く／却下理由を埋められるなら埋める | 8分 |
| 2-3 | ACT の担当・期限を入れる／前回の ACT の状態を更新 | 4分 |
| 2-4 | 制約・前提・用語への昇格候補を yes/no で承認（Pass 4） | 6分 |

```sh
python3 tools/kime.py review --meeting MTG-20260925   # 該当するカードだけを上の順で並べる
```

`なぜ` を書かずに済ませてもよい。ただしその DEC は次回アジェンダの冒頭に載り続け、
制約・前提への昇格候補にもならない。

最後に「lint して」。**error 0 だけが不変条件。** `act-overdue` `q-stale` `why-missing`
などの warning は本当の未達を映す計器なので、消すためにカードを書き換えない。

---

## ⑤ 議事録を出す

> 「MTG-20260925 の議事録を出して」「顧客提出版がほしい」

```sh
python3 tools/kime.py minutes-input --meeting MTG-20260925                       # 社内版の材料
python3 tools/kime.py minutes-input --meeting MTG-20260925 --edition customer    # 顧客提出版の材料
```

- 議事録はカードから作る生成物で、**ファイルには保存しない**。直すならカードを直して出し直す
- 顧客提出版で出せない情報は CLI が機械的に落とす（`ontology.yaml` の `editions.customer`）

ACT を GitHub Issue にしたいときは「ACT-014 を Issue にして」
（`kime issue --act ACT-014 --repo owner/repo`、`--create` で起票。起票の前に必ず確認する）。

---

## コマンド早見表

`kime` は `python3 tools/kime.py`。対象の案件は `.env` の `CURRENT_PROJECT`、または `--root` で指定する。

| コマンド | 使う場面 |
|---|---|
| `kime agenda-input [--meeting MTG-...]` | ① 次回アジェンダの材料 |
| `kime new agenda --title "..." --role 顧客PM --meeting MTG-... --write` | ① 議題を起票する |
| `kime agenda-sync --meeting MTG-... --write` | ② Pass 1 の後、扱った議題を書き戻す |
| `kime agenda` | ① 次回アジェンダの一覧（ビュー） |
| `kime unknown-terms --meeting MTG-...` | ② 未知語の候補を拾う |
| `kime new decision --title "..." --from-log LOG-... --role 顧客PM --write` | ③ カードを起こす（採番つき） |
| `kime update <ID> --set k=v` | ③④ 既存カードを書き換える |
| `kime scope-questions --meeting MTG-... --write` | ③ 範囲の問いを起票 |
| `kime verify-quotes --fix` | ③ 引用の照合と降格 |
| `kime review --meeting MTG-...` | ④ 確認のチェックリスト |
| `kime promote-input --meeting MTG-...` | ④ 昇格候補の材料 |
| `kime minutes-input --meeting MTG-... [--edition customer]` | ⑤ 議事録の材料 |
| `kime confirm --meeting MTG-... --sent YYYY-MM-DD` | ⑤ みなし確定の期限を書き戻す |
| `kime issue --act ACT-NNN --repo owner/repo` | ⑤ Issue の下書き |
| `kime lint` | いつでも。error 0 が不変条件 |
| `kime views` | ビューの再生成（通常は Stop フックが行う） |
| `kime schema --check --check-samples --check-templates` | 設定層を変えたとき |
| `python3 -m unittest discover -s tests` | 道具を変えたとき |

各サブコマンドの詳細は `kime <サブコマンド> --help`。

---

## ファイルの地図

| 場所 | 内容 |
|---|---|
| `projects/<案件名>/` | 案件ごとのカード群と `role-mapping.yaml` |
| `projects/<案件名>/meetings/MTG-*/` | 文字起こし・論点・LOG（**不変層**） |
| `projects/<案件名>/views/` | 生成物。**手で編集しない** |
| `ontology.yaml` | 型・フィールド・語彙・閾値の唯一の正本 |
| `decision-guide.md` | 何を DEC とするかの判定ガイド。**最初に読む** |
| `schema.md` | カード定義・ID 規約（フィールド表は `ontology.yaml` から生成） |
| `templates/` | 案件とカードの雛形 |
| `.claude/skills/` | 各パスの手順と判定基準 |
| `CLAUDE.md` | 3つの層と、絶対に守る3つのルール |
| `docs/design.md` | 設計の根拠・期待値の較正・判定基準・既知の難所 |
| `docs/backlog.md` | やらないと決めたことと、その理由 |
| `research-notes.md` | 先行研究の調査（出典つき） |

案件ディレクトリに `.fixture` を置くと教材として、`.wip` を置くと作りかけとして自動検査から外れる。
作っている途中は error が出て当たり前なので、`.wip` を置いて作り、error 0 になってから外す。

門は `.githooks/pre-commit`（テスト・生成物の鮮度・lint・不変層の5段）と、
同じものを `--all` で呼ぶ CI（`.github/workflows/checks.yml`）の二重。

---

## 始める前にチームに言っておくこと

- **1〜3回目の結果は悪い。** 最初は用語の登録が主役で、DEC の抽出精度は低く出る。4回目あたりから逆転する
- **④ の25分を飛ばさない。** 飛ばすと捏造された記録ができる。払えない週は Pass 3 で止め、翌週まとめてやる
- 対象の会議は、自分が出る定例1本だけにする。増やさない
