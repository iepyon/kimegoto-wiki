#!/usr/bin/env python3
"""`kime unknown-terms` — LOG 本文から未知語の候補を機械的に拾う。

未知語の3条件のうち、

1. 用語集（`terms/*.md` の `正式` と `表記揺れ`）に無い
2. カタカナ語 / 英字略語 / 漢字列 のいずれか
3. 同一会議内で `term-min-occurrences` 回以上出現

は全部が文字列処理で決まる。とくに **3 の計数は LLM がいちばん間違える**
（数えるたびに違う数を出す）。ここを機械に寄せ、LLM には

- 一般的なビジネス用語の除外（「スケジュール」「リソース」「アサイン」等）
- `推定` の1行（既存用語の表記崩れか、新規用語か）

だけを残す。どちらも語彙の知識が要るので機械では決まらない。

閾値と用語集の在処は `ontology.yaml` が正本。ここに数字を書かない。
"""

import argparse
import re
import sys

from tools import schema
from tools.cards import Wiki, resolve_root

# 候補の文字クラス。長さの下限は「偶然の断片を拾わない」ための最小限。
PATTERNS = [
    # 漢字＋カタカナの複合語を先に見る（「権限マトリクス」を「マトリクス」に
    # 割らない。案件固有の語はたいていこの形で現れる）。
    re.compile(r"[一-龥]{1,4}[ァ-ヴヷ-ヺー]{2,}"),
    re.compile(r"[ァ-ヴヷ-ヺー]{3,}"),          # カタカナ語
    re.compile(r"[A-Za-z][A-Za-z0-9+#\-]{1,}"),  # 英字略語・製品名
    re.compile(r"[一-龥]{3,}"),                  # 漢字列（2字の常用語は拾わない）
]


def glossary(wiki):
    """用語集に載っている表記の集合。`正式` と `表記揺れ` の全値。"""
    known = set()
    for card in wiki.by_type("TERM"):
        if card.error is not None:
            continue
        if card.get("正式"):
            known.add(card.get("正式"))
        known.update(v for v in card.list("表記揺れ") if v)
    return known


def candidates(wiki, meeting_id):
    """[{語, 出現回数, 初出, 文脈}, ...]。出現回数の多い順。"""
    known = glossary(wiki)
    minimum = wiki.ontology.threshold("term-min-occurrences")
    found = {}
    for log in sorted(wiki.logs_of(meeting_id), key=lambda c: c.id):
        for _, text in log.utterances:
            for pattern in PATTERNS:
                for word in pattern.findall(text):
                    if word in known:
                        continue
                    row = found.setdefault(word, {"語": word, "出現回数": 0,
                                                  "初出": log.id, "文脈": text})
                    row["出現回数"] += 1
    rows = [r for r in found.values() if r["出現回数"] >= minimum]
    # 長い語に含まれる短い語は落とす（「権限マトリクス」があれば「マトリクス」は
    # 出さない）。出現回数が上回るなら独立した語なので残す。
    rows = [r for r in rows
            if not any(other["語"] != r["語"]
                       and r["語"] in other["語"]
                       and other["出現回数"] >= r["出現回数"]
                       for other in rows)]
    return sorted(rows, key=lambda r: (-r["出現回数"], r["語"]))


def render(wiki, meeting_id):
    rows = candidates(wiki, meeting_id)
    minimum = wiki.ontology.threshold("term-min-occurrences")
    out = ["# 未知語の候補 — %s" % meeting_id, "",
           "用語集に無く、%d回以上出現し、カタカナ / 英字 / 漢字列のいずれかに"
           "当たる語。**機械が拾っただけで、まだ未知語ではない。**" % minimum, "",
           "ここから次の2つだけを人が（LLM が）判断する。", "",
           "1. 一般的なビジネス用語を落とす（「スケジュール」「リソース」「アサイン」等）",
           "2. `推定` を1行書く（既存用語の表記崩れか、新規用語か。断定しない）", "",
           "残ったものを `meetings/%s/unknown-terms.yaml` に書く。" % meeting_id, ""]
    if not rows:
        out.append("候補なし。")
        return "\n".join(out) + "\n"
    out.append("```yaml")
    out.append("meeting: %s" % meeting_id)
    out.append("unknown_terms:")
    for row in rows:
        out.append("  - 語: %s" % row["語"])
        out.append("    出現回数: %d" % row["出現回数"])
        out.append("    初出: %s" % row["初出"])
        out.append("    文脈: %s" % row["文脈"])
        out.append("    推定: ")
        out.append("")
    out.append("```")
    out.append("")
    out.append("候補 %d件。" % len(rows))
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kime unknown-terms",
                                 description="LOG 本文から未知語の候補を拾う")
    ap.add_argument("--meeting", default=None, help="会議 ID（既定: 最新）")
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)

    wiki = Wiki(resolve_root(args.root), schema.load())
    meeting_id = args.meeting
    if not meeting_id:
        latest = wiki.latest_meeting()
        if latest is None:
            print("会議が1つも無い", file=sys.stderr)
            return 2
        meeting_id = latest.id
    if meeting_id not in wiki.meetings:
        print("会議が無い: %s" % meeting_id, file=sys.stderr)
        return 2

    print(render(wiki, meeting_id), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
