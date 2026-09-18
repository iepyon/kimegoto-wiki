---
name: log-cards
description: 論点ごとに LOG カードを生成する（Pass 2）。「LOG を作って」「Pass 2 を回して」「会話ログをカードにして」といった依頼で使う。未知語の検出も行う。DEC/Q/ACT は作らない。
---

# Pass 2 — LOG カードの生成

共通規約は `CLAUDE.md` が正典。手順の正本は `prompts/pass2_log.md`。
以下は本スキル固有の手順。

## 手順

1. `meetings/MTG-YYYYMMDD/segments.yaml` と `transcript.md` を読む
2. `terms/*.md` の `正式` と `表記揺れ` を全部読む（正規化に使う）
3. `prompts/pass2_log.md` の指示をそのまま実行する
4. `python3 tools/giji.py new log --meeting MTG-YYYYMMDD` で ID を採番する
5. `meetings/MTG-YYYYMMDD/logs/LOG-YYYYMMDD-NN.md` に書き出す
6. 未知語リストを `meetings/MTG-YYYYMMDD/unknown-terms.yaml` に出す

## ここが後続すべての土台になる

**LOG はこの会議から生まれるすべての引用の照合先。** 本文の形式は
`- **役割**: 発言` で固定する。引用検証がこの行から発言部分を取るので、
形が崩れると検証機構が死ぬ。

沈黙などの注記は `- **(沈黙 約6秒)**` の形で書く（役割として読まれない形）。

書き終えたら `python3 tools/giji.py lint --check log-format` で形式を確認する。

## このパスでやらないこと

- DEC / Q / ACT を作る（Pass 3）
- CON / ASM / TERM を作る（Pass 4 の承認後）
- 発言の意味を解釈する

## 一度コミットしたら書き換えない

LOG は不変層。生成中（未コミット）は自由に直してよいが、コミットしたあとは
PreToolUse フックが書き込みを止める。
