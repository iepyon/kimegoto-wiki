#!/usr/bin/env python3
"""
YAML サブセットパーサ（標準ライブラリのみ）

このキットは外部依存を持たない方針なので PyYAML を使えない。だが YAML を
読む必要はある（ontology.yaml / role-mapping.yaml / segments.yaml /
promote-candidates.yaml / 各カードの frontmatter）。そこで、それらが実際に
使う構文だけを扱う狭いパーサを自前で持つ。

設計方針:

1. **値はすべて str。** PyYAML の BaseLoader 相当。`はい` が True になったり
   `2026-09-18` が date になったりしない。カードの値は人間が書いた日本語で、
   型推論の恩恵より事故のほうが大きい。

2. **知らない構文は黙って通さず例外にする。** アンカー・タグ・複数ドキュメント・
   複雑キーは非対応。中途半端に読めたふりをすると、lint が「空欄」と誤認して
   検出をすり抜ける。読めないなら読めないと言う（フェイルクローズ）。

3. **例外は行番号を持つ。** 壊れた frontmatter は1件で名指しして、そのカードの
   スキーマ系チェックを飛ばすために使う。コロン1つの書き損じが無関係な error を
   量産するのを防ぐ。

扱う構文:
    - ブロックマッピング（入れ子）
    - ブロックシーケンス（`- スカラー` / `- key: value` / `-` + 子ブロック）
    - インラインシーケンス `[a, b]` / インラインマッピング `{a: b}`
    - シングル・ダブルクォート
    - ブロックスカラー `|` `>`（および `|-` `>-` `|+` `>+`）
    - `#` コメント（行頭、および クォート外の ` #` 以降）

扱わない構文（例外になる）:
    - アンカー `&x` / エイリアス `*x` / タグ `!!str`
    - 複数ドキュメント `---` 区切り（frontmatter の切り出しは呼び出し側の仕事）
    - 複雑キー `? key`
    - タブによるインデント

依存: 標準ライブラリのみ
"""

import re

__all__ = ["MiniYamlError", "parse", "parse_frontmatter_block", "split_frontmatter"]


class MiniYamlError(ValueError):
    """読めない YAML。`line` は 1 始まりの行番号（不明なら None）。"""

    def __init__(self, message, line=None):
        self.line = line
        if line is not None:
            super().__init__("%d行目: %s" % (line, message))
        else:
            super().__init__(message)


# 行頭の `-` に続くのは 空白 か 行末 のときだけシーケンス項目。
# `-1` や `-- 補足` をシーケンスと誤認しないため。
_SEQ_ITEM = re.compile(r"^-(?:\s+(?P<rest>.*))?$")

# 未対応構文の早期検出。値の中に出てもよいので、行頭側だけを見る。
_UNSUPPORTED_PREFIX = [
    ("&", "アンカー (&) は未対応"),
    ("*", "エイリアス (*) は未対応"),
    ("!", "タグ (!) は未対応"),
    ("?", "複雑キー (?) は未対応"),
]

_BLOCK_SCALAR = re.compile(r"^[|>]([+-]?)(\d*)$|^[|>](\d*)([+-]?)$")


class _Line:
    __slots__ = ("indent", "text", "no", "raw", "skip")

    def __init__(self, raw, no):
        self.raw = raw
        self.no = no
        stripped = raw.lstrip(" ")
        self.indent = len(raw) - len(stripped)
        self.text = stripped.rstrip()
        # 空行と、行全体がコメントの行は構造として読み飛ばす。
        # ただし raw は保持する（ブロックスカラーの中身になりうるため）。
        self.skip = self.text == "" or self.text.startswith("#")


def _scan(text):
    lines = []
    for i, raw in enumerate(text.splitlines(), start=1):
        if "\t" in raw[: len(raw) - len(raw.lstrip(" \t"))]:
            raise MiniYamlError("インデントにタブが使われている", i)
        lines.append(_Line(raw, i))
    return lines


def _next_content(lines, idx):
    """idx 以降で最初の「構造として意味のある行」の位置。無ければ len(lines)。"""
    while idx < len(lines) and lines[idx].skip:
        idx += 1
    return idx


# ---------------------------------------------------------------- スカラー

def _strip_comment(s):
    """クォートの外にある ` #` 以降を落とす。"""
    quote = None
    i = 0
    while i < len(s):
        c = s[i]
        if quote:
            if c == "\\" and quote == '"':
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c == "#" and (i == 0 or s[i - 1] in " \t"):
            return s[:i].rstrip()
        i += 1
    return s.rstrip()


