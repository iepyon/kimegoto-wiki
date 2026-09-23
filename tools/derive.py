#!/usr/bin/env python3
"""導出フィールドの適用 — `ontology.yaml` の `derivations` を実行する。

これまで `derivations` は **lint が事後照合するだけ**で、値そのものは LLM が
書いていた。役割から `種別` を引く、`種類` × `所在` から `硬度` を決める、といった
一意に定まる写像を LLM にやらせると、ときどき静かに間違う。しかも lint は
「食い違っている」としか言えず、正しい値を入れ直すのは人間の仕事になる。

**機械が書き、lint は保険として残す。** ここはその「機械が書く」側。

推測はしない。role-mapping に無い役割、表に無い組み合わせは**埋めずに空欄で返す**
（空欄は情報であり、埋めるべき穴ではない）。
"""

from tools.schema import Ontology  # noqa: F401  （型の見通しのため）


def _role_field(wiki, role, source_field):
    """role-mapping の1欄。未登録の役割からは引かない。"""
    if not role or not wiki.is_known_role(role):
        return ""
    return (wiki.role(role) or {}).get(source_field, "") or ""


def derived_fields(wiki, type_name, role="", log="", meeting="", kind="", today=""):
    """機械的に決まるフィールドを {名前: 値} で返す。

    引けなかったものはキーごと返さない（`kime new` が雛形の空欄を残す）。
    第2の戻り値は人間に見せる注意書き。
    """
    o = wiki.ontology
    fields, notes = {}, []

    date = wiki.meetings[meeting].date if meeting in wiki.meetings else ""
    known = bool(role) and wiki.is_known_role(role)
    if role and not known:
        notes.append("役割 `%s` は role-mapping.yaml に無い。"
                     "決定権「なし」として扱い、役割から引くフィールドは空欄にした" % role)

    if log:
        fields["derived_from"] = "[%s]" % log
        # 論点に付いた議題を子カードへ写す。Pass 1 が付けたものだけで、推測はしない。
        agenda = wiki.segment_agenda(log) if type_name in ("DEC", "Q", "ACT") else ""
        if agenda:
            if wiki.get(agenda) is not None and wiki.get(agenda).type == "AGD":
                fields["議題"] = agenda
            else:
                notes.append("segments.yaml の議題 `%s` が無い。`議題` は空欄にした" % agenda)
    if type_name == "LOG" and meeting:
        fields["meeting"] = meeting

    if type_name == "AGD":
        # 会議の前に起票されるので、会議の実在を見ない（予定会議は未来でよい）。
        if role:
            fields["提起者"] = role
        if today:
            fields["提起日"] = today
        if meeting:
            fields["予定会議"] = "[%s]" % meeting

    elif type_name == "DEC":
        if role:
            fields["決定の所在"] = role
        if date:
            fields["決定日"] = date
        body = (wiki.meta or {}).get("会議体", "")
        if body:
            fields["会議体"] = body
        key, source = o.role_derivation("種別") or ("", "")
        if source:
            value = _role_field(wiki, role, source)
            if value:
                fields["種別"] = value
        if known and (wiki.role(role) or {}).get("決定権") != "あり":
            notes.append("役割 `%s` は決定権が「あり」ではない。"
                         "この発言だけで DEC を起票しない — Q に落とす" % role)

    elif type_name == "Q":
        if role:
            fields["確認先"] = role
        if date:
            fields["初出"] = date
            fields["最終言及"] = date

    elif type_name == "ACT":
        company = _role_field(wiki, role, "社名")
        if company:
            fields["担当"] = company

    elif type_name == "TERM":
        if log:
            fields["初出"] = log

    elif type_name == "CON":
        _, source = o.role_derivation("所在") or ("", "")
        location = _role_field(wiki, role, source) if source else ""
        if location:
            fields["所在"] = location
        if kind:
            fields["種類"] = kind
        if kind and location:
            hardness = o.derive_hardness(kind, location)
            if hardness:
                fields["硬度"] = hardness
            else:
                notes.append("`%s` × `%s` は導出表にない組み合わせ。"
                             "`硬度` は空欄のままにした（ontology.yaml の derivations を見る）"
                             % (kind, location))

    return fields, notes
