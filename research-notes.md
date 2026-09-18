# 先行研究の調査と設計への反映

2026-09-18 時点。3方向（論証構造・会議理解NLP・実務の記録体系）を調査し、
採った指摘と採らなかった指摘を出典つきで記録する。

**この文書自体が、この仕組みの自己適用**である。採らなかった選択肢とその理由を残しておかないと、
半年後に「なぜ IBIS を使わなかったのか」が誰にも分からなくなる。

---

## 0. まず、我々の設計が既に踏めていたもの

偶然ではなく、同じ問題に当たった結果として一致していた。

| 我々の判断 | 対応する先行研究の結論 |
|---|---|
| カードが真実源、議事録はレンダリング | Shipman & Marshall (1999) が報告した IBIS 系の失敗要因そのものへの対処。itIBIS の事例では「**議事録を通常の散文形式に変換しないと外部グループが関与しなかった**」。我々は変換を自動化することで両立させている |
| 迷ったら DEC ではなく Q | 決定検出の精度が 0.43 という実測に対する正しい非対称設計（Fernández 2008） |
| 必須フィールドを作らない | Shipman の premature structure。MADR 4.0.0 も中核3項目以外すべて任意（"Feel free to remove any of them"） |
| 信頼度をフィールド単位に持つ | GRADE はアウトカムごとに確信度を評定し、問題があれば**格下げ**する。我々の「照合失敗→推測に自動降格」は同型 |
| Pass 2 → Pass 3 の二段構成 | Kirstein ら (2025) の FRAME が同じ形。後述（採用6） |
| 論点を1時間で10前後に切る | トピック分割の実測が Pk 0.33 前後。細かく割ると悪化するだけ（採用5） |

---

## 1. 採った指摘

### 採用1 — `検知方法` には標準名がある：**signpost**

Assumption-Based Planning（Dewar ほか, RAND, 1993）の中核概念。定義は
「**an event or threshold that, if detected, signifies that a vulnerable assumption is being broken**」
（Walker, Haasnoot & Kwakkel 2013 で確認）。

ABP は前提を2軸で絞る — **load-bearing**（計画がそれに依存）と **vulnerable**（覆されやすい）。
我々の ASM は逆リンクで load-bearing は表現できていたが、**vulnerable の軸がなかった**。
全 ASM を追跡する設計は2週25分では破綻する。

**反映**
- `検知方法` → `signpost`。記述は**事象または閾値**に限る（「注意して見る」は不可）
- `脆弱性: 高 / 中 / 低` を追加
- **運用対象は 脆弱性:高 かつ 逆リンクあり のものだけ**。これが棚卸しの門になる
- ASM から生える ACT に ABP の区別を持たせる — `shaping`（前提を守る働きかけ）/ `hedging`（破れた場合の備え）
- PMBOK 系 assumption log の9列のうち **`次回確認日` だけ採る**（既定値＝次回会議日）

### 採用2 — CON は2種が混ざっていた（KAOS）

KAOS は環境側の記述を分ける。**domain property** =「環境についての事実（物理法則など）」、
**domain hypothesis** =「単に成り立っていればよい記述的言明」、**expectation** = 環境エージェントに
割り当てられた規範的言明（Aoyama ほか 2018 が van Lamsweerde 2009 を引用）。

そして判定テストがそのまま使える —
「**assumptions cannot be enforced by the software-to-be**」（van Lamsweerde 2001）。

我々の CON には (a) 法令・既存システムの事実 と (b)「顧客が〜してくれる」が混在していた。
前者に失効条件を求めても埋まらず、後者は破られ得るのに同じ扱いになっていた。

**反映**
- CON に `種類: property / expectation` を追加
- `property` は `失効条件` を空にできる（事実は失効しない）
- `expectation` は `失効条件` を持ち、破られたら DEC を見直す
- **硬度は廃止せず、`種類` × `所在` から導出する**（沈殿型ナレッジの語彙は維持する）
- 判定テスト追加：**自社の作業で守れるものは CON でも ASM でもない。ACT か DEC である**

### 採用3 — 期待値を実測値で較正する

