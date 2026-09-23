#!/usr/bin/env python3
"""`kime agenda` — 次回アジェンダを標準出力へ。

④が「Wiki を使う動機」になる。溜める動機より引く動機を先に作るのが定着の条件。
"""

import argparse
import datetime
import sys

from tools import gen_views, schema
from tools.cards import Wiki, resolve_root


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kime agenda", description="次回アジェンダを出す")
    ap.add_argument("--root", default=None)
    ap.add_argument("--today", default=None)
    args = ap.parse_args(argv)

    today = datetime.date.fromisoformat(args.today) if args.today else None
    wiki = Wiki(resolve_root(args.root), schema.load())
    print(gen_views.render(wiki, "agenda-next", today), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
