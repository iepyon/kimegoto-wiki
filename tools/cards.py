#!/usr/bin/env python3
"""記録層 — Markdown カードの読み込み。

カードは1件1ファイル。frontmatter が構造、本文が散文。DB は持たない。

**素の文字列契約**: `Card.data` の値はすべて str / list / dict のいずれかで、
`None` は入らない（空欄は `""`）。下流が型で分岐せずに済むようにするため。
配列は list、構造化フィールドは list of dict のまま保つ。

**壊れた frontmatter を握りつぶさない**: 読めなかったカードは `error` を持つ
Card として残す。捨てると「そのカードは存在しない」ことになり、参照整合の
チェックが無関係な error を量産する。1件で名指しして、そのカードのスキーマ系
チェックだけを飛ばす。
"""

import os
import re
from functools import cached_property
from pathlib import Path

from tools import schema
from tools.miniyaml import MiniYamlError, parse, parse_frontmatter_block

# LOG 本文の発言行。`- **顧客PM**: ADに繋ぐのは…`
# `- **(沈黙 約6秒)**` のような注記は役割ではないので拾わない。
UTTERANCE = re.compile(r"^\s*-\s*\*\*(?P<role>[^*]+?)\*\*\s*[:：]\s*(?P<text>.+?)\s*$")
ANNOTATION = re.compile(r"^\s*-\s*\*\*\(.+\)\*\*\s*$")