私が前回「1〜3回目は結果が悪い」と書いたのは根拠のない見立てだった。数字がある。

| 項目 | 実測 | 出典 |
|---|---|---|
| 決定対話行為の**人間の注釈一致** | κ 0.63–0.73 | Fernández 2008 |
| アクション項目の**人間の一致** | κ 0.435–0.78 | Purver 2007 / Morgan 2006 |
| 決定対話行為の出現頻度 | 全発話の **4.3%** | Fernández 2008 |
| 決定サブ対話の**位置**検出 | F1 0.58（精度 0.43 / 再現 0.88） | Fernández 2008 |
| 決定の**構成要素**の同定 | F1 0.16–0.39 | Fernández 2008 |
| アクション項目検出 | F 0.32 | Morgan 2006 |
| トピック分割 | Pk 0.33–0.41（**境界の約3割が誤り**） | Solbiati ほか |
| 会議要約の事実不整合（グラウンディングなし） | サンプルの **74%** | QMSum, Zhong 2021 |

数字は 2006–2008 年の統計的分類器（英語, AMI/ICSI）なので現代の LLM は上回る。
だが**人間の一致率は上限として残る**。κ 0.63–0.78 ということは、
「決定とは何か」に人間同士で2〜4割の不一致がある。**正解率9割は原理的に望めない。**

**反映** — README と概要ページの期待値を実測値に差し替え。
「精度が上がれば人間の確認は不要になる」という期待を最初から潰しておく。

### 採用4 — 引用は「提案発話」ではなく「復唱・合意発話」から採る

Fernández ら (2008) は決定対話行為を4分類する — Issue / **Resolution Proposal** /
**Resolution Restatement** / **Agreement**。

提案発話は言い換えられ、撤回される。復唱と合意の発話は決定文として安定する。
そして安定しているぶん、**引用の機械照合が通りやすい**。

**反映** — Pass 3 のプロンプトに引用の採取優先順位を明示。
`Agreement > Resolution Restatement > Resolution Proposal`。
（なお Restatement は人間の一致率が最も低く F1 0.16 なので、取りこぼす前提で。）

### 採用5 — 最大のエラー源は幻覚ではなく**欠落**。ここが我々の穴だった

Kirstein ら (2024) の人手エラー注釈（IAA 0.81）:

```
欠落 89%  ／ 構造崩れ 57% ／ 冗長 40% ／ 非一貫 37%
幻覚 26%  ／ 誤推論 20% ／ 参照誤り 11%
```

**欠落は幻覚の3倍以上**。そして我々の引用検証スクリプトは
「言っていないことを言った」を検出するが「**言ったことを落とした**」を一切検出しない。
設計の最大の穴。

同論文はもう一つ重要なことを報告している。自動評価指標の相関の**約1/3が「エラー隠蔽」**で、
QuestEval と BLEU は**幻覚に正の相関**を示す。ROUGE-1 だけが欠落に −0.40 で反応する。

**反映**
- Pass 3 に欠落ガードを追加：**種別が `議論` / `確認` のセグメントで出力が0件なら、理由を1行書く**
- 理由が書けないセグメントは**レビュー必須フラグ**を立てる
- 指標に「引用一致率」を品質指標として使わないことを明記（後述の落とし穴）

### 採用6 — 我々の賭けは支持されている（ただし幻覚に対してのみ）

Kirstein ら (2025, Findings of EMNLP) の FRAME は、要約生成の前に
「自己完結した検証可能な事実」を抽出し、抽出した事実を超える生成を制約する。
結果、**幻覚が 3–4/5 → 1/5、欠落も 3–4/5 → 1/5**（低いほど良い）。

我々の Pass 2（逐語ログ）→ Pass 3（引用必須抽出）はほぼ同型。
ただし FRAME は Pass 2 相当を「**検証可能な事実の列挙**」にしている点が違い、
そこが欠落の改善にも効いている。

Wang ら (2022) は対話要約の **36–50% が事実誤りを含む**（人間の参照要約でも約17%）と報告し、
最頻エラーは主語・目的語誤り、次に日付・場所の詳細誤り。
**どちらも逐語引用の部分一致照合で機械的に捕まる型**。標的は正しい。

