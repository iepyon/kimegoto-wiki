#!/usr/bin/env python3
"""kime — kimegoto（決め事を記録するキット）の CLI。

サブコマンドを振り分けるだけの薄い層。実体は tools/*.py の main(argv) にある
（フックからインプロセスで呼べるようにするため）。

    python3 tools/kime.py <サブコマンド> [オプション]
"""

import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# サブコマンド名 -> (モジュール, 一行説明)
COMMANDS = {
    "agenda": ("tools.agenda_cmd", "次回アジェンダ（ビュー）を出す"),
    "agenda-input": ("tools.agenda_input_cmd", "次回アジェンダをレンダリングするための材料を組み立てる"),
    "agenda-sync": ("tools.agenda_sync_cmd", "論点に付いた議題を議題カードの status と予定会議に書き戻す"),
    "issue": ("tools.issues", "ACT から GitHub Issue の下書きを作る"),
    "lint": ("tools.kimelint", "カードの整合性を機械的に検査する"),
    "minutes-input": ("tools.minutes_cmd", "議事録をレンダリングするための材料を組み立てる"),
    "new": ("tools.new_cmd", "雛形から新しいカードを起こす"),
    "unknown-terms": ("tools.terms_cmd", "LOG 本文から未知語の候補を拾う"),
    "update": ("tools.update_cmd", "既存カードのフィールドを書き換える"),
    "confirm": ("tools.confirm_cmd", "みなし確定の期限を `確定日` に書き戻す"),
    "promote-input": ("tools.promote_cmd", "昇格候補を出すための材料（理由が記録されていない決定は落とす）"),
    "review": ("tools.review_cmd", "確認②の25分のチェックリスト"),
    "scope-questions": ("tools.scope_cmd", "`範囲: 判定保留` の決定に定型の問いを起票する"),
    "status": ("tools.status_cmd", "いまの会議の進み具合と、次にやることを出す"),
    "schema": ("tools.gen_schema_doc", "ontology.yaml と schema.md / 雛形の同期"),
    "verify-quotes": ("tools.verify_cmd", "引用を LOG カードと照合する（--fix で降格）"),
    "views": ("tools.gen_views", "カードからビューを生成する"),
}


def _usage():
    print(__doc__.strip())
    print("\nサブコマンド:")
    width = max(len(name) for name in COMMANDS)
    for name in sorted(COMMANDS):
        print("  %-*s  %s" % (width, name, COMMANDS[name][1]))
    print("\n各サブコマンドの詳細は `<サブコマンド> --help`。")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        _usage()
        return 0
    name = argv[0]
    if name not in COMMANDS:
        print("未知のサブコマンド: %s" % name, file=sys.stderr)
        _usage()
        return 2
    module_name = COMMANDS[name][0]
    module = __import__(module_name, fromlist=["main"])
    return module.main(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
