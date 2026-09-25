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
        self.common_fields = data.get("common-fields", {})
        self.fields = {t: {name: self._resolve_field(t, name, spec) for name, spec in specs.items()}
                       for t, specs in data.get("fields", {}).items()}
        self.structs = data.get("structs", {})
        self.status_implications = data.get("status-implications", [])
        self.derivations = data.get("derivations", {})
        self.meeting_date_anchors = data.get("meeting-date-anchors", {})
        self.editions = data.get("editions", {})
        self.thresholds = data.get("thresholds", {})
        self.signpost_vague_words = data.get("signpost-vague-words", [])
        self.deferral_phrases = data.get("deferral-phrases", [])
        self.assumption_trigger_words = data.get("assumption-trigger-words", [])
        self.unverified_confidence = data.get("unverified-confidence", "")
        self.no_record_value = data.get("no-record-value", "")
        self.unknown_value = data.get("unknown-value", "")
        self.files = data.get("files", {})
        self.scope_question = data.get("scope-question", {})
        self.agenda = data.get("agenda", {})
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

    def _resolve_field(self, type_name, name, spec):
        """`名前: common` を common-fields の定義に展開する。

        `{ common: true, required: false }` なら、共通の定義に書いた項目だけを上書きする。
        """
        if spec == "common":
            override = {}
        elif isinstance(spec, dict) and str(spec.get("common", "")).lower() == "true":
            override = {k: v for k, v in spec.items() if k != "common"}
        else:
            return spec
        if name not in self.common_fields:
            raise SchemaError("%s.%s は common だが common-fields に無い" % (type_name, name))
        return {**self.common_fields[name], **override}

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
        return self.quote_field(type_name) is not None

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

    def ref_targets(self, type_name, field_name):
        """参照フィールドが指してよい型のリスト。"""
        ref = (self.field(type_name, field_name) or {}).get("ref", [])
        return list(ref) if isinstance(ref, list) else [ref]

    def ref_fields(self, type_name):
        """(フィールド名, 参照先型のリスト) を返す。ref / ref-list の両方。"""
        return [(name, self.ref_targets(type_name, name))
                for name, spec in self.field_specs(type_name).items()
                if spec.get("kind") in ("ref", "ref-list")]

    # ------------------------------------------------------------ 導出

    def derive_hardness(self, kind, location):
        """種類 × 所在 から硬度を導く。表に無い組み合わせは None。"""
        table = (self.derivations.get("硬度") or {}).get("table", {})
        return table.get("%s/%s" % (kind, location)) or None

    def hardness_table(self):
        return (self.derivations.get("硬度") or {}).get("table", {})

    def role_derivation(self, field):
        """role-mapping から引くフィールドの (引く先のキー, 取り出す欄)。

        `種別` なら (決定の所在, 決定の種別)。role-mapping を引かない
        フィールドなら None。
        """
        spec = self.derivations.get(field) or {}
        if spec.get("from") != "role-mapping":
            return None
        return spec.get("key"), spec.get("source-field")

    def role_derived_fields(self):
        return [name for name in self.derivations
                if (self.derivations[name] or {}).get("from") == "role-mapping"]

    # -------------------------------------------------- カードと会議の日付

    def date_anchor(self, type_name, which):
        """その型で「最初の会議日 / 最新の会議日」に対応するフィールド名。

        Q なら first=初出 / last=最終言及。持たない型は None。
        """
        return (self.meeting_date_anchors.get(type_name) or {}).get(which) or None


    # ------------------------------------------------------------ 閾値

    def threshold(self, name):
        try:
            return int(self.thresholds[name])
        except KeyError:
            raise SchemaError("未知の閾値: %s" % name) from None

    # ------------------------------------------------------------ 版

    def sections_of(self, edition_name):
        """その版の節構成。[(見出し, 注記), ...]。"""
        out = []
        for row in self.edition(edition_name).get("sections", []):
            if isinstance(row, dict):
                out.append((row.get("title", ""), row.get("note", "")))
            elif row:
                out.append((str(row), ""))
        return out

    def agenda_sections(self):
        """次回アジェンダの節構成。[(キー, 見出し, 注記), ...]。"""
        return [(row.get("key", ""), row.get("title", ""), row.get("note", ""))
                for row in self.agenda.get("sections", []) if isinstance(row, dict)]

    def closed_status(self, type_name):
        """その型の閉じた status。宣言の無い型は空（開閉を持たない）。"""
        return list(self.spec(type_name).get("closed-status", []))

    def is_open(self, type_name, status):
        """その status が開いている（アジェンダに持ち越す・lint が追う）か。"""
        return status not in self.closed_status(type_name)

    def is_active(self, type_name, status):
        """その status が現に効いているか（DEC はみなし確定の対象、ASM は棚卸しの対象）。"""
        return status in self.spec(type_name).get("active-status", [])

    def tracked_vulnerability(self):
        """棚卸しで追う前提の `脆弱性`。"""
        return list(self.spec("ASM").get("tracked-vulnerability", []))

    def extract_kinds(self):
        """Pass 3 が最低1件を出す LOG の `種別`（欠落ガード）。"""
        return list(self.spec("LOG").get("extract-kinds", []))

    # ------------------------------------------------------------ 周辺ファイル

    def file_keys(self, file_name):
        """周辺ファイルのキー宣言。{キー: {in, description, enum?, grants?}}。"""
        try:
            return self.files[file_name].get("keys", {})
        except KeyError:
            raise SchemaError("未知の周辺ファイル: %s" % file_name) from None

    def grants_authority(self, role_info):
        """role-mapping の役割の属性が、DEC を確定してよい決定権を持つか。"""
        spec = self.file_keys("role-mapping").get("決定権", {})
        return bool(spec.get("grants")) and (role_info or {}).get("決定権") == spec["grants"]

    def scope_question_value(self, key):
        """`scope-question` の値。宣言が無ければ止める（既定値で黙って動かさない）。"""
        try:
            return self.scope_question[key]
        except (KeyError, TypeError):
            raise SchemaError("scope-question.%s が無い" % key) from None

    def is_meeting_id(self, value):
        return bool(value) and bool(self._meeting_re.match(value))

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