**反映** — Pass 2 を「整形ログ」から「**検証可能な事実の列挙を兼ねたログ**」に寄せる。
発言ログに加えて、そのセグメントで確定した事実（数値・日付・固有名）を列挙させる。

### 採用7 — 沈黙由来の却下は `推測` 固定にする

私は前回「代替案の言及があり反応がない場合」を `信頼度: 言及のみ` で起票すると書いた。
沈黙を却下の根拠に使う手法は、文献に対応するものを見つけられなかった。
そもそも**明示的な合意ですら κ 0.63 / F1 0.39** で最も難しいクラスである（Fernández 2008）。

**反映** — 沈黙を根拠とする却下判定は**自動で `信頼度: 推測` に固定**。
`言及のみ` は「代替案の言及の引用は取れたが却下理由の発言がない」場合に限る。

### 採用8 — `なぜ` を自由記述にすると無価値になる。一文形にする

Falessi ほか (2013) は院生75名・設計決定25件・後続作業5種の統制実験で、
Tyree & Akerman の13カテゴリを評定した。結果：
**Decision と Related requirements は作業を問わず高価値。Notes は一貫して低価値。**
Positions（代替案）は「検証」と「解空間の誤り検出」でのみ有用で、影響評価には無関係。

自由記述の `なぜ` は Notes と同じ運命をたどる。最小の構造付与として Y-statement を使う
（Olaf Zimmermann, ADR Templates）:

> **In the context of** `<use case>`, **facing** `<concern>` **we decided for** `<option>`
> **to achieve** `<quality>`, **accepting** `<downside>`.

`accepting <downside>` は我々に無かった項目で、**採った案の不利**を1行で残せる。
`代替案[].却下理由`（捨てた案の理由）とは別物。

**反映**
- `なぜ` を Y-statement の穴埋め補助つきにする（自由記述も許すが、雛形を出す）
- `受容した不利` を任意フィールドとして追加
- Falessi の結果から、**`代替案` の入力を全 DEC に促さない**。
  後で検証・再検討されうる決定（`種別: 技術判断`、または ASM から逆リンクされているもの）に絞る

### 採用9 — MADR の Confirmation で「寿命管理」が一つの型になる

MADR 4.0.0 (2024-09-17) の任意項目 `Confirmation` =
「ADR の実装／遵守をどう確認できるか（例：設計・コードレビュー、ArchUnit のようなテスト）」。

これを入れると3つが対称になる。

| カード | フィールド | 検知するもの |
|---|---|---|
| DEC | **確認方法** | 決定が守られているか |
| ASM | **signpost** | 前提が崩れたか |
| CON | **失効条件** | 制約が消えたか |

**反映** — DEC に任意フィールド `確認方法` を追加。三者で「決定・前提・制約それぞれの寿命管理」が揃う。

### 採用10 — 受託開発固有：決定ごとに「当初合意範囲の内/外」を立てる

弁護士法人クラフトマンの解説は「課題管理一覧表などを作成して管理し、その課題が
**当初合意された要件や仕様の範囲なのか範囲外なのかを都度明確にしていく**」ことを有益とし、
凍結仕様書からの逸脱が明らかな場合に追加請求が認められやすいとして裁判例を挙げている
（大阪地裁 H14.8.29、東京地裁 H17.4.22、東京高裁 H26.1.15）。

我々の `種別`（交渉可能 / 技術判断 / 契約制約）は「今後変えられるか」の軸しかなかった。
**直交する軸**が必要。

**反映**
- DEC に `範囲: 当初合意内 / 範囲外(追加) / 判定保留` を追加
- `判定保留` が立ったら**自動で Q を起票**
- 25分の中で人間が必ず見る欄はこれ、と優先順位を決められる

これは今回の調査でいちばん実務価値が高い追加だと思う。

### 採用11 — 議事録は相手方の確認で初めて証拠になる。みなし確定ルールを入れる

