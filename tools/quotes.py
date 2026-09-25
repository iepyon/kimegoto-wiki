#!/usr/bin/env python3
"""引用の機械検証。

カードの `引用` が、参照先 LOG カードの本文に実在するかを照合する。
存在しないものは信頼度を「推測」に降格する。

プロンプトに「引用は原文のまま」と書いても守られない。構造で守るための道具。

**照合先は LOG カードであって文字起こし原本ではない。** Pass 2 で正規化して
いるため原本とは文字列が一致しない。

**検出と書き戻しを分ける。**
  - 検出（`check`）は lint が呼ぶ。ファイルを一切書き換えない。
  - 書き戻し（`fix_card`）は `kime verify-quotes --fix` だけが呼ぶ。行単位で
    置き換え、frontmatter のコメントと空欄の順序を壊さない。
"""

import re
import unicodedata

from tools.miniyaml import split_frontmatter

LOG_ID = re.compile(r"LOG-\d{8}-\d+")
QUOTE_LINE = re.compile(r"^(?P<indent>\s*)(?:-\s+)?引用\s*[:：]\s*(?P<value>.*?)\s*$")
CONF_LINE = re.compile(r"^(?P<indent>\s*)(?:-\s+)?信頼度\s*[:：]\s*(?P<value>.*?)\s*$")

# 正規化で落とす文字。語順・語彙は変えない前提なので、
# 括弧・引用符・空白・文末記号だけを除去して比較する。
STRIP = re.compile(r"[\s「」『』【】（）()\[\]｛｝{}、。，．,\.!?！？…‥\"'`]")

# status の意味
OK = "ok"                 # LOG 本文に見つかった
FAIL = "fail"             # 見つからず、信頼度が 推測 でもない（= 要修正）
NO_REF = "no_ref"         # frontmatter に LOG の id が無く、照合しようがない
ALREADY_GUESS = "already_guess"   # 見つからないが、既に 推測 を名乗っている
FIXED = "fixed"           # --fix で 推測 に降格した


def norm(text):
    """比較用の正規化。全角半角を寄せ、記号と空白を落とす。"""
    return STRIP.sub("", unicodedata.normalize("NFKC", text or ""))


def strip_quotes(value):
    """YAML のクォートと鉤括弧を外す。"""
    v = (value or "").strip()
    for a, b in (('"', '"'), ("'", "'"), ("「", "」"), ("『", "』")):
        if len(v) >= 2 and v.startswith(a) and v.endswith(b):
            v = v[1:-1].strip()
    return v


class QuoteIssue:
    """引用1件の照合結果。"""

    __slots__ = ("card", "line", "quote", "confidence", "status", "detail")

    def __init__(self, card, line, quote, confidence, status, detail):
        self.card = card
        self.line = line
        self.quote = quote
        self.confidence = confidence
        self.status = status
        self.detail = detail

    def __repr__(self):
        return "<QuoteIssue %s:%d %s>" % (self.card.id, self.line, self.status)

    @property
    def is_problem(self):
        """慎重側（推測）への降格は問題にしない。水増しだけを拾う。"""
        return self.status in (FAIL, NO_REF)


def _frontmatter_range(lines):
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return (1, i)
    return None


def _collect(lines, fm_range):
    """frontmatter から (引用の行番号, 引用値, 信頼度の行番号) を集める。

    信頼度は引用の直後の非空行に現れることを前提にする。この前提が崩れると
    --fix が降格先を見つけられないので、lint 側で `confidence-position` として
    別途 warning を出す。
    """
    start, end = fm_range
    found = []
    for i in range(start, end):
        m = QUOTE_LINE.match(lines[i])
        if not m:
            continue
        value = strip_quotes(m.group("value"))
        if not value or value in ("|", ">", "null", "~"):
            continue  # 空欄・ブロックスカラーは対象外
        conf_idx = None
        for j in range(i + 1, min(i + 4, end)):
            if not lines[j].strip():
                continue
            if CONF_LINE.match(lines[j]):
                conf_idx = j
            break
        found.append((i, value, conf_idx))
    return found


