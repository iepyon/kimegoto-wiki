#!/usr/bin/env python3
"""llm-wiki 引用検証（`kime verify-quotes` の互換ラッパ）

    python3 verify_quotes.py               # 検証して報告するだけ
    python3 verify_quotes.py --fix         # 一致しない引用の信頼度を「推測」に降格
    python3 verify_quotes.py --root path/to/project

実体は tools/verify_cmd.py にある。README と example/README.md がこのコマンドを
案内しているので、入口としてここに残している。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tools.verify_cmd import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