伊藤雅浩弁護士（弁護士法人内田・鮫島法律事務所, 2017）:
「相手方が内容を確認・同意していないメモは、往々にして自己に都合の良いことしか書かれておらず、
訴訟で水掛け論を招く」「**議事録回覧後、一定期間内に異議がなければ確定する**などのルール設定が有効」。
また「決定事項の重みは会議の位置づけで異なる」ため、会議体を契約書で定義し現場運用と一致させることを求めている。
確認期限の実務相場は3営業日。

**反映**
- 顧客提出版の末尾に「本議事録は送付後3営業日以内に異議がなければ確定」の一文を定型で入れる
- 確定した日を DEC の `確定日` に書き戻す
- `決定の所在`（役割）に加えて **`会議体`**（定例WG / ステアリングコミッティ等）を持たせる。
  役割だけでは契約上の会議体定義と接続できない

### 採用12 — 「何を DEC とするか」の判定が最大のコスト。ガイドを先に作る

Ahmeti ほか (ECSA 2024) のアクションリサーチ（スウェーデン企業のアジャイル2チーム・3か月）で
報告された最大の障害は、記述コストではなく**判定**だった：

> "The hardest part might be to actually decide whether it's a change ... to be considered as an ADR,
> or if it's just part of normal maintenance"

ADR 自体は "really easy to write" と評価されている。
**効いた唯一の介入はガイドラインの明示**で、満足度が 2.0→2.9 / 2.5→3.1 に改善した。

**反映**
- `decision-guide.md` を1枚作る（何が DEC か、何が DEC でないか、境界例）
- 25分の人手は「書く」ではなく**昇格判定（採用/破棄/保留）**に全振りする方針を明文化
- なお同研究は status 欄（superseded 含む）を用意したが**実際に維持できたという証拠はない**。
  我々も `status` の自動維持を期待しない

### 採用13 — 捕捉コストの負担者と受益者の不一致を、まだ解いていなかった

Jintae Lee (IEEE Expert, 1997) は「コスト負担者が受益者と同一でないとき、
費用対効果のあるシステムを提供することは一層困難になる」と述べ、Grudin を引いている。
Lee の処方は (1) 設計手法の**副産物**として根拠が出る、(2) システムと設計者が相互に得をする、
(3) インセンティブ、(4) 漸進的形式化。

我々は土台（決定・未決・アクション）を LLM が生成するのでそこのコストは下がる。
しかし**上乗せ（`なぜ` / `作らない` / `却下理由`）は依然「書く人が得をしない」構造のまま**だった。

**反映** — 書かないことに**即時のコスト**を付ける。必須フィールドにせずインセンティブを作る唯一の形。
- `なぜ` が未記入の DEC は、次回会議のアジェンダ冒頭に自動掲示される
- `なぜ` が未記入の DEC は、CON / ASM への昇格候補になれない
  （＝その制約が将来の議論で自動的に効かない）

「書かないと次の会議が長くなる」という形にする。

### 採用14 — 最低コストの部分形式化を1つ足す（漸進的形式化）

Shipman & Marshall (1999) の処方は「テキストや空間配置のパターンから**推奨仕様を提示する**」こと。
tacit knowledge を会議中に言語化させてはいけない（作業自体を壊す）。

**反映** — LOG の断片に「**後で効く**」フラグだけ立てられる一手を用意する。
カード化も分類もしない。後日その断片が CON / ASM の昇格候補として提示される。

### 採用15 — Q は「不明点」ではなく「利害の衝突（issue）」として起票する

WinWin（Boehm ほか 1998）の4要素は win condition / **issue** / **option** / agreement。
ステークホルダが目標を win condition として表明し、全員が同意すれば agreement になる。
同意しない場合に**衝突を issue として登録し、option を探索する**。

我々の `代替案` は WinWin の **option** と同一概念なので、標準語であることを注記する。

**反映** — Q に `対立当事者: [顧客側 / 自社側 / …]` を追加。
「誰と誰の意見が合っていないのか」が入ると、確認先が自動で決まる。

---

## 2. 採らなかった指摘

記録しておかないと半年後に再検討されるので、理由つきで残す。

### 不採用1 — IBIS / gIBIS / Dialogue Mapping の会議中リアルタイム図式化

