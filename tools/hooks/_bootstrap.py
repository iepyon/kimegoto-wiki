"""フックからキットのモジュールを import できるようにする。"""

import os
import sys

KIT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if KIT_ROOT not in sys.path:
    sys.path.insert(0, KIT_ROOT)


def is_this_kit():
    """このリポジトリで動いているか。他のリポジトリで誤爆しないための門。"""
    return os.path.exists(os.path.join(KIT_ROOT, "ontology.yaml"))