class Card:
    """1枚のカード。"""

    # __slots__ は使わない（cached_property が __dict__ を必要とするため）。

    def __init__(self, path, type_name, card_id, data, body, error=None):
        self.path = path
        self.type = type_name
        self.id = card_id
        self.data = data
        self.body = body
        self.error = error
        self._mtime = None

    def __repr__(self):
        return "<Card %s %s>" % (self.type, self.id)

    def get(self, name, default=""):
        value = self.data.get(name, default)
        return default if value is None else value

    def list(self, name):
        """ref-list / str-list を必ず list で返す。"""
        value = self.data.get(name, [])
        if isinstance(value, list):
            return value
        if value == "":
            return []
        return [value]

    def structs(self, name):
        """struct-list を必ず list of dict で返す。形が違う要素は落とさず残す。"""
        value = self.data.get(name, [])
        if isinstance(value, list):
            return value
        return [] if value == "" else [value]

    @property
    def filename_id(self):
        return self.path.stem

    @property
    def mtime(self):
        if self._mtime is None:
            self._mtime = self.path.stat().st_mtime
        return self._mtime

    def headline(self, ontology):
        """見出し。型ごとに title だったり 内容 だったりする。"""
        return self.get(ontology.headline_field(self.type)) or self.id

    @cached_property
    def utterances(self):
        """LOG 本文の発言。[(役割, 発言), ...]。LOG 以外では空。"""
        if self.type != "LOG":
            return []
        out = []
        for line in self.body.splitlines():
            m = UTTERANCE.match(line)
            if m:
                out.append((m.group("role").strip(), m.group("text").strip()))
        return out

    @cached_property
    def malformed_utterance_lines(self):
        """`## 発言` 節にあるが発言行の形になっていない行。[(行番号, 内容), ...]。"""
        if self.type != "LOG":
            return []
        out, in_section = [], False
        offset = len(self.body.splitlines()) - len(self.body.splitlines())
        for i, line in enumerate(self.body.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("## "):
                in_section = stripped == "## 発言"
                continue
            if not in_section or stripped == "":
                continue
            if not stripped.startswith("-"):
                continue
            if UTTERANCE.match(line) or ANNOTATION.match(line):
                continue
            out.append((i + offset, stripped))
        return out


class Meeting:
    """1回の会議。カードではないが、カードの入れ物として扱う。"""

    __slots__ = ("id", "dir", "_ontology")

    def __init__(self, meeting_id, directory, ontology):
        self.id = meeting_id
        self.dir = directory
        self._ontology = ontology

    def __repr__(self):
        return "<Meeting %s>" % self.id

    @property
    def date(self):
        """MTG-20260918 → 2026-09-18。"""
        digits = self.id.split("-")[-1]
        return "%s-%s-%s" % (digits[0:4], digits[4:6], digits[6:8])

    @property
    def transcript_path(self):
        return self.dir / self._ontology.meetings.get("transcript", "transcript.md")

    @property
    def segments_path(self):
        return self.dir / self._ontology.meetings.get("segments", "segments.yaml")

    @property
    def candidates_path(self):
        return self.dir / self._ontology.meetings.get("candidates", "promote-candidates.yaml")

    @property
    def logs_dir(self):
        return self.dir / self._ontology.meetings.get("logs-dir", "logs")


def parse_card(path, ontology):
    """1ファイルを Card にする。読めなければ error 付きの Card。"""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    card_id = path.stem
    type_name = ontology.type_of_id(card_id)
    try:
        data, body = parse_frontmatter_block(text)
    except MiniYamlError as exc:
        return Card(path, type_name, card_id, {}, text, error=exc)
    # frontmatter の id を優先する。ファイル名との不一致は lint が拾う。
    declared = data.get("id", "")
    if declared and ontology.type_of_id(declared):
        type_name = ontology.type_of_id(declared)
    return Card(path, type_name, card_id, data, body)


class Wiki:
    """1案件分のカード群。"""

    def __init__(self, root, ontology=None):
        self.root = Path(root).resolve()
        self.ontology = ontology or schema.load()
        if not self.root.is_dir():
            raise FileNotFoundError("案件ディレクトリが無い: %s" % self.root)

    def __repr__(self):
        return "<Wiki %s>" % self.root

    # ------------------------------------------------------------ 走査

    @cached_property
    def _scanned(self):
        cards, stray = [], []
        for type_name in self.ontology.type_names():
            for path in self._paths_for(type_name):
                card = parse_card(path, self.ontology)
                if card.type is None:
                    stray.append(path)
                    continue
                cards.append(card)
        cards.sort(key=lambda c: (c.type, c.id))
        return cards, stray

    def _paths_for(self, type_name):
        if self.ontology.spec(type_name).get("nested-under") == "meetings":
            logs_dir = self.ontology.meetings.get("logs-dir", "logs")
            base = self.root / self.ontology.meetings.get("dir", "meetings")
            if not base.is_dir():
                return []
            return sorted(base.glob("*/%s/*.md" % logs_dir))
        directory = self.root / self.ontology.dir_of(type_name)
        if not directory.is_dir():
            return []
        return sorted(p for p in directory.glob("*.md") if p.name != "README.md")

    @property
    def cards(self):
        return self._scanned[0]

    @property
    def stray(self):
        """型ディレクトリに置かれているが ID がどの型にも当たらないファイル。"""
        return self._scanned[1]

    @cached_property
    def broken(self):
        return [c for c in self.cards if c.error is not None]

    @cached_property
    def _by_id(self):
        out = {}
        for card in self.cards:
            out.setdefault(card.id, card)
        return out

    @cached_property
    def _by_type(self):
        out = {t: [] for t in self.ontology.type_names()}
        for card in self.cards:
            out.setdefault(card.type, []).append(card)
        return out

    def by_type(self, *type_names):
        out = []
        for type_name in type_names:
            out.extend(self._by_type.get(type_name, []))
        return out

    def get(self, card_id):
        return self._by_id.get(card_id)

    def exists(self, card_id):
        return card_id in self._by_id or card_id in self._meeting_ids

    def counts(self):
        return {t: len(self._by_type.get(t, [])) for t in self.ontology.type_names()}

    def next_id(self, type_name):
        """採番は最大値+1。取り下げた番号は欠番のまま残す（再利用しない）。"""
        numbers = [self.ontology.id_number(c.id) for c in self.by_type(type_name)]
        numbers = [n for n in numbers if n is not None]
        width = 3
        return "%s-%0*d" % (type_name, width, (max(numbers) if numbers else 0) + 1)

    # ------------------------------------------------------------ 会議

    @cached_property
    def meetings(self):
        base = self.root / self.ontology.meetings.get("dir", "meetings")
        if not base.is_dir():
            return {}
        out = {}
        for directory in sorted(p for p in base.iterdir() if p.is_dir()):
            if self.ontology.type_of_id(directory.name) == "MTG":
                out[directory.name] = Meeting(directory.name, directory, self.ontology)
        return out

    @cached_property
    def _meeting_ids(self):
        return set(self.meetings)

    def meetings_of(self, card):
        """そのカードが現れた会議の集合（古い順）。

        カード ↔ 会議は多対多なので、単一の値では表せない。derived_from の
        LOG を辿って得る。LOG 自身は meeting を直接持つ。
        """
        if card.type == "LOG":
            meeting = card.get("meeting")
            return [meeting] if meeting else []
        found = []
        for ref in card.list("derived_from"):
            log = self.get(ref)
            if log is None or log.type != "LOG":
                continue
            meeting = log.get("meeting")
            if meeting and meeting not in found:
                found.append(meeting)
        return sorted(found)

    def cards_of_meeting(self, meeting_id, *types):
        """その会議で生成または更新されたカード。

        1枚のカードが複数の会議に現れるのは正常（更新されたということ）。
        """
        pool = self.by_type(*types) if types else self.cards
        return [c for c in pool
                if c.error is None and meeting_id in self.meetings_of(c)]

    def logs_of(self, meeting_id):
        return [c for c in self.by_type("LOG") if c.get("meeting") == meeting_id]

    def latest_meeting(self):
        return self.meetings[max(self.meetings)] if self.meetings else None

    # ------------------------------------------------------ role-mapping

    @cached_property
    def role_mapping(self):
        path = self.root / "role-mapping.yaml"
        if not path.exists():
            path = schema.KIT_ROOT / "role-mapping.yaml"
        if not path.exists():
            return {}
        try:
            data = parse(path.read_text(encoding="utf-8"))
        except MiniYamlError:
            return {}
        return data if isinstance(data, dict) else {}

    @property
    def roles(self):
        return self.role_mapping.get("roles", {})

    @property
    def meta(self):
        return self.role_mapping.get("meta", {})

    def role(self, name):
        """未登録の役割は unknown_role_default にフォールバックする。"""
        if name in self.roles:
            return self.roles[name]
        return self.role_mapping.get("unknown_role_default", {})

    def is_known_role(self, name):
        return name in self.roles

    @cached_property
    def companies(self):
        """ACT の `担当` に入りうる社名の集合。"""
        meta = self.meta
        out = set()
        for key in ("自社", "顧客"):
            if meta.get(key):
                out.add(meta[key])
        partners = meta.get("協力会社", [])
        out.update(partners if isinstance(partners, list) else [partners])
        for role in self.roles.values():
            if role.get("社名"):
                out.add(role["社名"])
        return {c for c in out if c}

    # ------------------------------------------------------------ 引用

    @cached_property
    def utterances_by_log(self):
        return {c.id: c.utterances for c in self.by_type("LOG")}

    # ------------------------------------------------------------ ビュー

    @property
    def views_dir(self):
        return self.root / "views"

    def newest_card_mtime(self):
        return max((c.mtime for c in self.cards), default=0.0)


def resolve_root(explicit=None):
    """対象の案件ディレクトリを決める。

    優先順: 明示指定 > 環境変数 GIJI_ROOT > .env の CURRENT_PROJECT > projects/example
    """
    if explicit:
        return Path(explicit).resolve()
    env = os.environ.get("GIJI_ROOT")
    if env:
        return Path(env).resolve()
    slug = _current_project()
    candidate = schema.KIT_ROOT / "projects" / slug
    if candidate.is_dir():
        return candidate.resolve()
    return Path.cwd().resolve()


def _current_project():
    """.env の CURRENT_PROJECT。外部依存を持たないための最小パーサ。"""
    path = schema.KIT_ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key.strip() == "CURRENT_PROJECT":
                return value.strip().strip("\"'")
    return "example"


# ---------------------------------------------------------------- 書き出し

# クォートが要る値。コロンを含むもの（`00:21:10` のように読めるものも安全側に
# 倒してクォートする）、`#` を含むもの、行頭が記号のもの、前後に空白があるもの。
_NEEDS_QUOTE = re.compile(r"[:]|(\s#)|^[\s\-\[\]{}>|*&!?%@`\"']|\s$|^$")


def _scalar(value):
    text = "" if value is None else str(value)
    if text == "":
        return ""
    if _NEEDS_QUOTE.search(text):
        return '"%s"' % text.replace("\\", "\\\\").replace('"', '\\"')
    return text


def dump_frontmatter(data, order=None):
    """dict を frontmatter の本体（`---` は含まない）にする。

    `giji new` の雛形出力に使う。既存カードの書き換えには使わない
    （コメントと空欄の順序が失われるため。書き換えは行単位で行う）。
    """
    lines = []
    keys = list(order) if order else list(data)
    for key in keys:
        if order and key not in data:
            continue
        value = data[key]
        if isinstance(value, list):
            if not value:
                lines.append("%s: []" % key)
            elif all(isinstance(v, dict) for v in value):
                lines.append("%s:" % key)
                for item in value:
                    first = True
                    for k, v in item.items():
                        prefix = "  - " if first else "    "
                        lines.append("%s%s: %s" % (prefix, k, _scalar(v)))
                        first = False
            else:
                lines.append("%s: [%s]" % (key, ", ".join(_scalar(v) for v in value)))
        elif isinstance(value, dict):
            lines.append("%s:" % key)
            for k, v in value.items():
                lines.append("  %s: %s" % (k, _scalar(v)))
        else:
            rendered = _scalar(value)
            lines.append("%s: %s" % (key, rendered) if rendered else "%s:" % key)
    return "\n".join(lines)


def render_card(data, body="", order=None):
    """frontmatter + 本文のカード1枚分のテキスト。"""
    out = "---\n%s\n---\n" % dump_frontmatter(data, order)
    if body:
        out += "\n%s" % body.lstrip("\n")
        if not out.endswith("\n"):
            out += "\n"
    return out