Conklin *Dialogue Mapping* (2005)。CogNexus Group 掲載の書評（Seybold 2013）によれば、
Conklin 本人が「**stealth mapping（グループに見せずに私的に描くこと）は Dialogue Mapping ではない**」
とし、共有ディスプレイと参加者による検証サイクルを必須とし、習得に「several hundred」時間を要する
craft だとしている。Shipman & Marshall の「継続的な人的ファシリテーションへの依存」報告とも一致。

**理由** — 我々は会議中の人的コストをゼロにし、音声から事後生成する設計。前提が正面から衝突する。
ただしこれは**意識的なトレードオフとして記録する**（後述）。

### 不採用2 — QOC / DRL の criteria × options 評価マトリクス

MacLean ほかの QOC、Jintae Lee の DRL（decision problem / alternative / claim + criteria 層）。
Buckingham Shum & Hammond (IJHCS 1994) は argumentation ベース DR の二大前提
（DR を論証として表すことは有用 / 設計者はその記法を使える）について
「設計文脈外の semiformal argumentation 研究はどちらの主張も説得的に実証できておらず、
DR 文献にも大きな空白がある」と結論している。

**理由** — 2週サイクルの受託開発には粒度が細かすぎる。さらに我々の `種別` は
「基準による多目的最適化」ではなく**誰の権限の問題か**の分類であり、criteria 層とは焦点がずれる。

### 不採用3 — Toulmin モデルの完全採用

claim / data / warrant / backing / qualifier / rebuttal。
warrant・backing は会議発話にほぼ現れない（Shipman の tacit knowledge そのもの）。
欄を用意して埋めさせれば**人間が作話する** — 我々の原則に正面から反する。

**理由** — 上記。なお qualifier に相当するものは `信頼度` が既に担っている。

### 不採用4 — argument mining による前提・制約リンクの自動生成

Lawrence & Reed (Computational Linguistics 2019): 論証/非論証の分類は F 0.74–0.77、
ADU 境界同定は最大 F 0.89 まで届くが、**関係同定（support/attack）は一貫してコンポーネント検出より低い**。
「ある文が論証的かどうかは、しばしばそれが使われる文脈に依存する」。

**理由** — `前提[]` / `制約[]` / `影響する決定` のリンクを LLM に自動確定させない。
**リンクは人間承認**という現設計を維持する。

### 不採用5 — RAID ログを別レジスタとして併設する

RAID は**標準ではない**。The Digital Project Manager (2022, 2026-05 更新) は
PMI / PRINCE2 / APM のいずれの標準でもない実務ツールと明記し、
**A は Assumptions か Actions、D は Dependencies か Decisions で論者によって意味が違う**ことを認めている。
PRINCE2 の管理成果物に assumptions register は存在しない。
PMBOK 系の assumption log は存在するが推奨欄が9列で、2週25分では埋まらない。

**理由** — 用語が曖昧で、我々の CON/ASM の分離より粗い。`次回確認日` の1欄だけ採った（採用1）。

### 不採用6 — ABP の5ステップ・ワークショップ

ファシリテータ役が必要で、2週25分の枠に入らない。
**signpost / 脆弱性 / shaping・hedging の語彙だけを借用し、手続は借用しない。**

### 不採用7 — KAOS の形式的 obstacle analysis

時相論理による形式定義（van Lamsweerde 2001）。形式モデリング技能を持つ役割が必要。

### 不採用8 — ADR のピアレビュー前置

Ahmeti ほか (2024) が効かせたガイドライン「ADR は他の開発者がレビューし、
レビュー通過後に公開する」は、社内レビュア役を置けないため採らない。
**その代替が採用11の「顧客みなし確定」**で、レビュアを社外（顧客）に外部化する。

---

## 3. 訂正：OpenSpec に `derived_from` はない

前回私は「OpenSpec 生成時に `derived_from` をフロントマターで埋める」と書いた。**間違い。**

OpenSpec は Fission-AI/OpenSpec（MIT、`@fission-ai/openspec`）という実在の単一ツールで、
Thoughtworks Technology Radar Vol.34 (2026-04) で Tools / **Assess**。
構造は `openspec/{specs, changes, archive}`、change フォルダは
`proposal.md`（why we're doing this, what's changing）/ `specs/` / `design.md` / `tasks.md`。
デルタ見出しは `## ADDED / MODIFIED / REMOVED Requirements` + `### Requirement:` + `#### Scenario:`。

