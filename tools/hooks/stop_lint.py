#!/usr/bin/env python3
"""Stop — error が残っていればターンを終わらせない。

warning では止めない。`act-overdue` や `q-stale` は真の未達を映す計器であって、
消すものではない。止めるのは error だけ。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _bootstrap import KIT_ROOT, is_this_kit  # noqa: E402

LIMIT = 12


def main():
    if not is_this_kit():
        return 0
    try:
        import json

        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
        if payload.get("stop_hook_active"):
            return 0
    except (ValueError, OSError):
        pass

    try:
        from tools import gijilint, schema
        from tools.cards import Wiki

        projects = os.path.join(KIT_ROOT, "projects")
        if not os.path.isdir(projects):
            return 0
        ontology = schema.load()
        errors = []
        for slug in sorted(os.listdir(projects)):
            root = os.path.join(projects, slug)
            if not os.path.isdir(root):
                continue
            if os.path.exists(os.path.join(root, ".wip")):
                continue          # 作りかけ。完成するまで error が出るのは当たり前
            wiki = Wiki(root, ontology)
            if not wiki.cards or wiki.is_fixture:
                continue
            errors.extend((slug, p) for p in gijilint.run(wiki)
                          if p.level == gijilint.ERROR)
    except Exception:          # noqa: BLE001
        return 0

    if not errors:
        return 0

    print("lint に error が %d件 残っています。" % len(errors), file=sys.stderr)
    for slug, problem in errors[:LIMIT]:
        print("  [%s] %-20s %-16s %s" % (slug, problem.check, problem.where, problem.message),
              file=sys.stderr)
    if len(errors) > LIMIT:
        print("  … 他 %d件" % (len(errors) - LIMIT), file=sys.stderr)
    print("\n`python3 tools/giji.py lint` で全件を確認できます。"
          "引用の不一致なら `python3 tools/giji.py verify-quotes --fix` で"
          "信頼度を推測に降格できます。", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
