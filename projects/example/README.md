# 動作確認用サンプル

引用検証をすぐ試せる最小構成。**DEC-014 の代替案2件目の引用だけ、意図的に
LOG カードと1文字違いにしてある。**

```
python3 verify_quotes.py --root projects/example        # 不一致1件を検出（終了コード 1）
python3 verify_quotes.py --root projects/example --fix  # 信頼度を「推測」に降格して書き戻す
python3 verify_quotes.py --root projects/example        # 再実行しても二重に処理しない
```

句読点・鉤括弧・全角半角の差は正規化して吸収する（Q-031 の引用は句点つきでも一致する）。

他のコマンドも同じく `--root` で指定する。

```
python3 tools/giji.py lint --root projects/example
python3 tools/giji.py views --root projects/example
python3 tools/giji.py review --root projects/example --meeting MTG-20260918
python3 tools/giji.py minutes-input --root projects/example --edition customer
```

## この案件は lint の error を1件出す

上記のとおり引用を意図的にずらしてあるので、`lint` は `quote-verbatim` の error を
必ず1件出す。**それが正しい状態。** `.fixture` を置いてあるので、pre-commit と
Stop フックの自動検査からは外れる（教材であって実運用の案件ではないため）。

## Pass 1 を試す

`meetings/MTG-20260918/transcript.md` を置いてある。書式は
`templates/project/README.md` の「文字起こしの書式」。`/segment` に渡すと
`segments.yaml` が出る（`logs/LOG-20260918-03.md` がその先の姿）。