README を直接確認した結果：**YAML フロントマターもトレーサビリティ欄も存在しない。**
「Plain Markdown — requirements with concrete scenarios, no special syntax to learn」と明記されている。

つまり `derived_from: [DEC-014, CON-007]` は **OpenSpec の機能ではなく我々の自前規約**になる。
検証もされない。

**反映**
- `derived_from` は `proposal.md` の冒頭行として置く自前規約であると明記（唯一の理由記述枠がそこ）
- 参考：GitHub Spec Kit には **`[NEEDS CLARIFICATION]` マーカー**があり、これは我々の **Q と同一概念**。
  未解決 Q を流し込めば往復が成立する（OpenSpec にこの受け口はない）
- Spec Kit の `constitution.md` は **CON: property の置き場として最も適合**する
  （変更されにくい環境の事実）

---

## 4. 意識的に受け入れるトレードオフ

**会議中に生まれる共通理解を、我々は構造的に取り逃す。**

Conklin は Dialogue Mapping の価値を成果物ではなく
「会議中に生まれる共通理解と、解決策への共有されたコミットメント」に置いている。
我々は事後生成なので、この価値を取れない。

受託開発では**顧客との合意形成そのものが成果物**なので、これは小さい犠牲ではない。
折衷として「会議中に未決 Q だけは共有画面に出す」程度は検討の余地がある。

---

## 5. 評価の落とし穴（自分たちに向けた警告）

AutoMin 2025 の主催者は、同一システムに対する **BART-F1 が 2023 年と 2025 年の計算で
負の相関**を示したと報告し、ROUGE / BERTScore / BARTScore は
「最良システムを他から識別できない」と結論している。
文書レベルの人手スコアと自動指標の相関は BARTScore 0.5 / ROUGE-1 0.3。
GPT ベースの採点は GPT 系出力を系統的に優遇する。

**我々が引用一致率を「議事録の品質指標」として扱い始めたら同じ罠に落ちる。**
引用一致率はグラウンディングの健全性チェックであって、品質指標ではない。

---

## 6. 日本語固有の事情（ほとんど無い）

- **CEJC**（Koiso ほか, LREC 2022、200時間・577会話・240万語）は大規模だが
  **日常会話が対象で業務会議を含まない**
- 日本語の議事録生成で見つかった学術文献は藤岡ほか (2010)
  『自然言語処理技術を活用した議会議事録の要約支援方法について』のみ。
  **定量評価は示されていない**。議会議事録という設定で、受託開発会議とは話者構成も文体も異なる
- **日本語の業務会議における決定検出・アクション抽出のベンチマークも、
  技術用語 ASR 誤りの体系的分析も、見つからなかった**

**含意** — 「一旦置いといて」「持ち帰ります」「前向きに検討」のような日本語の曖昧表現の扱いは、
**文献から借りられない**。自前で少数の実会議に注釈を付け、社内 κ を測るのが唯一の道。
Fernández らの κ 0.63–0.73 が現実的な目標値の目安になる。

**最初の3〜5会議は、LLM 出力と人間判断の差分を記録するデータ収集フェーズと位置づける。**

---

## 出典

実際に取得して内容を確認したもの。