def _normalized_logs(wiki):
    """LOG id -> 発言を連結した正規化済み文字列。"""
    return {log.id: norm("\n".join(text for _, text in log.utterances))
            for log in wiki.by_type("LOG")}


def _examine(card, lines, logs, guess):
    """1枚分の照合。書き換えはしない。(QuoteIssue, 信頼度の行番号) の列を返す。

    `guess` は照合できなかった印の `信頼度`（`ontology.yaml` の `unverified-confidence`）。
    """
    fm = _frontmatter_range(lines)
    if not fm:
        return []
    fm_text = "\n".join(lines[fm[0]:fm[1]])
    referenced = list(dict.fromkeys(LOG_ID.findall(fm_text)))

    out = []
    for line_idx, quote, conf_idx in _collect(lines, fm):
        confidence = None
        if conf_idx is not None:
            confidence = strip_quotes(CONF_LINE.match(lines[conf_idx]).group("value"))

        if not referenced:
            out.append((QuoteIssue(card, line_idx + 1, quote, confidence, NO_REF,
                                   "derived_from に LOG の id が無い"), conf_idx))
            continue

        needle = norm(quote)
        hit = next((lid for lid in referenced
                    if lid in logs and needle in logs[lid]), None)
        if hit:
            out.append((QuoteIssue(card, line_idx + 1, quote, confidence, OK, hit), conf_idx))
            continue

        missing = [lid for lid in referenced if lid not in logs]
        detail = "参照先 %s の本文に見つからない" % " / ".join(referenced)
        if missing:
            detail += "（LOG カード自体が見つからない: %s）" % ", ".join(missing)
        status = ALREADY_GUESS if confidence == guess else FAIL
        out.append((QuoteIssue(card, line_idx + 1, quote, confidence, status, detail), conf_idx))
    return out


def check(wiki):
    """案件全体を照合する。ファイルは書き換えない。"""
    logs = _normalized_logs(wiki)
    out = []
    for card in wiki.cards:
        if card.error is not None:
            continue
        lines = card.path.read_text(encoding="utf-8").splitlines()
        out.extend(issue for issue, _ in _examine(card, lines, logs, wiki.ontology.unverified_confidence))
    return out


def fix_card(card, logs, guess):
    """1枚を降格して書き戻す。(降格件数, QuoteIssue の列)。"""
    lines = card.path.read_text(encoding="utf-8").splitlines()
    results = _examine(card, lines, logs, guess)
    fixed = 0
    for issue, conf_idx in results:
        if issue.status != FAIL or conf_idx is None:
            continue
        m = CONF_LINE.match(lines[conf_idx])
        lines[conf_idx] = lines[conf_idx][:m.start("value")] + guess
        issue.status = FIXED
        fixed += 1
    if fixed:
        card.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return fixed, [issue for issue, _ in results]


def fix(wiki):
    """案件全体を降格して書き戻す。(降格件数, QuoteIssue の列)。"""
    logs = _normalized_logs(wiki)
    total, issues = 0, []
    for card in wiki.cards:
        if card.error is not None:
            continue
        count, found = fix_card(card, logs, wiki.ontology.unverified_confidence)
        total += count
        issues.extend(found)
    return total, issues


def confidence_out_of_position(wiki):
    """`信頼度` が `引用` の直後に無いカード。--fix が働かなくなる構造。"""
    out = []
    for card in wiki.cards:
        if card.error is not None:
            continue
        lines = card.path.read_text(encoding="utf-8").splitlines()
        fm = _frontmatter_range(lines)
        if not fm:
            continue
        for line_idx, quote, conf_idx in _collect(lines, fm):
            if conf_idx is None:
                out.append((card, line_idx + 1, quote))
    return out