def _unquote(s, lineno):
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        body = s[1:-1]
        if s[0] == "'":
            return body.replace("''", "'")
        # ダブルクォートのエスケープは実際に使うものだけ。
        out = []
        i = 0
        while i < len(body):
            if body[i] == "\\" and i + 1 < len(body):
                nxt = body[i + 1]
                out.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(nxt, "\\" + nxt))
                i += 2
            else:
                out.append(body[i])
                i += 1
        return "".join(out)
    return s


def _split_top(s, lineno):
    """クォートと [] {} の入れ子を尊重してトップレベルのカンマで分割。"""
    parts, buf, depth, quote = [], [], 0, None
    i = 0
    while i < len(s):
        c = s[i]
        if quote:
            buf.append(c)
            if c == "\\" and quote == '"' and i + 1 < len(s):
                buf.append(s[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
            buf.append(c)
        elif c in "[{":
            depth += 1
            buf.append(c)
        elif c in "]}":
            depth -= 1
            if depth < 0:
                raise MiniYamlError("括弧の対応が取れていない", lineno)
            buf.append(c)
        elif c == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(c)
        i += 1
    if quote:
        raise MiniYamlError("クォートが閉じていない", lineno)
    if depth != 0:
        raise MiniYamlError("括弧の対応が取れていない", lineno)
    tail = "".join(buf).strip()
    if tail or parts:
        parts.append(tail)
    return [p for p in parts if p != ""] if parts == [""] else parts


def _split_key(s, lineno):
    """`key: value` を (key, value) に切る。値が無ければ value は None。

    クォートの外にある最初の `:` のうち、直後が空白か行末のものを境にする。
    `時刻: 00:21:10 - 00:34:52` の `00:21` で切れないのはこの条件のため。
    """
    quote = None
    i = 0
    while i < len(s):
        c = s[i]
        if quote:
            if c == "\\" and quote == '"':
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c == ":":
            if i + 1 == len(s):
                return _unquote(s[:i].strip(), lineno), None
            if s[i + 1] in " \t":
                return _unquote(s[:i].strip(), lineno), s[i + 1 :].strip()
        i += 1
    return None, None


def _parse_flow(s, lineno):
    """`[a, b]` / `{a: b}` を list / dict に。"""
    if s.startswith("["):
        if not s.endswith("]"):
            raise MiniYamlError("インラインシーケンスが閉じていない", lineno)
        return [_parse_scalar(p, lineno) for p in _split_top(s[1:-1].strip(), lineno)]
    if not s.endswith("}"):
        raise MiniYamlError("インラインマッピングが閉じていない", lineno)
    out = {}
    for part in _split_top(s[1:-1].strip(), lineno):
        key, value = _split_key(part, lineno)
        if key is None:
            raise MiniYamlError("インラインマッピングに `key: value` でない要素がある", lineno)
        out[key] = _parse_scalar(value, lineno) if value is not None else ""
    return out


def _parse_scalar(s, lineno):
    if s is None:
        return ""
    # 末尾コメントはどの形の値にも付きうる（`協力会社: []  # 社名を列挙` など）。
    # _strip_comment はクォートを尊重するので、先に一度だけ落としてよい。
    s = _strip_comment(s.strip())
    if s == "" or s in ("~", "null"):
        return ""
    if s[0] in "[{":
        return _parse_flow(s, lineno)
    if s[0] in "\"'":
        return _unquote(s, lineno)
    for prefix, message in _UNSUPPORTED_PREFIX:
        if s.startswith(prefix):
            raise MiniYamlError(message, lineno)
    return s


# ------------------------------------------------------------ ブロック

def _read_block_scalar(lines, idx, parent_indent, header, lineno):
    """`|` / `>` の本体を読む。idx は指示子の次の行を指している。"""
    m = _BLOCK_SCALAR.match(header)
    if not m:
        raise MiniYamlError("ブロックスカラーの指示子が読めない: %r" % header, lineno)
    folded = header[0] == ">"
    chomp = (m.group(1) or m.group(4) or "").strip()

    body, block_indent = [], None
    while idx < len(lines):
        line = lines[idx]
        if line.text == "":
            body.append("")
            idx += 1
            continue
        if line.indent <= parent_indent:
            break
        if block_indent is None:
            block_indent = line.indent
        body.append(line.raw[block_indent:] if len(line.raw) >= block_indent else "")
        idx += 1

    while body and body[-1] == "":
        body.pop()
    if folded:
        text = " ".join(x for x in body if x != "")
    else:
        text = "\n".join(body)
    if chomp != "-" and text:
        text += "\n"
    if chomp == "-":
        text = text.rstrip("\n")
    return text, idx


def _parse_block(lines, idx, indent):
    idx = _next_content(lines, idx)
    if idx >= len(lines):
        return "", idx
    m = _SEQ_ITEM.match(lines[idx].text)
    if m:
        return _parse_sequence(lines, idx, indent)
    return _parse_mapping(lines, idx, indent)


def _parse_mapping(lines, idx, indent):
    out = {}
    while True:
        idx = _next_content(lines, idx)
        if idx >= len(lines):
            break
        line = lines[idx]
        if line.indent < indent:
            break
        if line.indent > indent:
            raise MiniYamlError("インデントが揃っていない", line.no)
        if _SEQ_ITEM.match(line.text):
            break

        key, value = _split_key(line.text, line.no)
        if key is None:
            raise MiniYamlError("`key: value` の形になっていない: %r" % line.text, line.no)
        if key in out:
            raise MiniYamlError("キーが重複している: %s" % key, line.no)
        idx += 1

        if value is not None and value[:1] in ("|", ">"):
            out[key], idx = _read_block_scalar(lines, idx, indent, value, line.no)
            continue
        # `代替案:   # WinWin の option と同一概念` のように、値の位置に行末コメント
        # しか無い行がある。コメントを落としてから「値が無い」と判定しないと、
        # 続く子ブロックを取り落とす。
        if value is not None and _strip_comment(value) != "":
            out[key] = _parse_scalar(value, line.no)
            continue

        # 値が空。子ブロックがあるか覗く。
        nxt = _next_content(lines, idx)
        if nxt < len(lines) and lines[nxt].indent > indent:
            out[key], idx = _parse_block(lines, nxt, lines[nxt].indent)
        elif nxt < len(lines) and lines[nxt].indent == indent and _SEQ_ITEM.match(lines[nxt].text):
            # キーと同じインデントに置かれたシーケンス（YAML で有効）
            out[key], idx = _parse_sequence(lines, nxt, indent)
        else:
            out[key] = ""
    return out, idx


def _parse_sequence(lines, idx, indent):
    out = []
    while True:
        idx = _next_content(lines, idx)
        if idx >= len(lines):
            break
        line = lines[idx]
        if line.indent < indent:
            break
        if line.indent > indent:
            raise MiniYamlError("インデントが揃っていない", line.no)
        m = _SEQ_ITEM.match(line.text)
        if not m:
            break

        rest = (m.group("rest") or "").strip()
        if rest[:1] not in ("|", ">"):
            rest = _strip_comment(rest)
        idx += 1

        if rest == "":
            nxt = _next_content(lines, idx)
            if nxt < len(lines) and lines[nxt].indent > indent:
                value, idx = _parse_block(lines, nxt, lines[nxt].indent)
            else:
                value = ""
            out.append(value)
            continue

        key, _ = _split_key(rest, line.no)
        if key is not None and rest[0] not in "[{\"'":
            # `- 案: ...` から始まるマッピング。`-` の直後を仮想的な行頭として
            # 扱うため、この行を差し替えてから同じインデントで読み直す。
            offset = line.indent + (len(line.text) - len(line.text[1:].lstrip(" ")))
            lines[idx - 1] = _Line(" " * offset + rest, line.no)
            value, idx = _parse_mapping(lines, idx - 1, offset)
            out.append(value)
            continue

        out.append(_parse_scalar(rest, line.no))
    return out, idx


def parse(text):
    """YAML テキストを dict / list / str に。読めなければ MiniYamlError。"""
    lines = _scan(text)
    idx = _next_content(lines, 0)
    if idx >= len(lines):
        return {}
    if lines[idx].text == "---":
        idx = _next_content(lines, idx + 1)
        if idx >= len(lines):
            return {}
    for line in lines[idx:]:
        if not line.skip and line.text == "---":
            raise MiniYamlError("複数ドキュメント (---) は未対応", line.no)
    value, _ = _parse_block(lines, idx, lines[idx].indent)
    return value


def split_frontmatter(text):
    """`---` で囲まれた frontmatter と本文を (fm_text, body, start_line) に分ける。

    frontmatter が無ければ (None, text, 0)。
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text, 0
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1 :]), 1
    return None, text, 0


def parse_frontmatter_block(text):
    """カードの frontmatter を (dict, body) に。読めなければ MiniYamlError。

    行番号はファイル先頭からの通し番号に補正する（`---` の分だけずれるため）。
    """
    fm_text, body, offset = split_frontmatter(text)
    if fm_text is None:
        raise MiniYamlError("frontmatter (--- で囲まれた領域) が無い")
    try:
        data = parse(fm_text)
    except MiniYamlError as exc:
        raise MiniYamlError(str(exc).split("行目: ", 1)[-1],
                            (exc.line + offset) if exc.line else None) from None
    if not isinstance(data, dict):
        raise MiniYamlError("frontmatter がマッピングになっていない")
    return data, body