**論証構造・設計合理性**
- Shipman, F. M. III & Marshall, C. C. "Formality Considered Harmful." *CSCW* 8(4):333–352, 1999. https://people.engr.tamu.edu/shipman/formality-paper/harmful.html
- Falessi, D., Briand, L. C., Cantone, G., Capilla, R., Kruchten, P. "The Value of Design Rationale Information." Simula 技術報告（*ACM TOSEM* 2013 対応）. https://cms.simula.no/sites/default/files/publications/Simula.approve.88.pdf
- Buckingham Shum, S. & Hammond, N. "Argumentation-based design rationale: what use at what cost?" *IJHCS* 40(4):603–652, 1994. https://www.sciencedirect.com/science/article/abs/pii/S1071581984710299 （抄録のみ）
- Lee, Jintae. "Design Rationale Systems: Understanding the Issues." *IEEE Expert*, 1997. https://users.cs.northwestern.edu/~paritosh/papers/sketch-to-models/LeeDesignRationaleSystems.pdf
- Lawrence, J. & Reed, C. "Argument Mining: A Survey." *Computational Linguistics* 45(4), 2019. https://direct.mit.edu/coli/article/45/4/765/93362/Argument-Mining-A-Survey
- Nygard, M. "Documenting Architecture Decisions." 2011. https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions
- MADR 4.0.0 (2024-09-17). https://adr.github.io/madr/
- ADR Templates（Y-statement / Zimmermann）. https://adr.github.io/adr-templates/
- W3C. "PROV-O: The PROV Ontology." 2013-04-30. https://www.w3.org/TR/prov-o/
- CDC/NCIRD. *ACIP GRADE Handbook* ch.7. https://www.cdc.gov/acip-grade-handbook/hcp/chapter-7-grade-criteria-determining-certainty-of-evidence/index.html
- Seybold, P. B. による Conklin *Dialogue Mapping* 書評, CogNexus Group, 2013. https://cognexusgroup.com/wp-content/uploads/2013/07/Using-Dialogue-Mapping-to-Address-Wicked-Problems-05-23-2013.pdf

**会議理解 NLP**
- Fernández, R., Frampton, M., Ehlen, P., Purver, M., Peters, S. "Modelling and Detecting Decisions in Multi-party Dialogue." SIGdial 2008. https://aclanthology.org/W08-0125.pdf
- Purver, M. ほか. "Detecting and Summarizing Action Items in Multi-Party Dialogue." SIGdial 2007. https://aclanthology.org/2007.sigdial-1.4.pdf
- Morgan, W., Chang, P.-C., Gupta, S., Brenier, J. M. "Automatically Detecting Action Items in Audio Meeting Recordings." SIGdial 2006. https://nlp.stanford.edu/pubs/sigdial06.pdf
- Murray, G. & Renals, S. "Detecting Action Items in Meetings." MLMI 2008. https://www.pure.ed.ac.uk/ws/files/14860467/Detecting_Action_Items_in_Meetings.pdf
- Solbiati, A. ほか. "Unsupervised Topic Segmentation of Meetings with BERT Embeddings." arXiv:2106.12978. https://arxiv.org/html/2106.12978v1
- Zhong, M. ほか. "QMSum." NAACL 2021. https://aclanthology.org/2021.naacl-main.472.pdf
- Wang, B. ほか. "Analyzing and Evaluating Faithfulness in Dialogue Summarization." EMNLP 2022. https://aclanthology.org/2022.emnlp-main.325.pdf
- Kirstein, F. ほか. "What's under the hood: Investigating Automatic Metrics on Meeting Summarization." 2024. https://arxiv.org/html/2404.11124
- Kirstein, F. ほか. "Re-FRAME the Meeting Summarization SCOPE." Findings of EMNLP 2025. https://arxiv.org/html/2509.15901v1
- Shinde, K. ほか. "Findings of the Third Automatic Minuting (AutoMin) Challenge." 2025. https://arxiv.org/html/2509.13814
- Bunt, H. ほか. "ISO 24617-2: A semantically-based standard for dialogue annotation." LREC 2012. https://people.ict.usc.edu/~traum/Papers/Buntetal-ISO24617-2.pdf
- AMI Corpus Annotation, Univ. of Edinburgh. https://groups.inf.ed.ac.uk/ami/corpus/annotation.shtml
- Koiso, H. ほか. "Design and Evaluation of the Corpus of Everyday Japanese Conversation." LREC 2022. https://aclanthology.org/2022.lrec-1.599/
- 藤岡亮介, 渡邊俊彦, 楢崎博司「自然言語処理技術を活用した議会議事録の要約支援方法について」バイオメディカル・ファジィ・システム学会誌 12(2), 2010. https://www.jstage.jst.go.jp/article/jbfsa/12/2/12_KJ00006659552/_article/-char/ja/

