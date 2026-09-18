#!/usr/bin/env python3
"""ontology.yaml のローダ。

型・フィールド・語彙・関係・導出・閾値の問い合わせ口を1箇所にまとめる。
lint もビューも生成器も、スキーマを知りたいときは必ずここを通る。
コードに語彙や閾値を直書きしない（正本は ontology.yaml）。
"""

import re
from pathlib import Path

from tools.miniyaml import MiniYamlError, parse

ONTOLOGY_FILENAME = "ontology.yaml"

# キットのルート（このファイルの1つ上）
KIT_ROOT = Path(__file__).resolve().parent.parent


class SchemaError(Exception):
    pass


class Ontology:
    def __init__(self, data, path):
        self.path = path
        self._d = data
        self.version = data.get("version", "")
        self.types = data.get("types", {})
        self.meetings = data.get("meetings", {})
        self.enums = data.get("enums", {})
        self.fields = data.get("fields", {})
        self.structs = data.get("structs", {})
        self.relations = data.get("relations", {})
        self.status_implications = data.get("status-implications", [])
        self.derivations = data.get("derivations", {})
        self.derived_relations = data.get("derived-relations", {})
        self.editions = data.get("editions", {})
        self.thresholds = data.get("thresholds", {})
        self.signpost_vague_words = data.get("signpost-vague-words", [])
        self.deferral_phrases = data.get("deferral-phrases", [])
        self._id_res = {t: re.compile(spec["id"]) for t, spec in self.types.items()}
        self._meeting_re = re.compile(self.meetings.get("id", "^MTG-"))

    # ------------------------------------------------------------ 型

    def type_names(self):
        return list(self.types)

    def spec(self, type_name):
        try:
            return self.types[type_name]
        except KeyError:
            raise SchemaError("未知の型: %s" % type_name) from None

    def label(self, type_name):
        return self.spec(type_name).get("label", type_name)

    def headline_field(self, type_name):
        """そのカードの見出しになるフィールド名（DEC は title、CON は 内容）。"""
        return self.spec(type_name).get("headline", "title")

    def dir_of(self, type_name):
        return self.spec(type_name).get("dir", "")

    def layer(self, type_name):
        return self.spec(type_name).get("layer", "")

    def type_of_id(self, card_id):
        """ID から型を判定する。どの型にも当たらなければ None。"""
        if not card_id:
            return None
        if self._meeting_re.match(card_id):
            return "MTG"
        for type_name, pattern in self._id_res.items():
            if pattern.match(card_id):
                return type_name
        return None

    def id_number(self, card_id):
        """採番に使う末尾の数値。取れなければ None。"""
        m = re.search(r"(\d+)$", card_id or "")
        return int(m.group(1)) if m else None

    # -------------------------------------------------------- フィールド

    def field_specs(self, type_name):
        return self.fields.get(type_name, {})

    def field(self, type_name, name):
        return self.field_specs(type_name).get(name)

    def required_fields(self, type_name):
        return [n for n, s in self.field_specs(type_name).items()
                if str(s.get("required", "")).lower() == "true"]

    def fields_of_kind(self, type_name, kind):
        return [n for n, s in self.field_specs(type_name).items() if s.get("kind") == kind]

    def quote_field(self, type_name):
        names = self.fields_of_kind(type_name, "quote")
        return names[0] if names else None

    def has_quote(self, type_name):
        return str(self.spec(type_name).get("has-quote", "")).lower() == "true"

    # ------------------------------------------------------------ 語彙

    def enum_values(self, enum_name):
        try:
            return self.enums[enum_name]
        except KeyError:
            raise SchemaError("未知の語彙: %s" % enum_name) from None

    def enum_for(self, type_name, field_name):
        spec = self.field(type_name, field_name) or {}
        name = spec.get("enum")
        return self.enum_values(name) if name else None

    def allows_free_text(self, type_name, field_name):
        spec = self.field(type_name, field_name) or {}
        return str(spec.get("free", "")).lower() == "true"

    # ------------------------------------------------------------ 関係

    def relation(self, name):
        return self.relations.get(name)

    def relation_range(self, name):
        rel = self.relations.get(name) or {}
        rng = rel.get("range", [])
        return rng if isinstance(rng, list) else [rng]

    def inverse_of(self, name):
        rel = self.relations.get(name) or {}
        return rel.get("inverse") or None

    def ref_fields(self, type_name):
        """(フィールド名, 参照先型のリスト) を返す。ref / ref-list の両方。"""
        out = []
        for name, spec in self.field_specs(type_name).items():
            if spec.get("kind") not in ("ref", "ref-list"):
                continue
            ref = spec.get("ref", "")
            if ref == "any":
                targets = self.type_names() + ["MTG"]
            else:
                targets = self.relation_range(name) or [ref]
            out.append((name, targets))
        return out

    # ------------------------------------------------------------ 導出

    def derive_hardness(self, kind, location):
        """種類 × 所在 から硬度を導く。表に無い組み合わせは None。"""
        table = (self.derivations.get("硬度") or {}).get("table", {})
        return table.get("%s/%s" % (kind, location)) or None

    def hardness_table(self):
        return (self.derivations.get("硬度") or {}).get("table", {})

    # -------------------------------------------------- 導出される関係

    def meeting_relation(self):
        """カード ↔ 会議（多対多）の宣言。"""
        return self.derived_relations.get("会議", {})

    def date_anchor(self, type_name, which):
        """その型で「最初の会議日 / 最新の会議日」に対応するフィールド名。

        Q なら first=初出 / last=最終言及。持たない型は None。
        """
        anchors = (self.meeting_relation().get("date-anchors") or {}).get(type_name, {})
        return anchors.get(which) or None

    def types_with_meetings(self):
        return self.meeting_relation().get("domain", [])

    # ------------------------------------------------------------ 閾値

    def threshold(self, name):
        try:
            return int(self.thresholds[name])
        except KeyError:
            raise SchemaError("未知の閾値: %s" % name) from None

    # ------------------------------------------------------------ 版

    def edition(self, name):
        try:
            return self.editions[name]
        except KeyError:
            raise SchemaError("未知の版: %s" % name) from None

    def edition_names(self):
        return list(self.editions)


_cache = {}


def load(path=None):
    """ontology.yaml を読む。同じパスは読み直さない。"""
    target = Path(path) if path else KIT_ROOT / ONTOLOGY_FILENAME
    target = target.resolve()
    if target in _cache:
        return _cache[target]
    if not target.exists():
        raise SchemaError("%s が見つからない" % target)
    try:
        data = parse(target.read_text(encoding="utf-8"))
    except MiniYamlError as exc:
        raise SchemaError("%s が読めない: %s" % (target.name, exc)) from None
    if not isinstance(data, dict):
        raise SchemaError("%s がマッピングになっていない" % target.name)
    ontology = Ontology(data, target)
    _cache[target] = ontology
    return ontology
