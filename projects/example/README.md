# 動作確認用サンプル

`verify_quotes.py` をすぐ試せる最小構成。DEC-014 の代替案2件目の引用だけ、
意図的に LOG カードと1文字違いにしてある。

```
cd example
python3 ../verify_quotes.py            # 不一致1件を検出（終了コード 1）
python3 ../verify_quotes.py --fix      # 信頼度を「推測」に降格して書き戻す
python3 ../verify_quotes.py            # 再実行しても二重に処理しない
```

句読点・鉤括弧・全角半角の差は正規化して吸収する（Q-031 の引用は句点つきでも一致する）。