**実務の記録体系**
- Walker, W. E., Haasnoot, M., Kwakkel, J. H. "Adapt or Perish." *Sustainability* 5(3):955–979, 2013. https://www.mdpi.com/2071-1050/5/3/955 （signpost / shaping / hedging / load-bearing / vulnerable の定義）
- Dewar, J. A. ほか. *Assumption-Based Planning*, RAND MR-114-A, 1993. https://www.rand.org/pubs/monograph_reports/MR114.html （書誌のみ）
- Aoyama ほか. "Supporting the Systematic Goal Refinement in KAOS using the Six-Variable Model." SciTePress 2018. https://www.scitepress.org/papers/2018/68507/68507.pdf
- van Lamsweerde, A. "Goal-Oriented Requirements Engineering: A Guided Tour." RE'01. https://homepages.uc.edu/~niunn/courses/RE-refs/GuidedTour01.pdf
- Ahmeti, B., Linder, M., Groner, R., Wohlrab, R. "Architecture Decision Records in Practice: An Action Research Study." ECSA 2024. https://rebekkaa.github.io/files/2024_ECSA.pdf
- Boehm, B. ほか. "Using the WinWin Spiral Model: A Case Study." *Computer* 31(7), 1998. https://cs.nyu.edu/~jcf/classes/g22.3033-007_sp04/handouts/UsingTheSpiralModel.pdf
- Hoban, S. M. "RAID Logs." The Digital Project Manager, 2022（2026-05 更新）. https://thedigitalprojectmanager.com/project-management/raid-log/
- PRINCE2 wiki, "Project log." https://prince2.wiki/management-products/project-log/
- 伊藤雅浩（弁護士法人内田・鮫島法律事務所）「会議運営上の注意（議事録等）」2017-03-29. https://www.it-houmu.com/archives/1640
- 弁護士法人クラフトマン「仕様変更・開発範囲の変更に関する諸問題」. https://www.ishioroshi.com/biz/kaisetu/it/index/shiyouhenkou/
- Fission-AI/OpenSpec. https://github.com/Fission-AI/OpenSpec ／ README を直接確認: https://raw.githubusercontent.com/Fission-AI/OpenSpec/main/README.md
- Thoughtworks Technology Radar Vol.34 (2026-04), OpenSpec. https://www.thoughtworks.com/en-us/radar/tools/openspec
- github/spec-kit, `spec-driven.md`. https://github.com/github/spec-kit/blob/main/spec-driven.md
- Kiro Docs, "Specs." https://kiro.dev/docs/specs/

### 未確認（本文で数値・定義を引用していないもの）

- Grudin, J. "Evaluating Opportunities for Design Capture" / "Groupware and social dynamics"
  — 本文取得不能。**「コスト負担者≠受益者」の主張を Grudin に帰属させているのは
  Lee (1997) が明示的に Grudin を引いている記述を根拠とする間接引用**
- Kunz & Rittel (1970) IBIS 原典、Conklin & Begeman (1988) gIBIS、Conklin *Dialogue Mapping* 本文
  — いずれも二次文献経由
- MacLean ほか QOC 原典、Toulmin *The Uses of Argument* (1958)、Tyree & Akerman の13カテゴリ
  — 本文未確認
- Dewar (2002) Cambridge UP 版の load-bearing / vulnerable / signpost の**原典定義**
  — ペイウォール。定義は Walker ほか (2013) で確認
- van Lamsweerde (2009) 書籍 — Aoyama ほか経由
- Hsueh & Moore の decision detection — F値・κ が取得できず、**数値は一切引用していない**
- IPA『情報システム・モデル取引・契約書（第二版）』2020-12-22
  — 存在・公表主体・公表日のみ確認。連絡協議会・変更管理・議事録の条項本文は未確認。
  「連絡協議会が決定権限を定義している」という筋は有望だが、裏が取れていないので採用判断に使っていない
- AMI の対話行為スキーム15クラスの具体名 — 取得できず

ブロックされたドメイン: dl.acm.org (403)、ResearchGate、Springer 有料本文、
jonathangrudin.com（リダイレクトループ）、pmc.ncbi.nlm.nih.gov (reCAPTCHA)。
いずれも回避策は取っていない。
