#!/usr/bin/env python3
"""Stop — カードより古いビューを再生成する。

アジェンダが「人が忘れても勝手に出てくる」ことが、この仕組みが引かれる条件。
だからターンの終わりに黙って作り直す。

**常に exit 0。** ここで止める理由は無い（生成に失敗しても作業は進められる）。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _bootstrap import KIT_ROOT, is_this_kit  # noqa: E402


def main():
    if not is_this_kit():
        return 0
    try:
        import json

        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
        if payload.get("stop_hook_active"):
            return 0          # 自分が起こしたターンでは動かない（無限ループ防止）
    except (ValueError, OSError):
        pass

    try:
        from tools import gen_views, schema
        from tools.cards import Wiki

        projects = os.path.join(KIT_ROOT, "projects")
        if not os.path.isdir(projects):
            return 0
        ontology = schema.load()
        for slug in sorted(os.listdir(projects)):
            root = os.path.join(projects, slug)
            if not os.path.isdir(root):
                continue
            wiki = Wiki(root, ontology)
            if not wiki.cards or wiki.is_fixture:
                continue
            # カードより新しいビューしか無いならスキップ（毎ターン全書き換えしない）
            newest = wiki.newest_card_mtime()
            views = wiki.views_dir
            if views.is_dir():
                oldest_view = min((p.stat().st_mtime for p in views.glob("*.md")), default=0)
                if oldest_view >= newest:
                    continue
            gen_views.generate(wiki)
    except Exception:          # noqa: BLE001 — フックは作業を止めない
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
