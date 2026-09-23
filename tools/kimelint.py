#!/usr/bin/env python3
"""決定論 lint — 規約を機械的に守らせる。

設計の原則3つ。

1. **検出だけ。ファイルを書き換えない。** 降格の書き戻しは
   `kime verify-quotes --fix` にしかない。lint が黙って直すと、人間が
   「何が起きたか」を見ないまま通過してしまう。

2. **非対称。** 慎重側への倒し（`推測` を名乗る、空欄のままにする）は止めない。
   止めるのは確証の水増しだけ。機械は疑うことを邪魔しない。

3. **warning 0 を目指さない。** `act-overdue` や `q-stale` は真の未達を映す
   計器であって、消すものではない。error 0 だけを不変条件にする。

閾値と語彙はこのファイルに書かない。正本は ontology.yaml。
"""

import argparse
import datetime
import json
import re
import sys

from tools import quotes, schema
from tools.cards import Wiki, resolve_root

ERROR = "error"
WARNING = "warning"


class Problem:
    __slots__ = ("level", "check", "where", "message")

    def __init__(self, level, check, where, message):
        self.level = level
        self.check = check
        self.where = where
        self.message = message

    def __repr__(self):
        return "<%s %s %s>" % (self.level, self.check, self.where)

    def as_dict(self):
        return {"level": self.level, "check": self.check,
                "where": self.where, "message": self.message}


class Context:
    """1回の lint 実行が参照するもの。"""

    def __init__(self, wiki, today=None):
        self.wiki = wiki
        self.o = wiki.ontology
        self.today = today or datetime.date.today()

    @property
    def sound(self):
        """frontmatter が読めたカードだけ。壊れたカードは巻き添えにしない。"""
        return [c for c in self.wiki.cards if c.error is None]

    def of_type(self, *types):
        return [c for c in self.sound if c.type in types]

    def date(self, card, field):
        """日付フィールドを date で。読めなければ None。"""
        raw = (card.get(field) or "").strip()
        try:
            return datetime.date.fromisoformat(raw)
        except ValueError:
            return None

    def days_since(self, card, field):
        d = self.date(card, field)
        return None if d is None else (self.today - d).days


CHECKS = []


def check(check_id, level):
    """チェック関数を登録するデコレータ。"""
    def wrap(func):
        func.check_id = check_id
        func.level = level
        CHECKS.append(func)
        return func
    return wrap


def _p(func, where, message, level=None):
    return Problem(level or func.level, func.check_id, where, message)


# ============================================================ スキーマ層

@check("frontmatter", ERROR)
def check_frontmatter(ctx):
    """frontmatter が読めない。1件で名指しし、他のチェックは巻き添えにしない。"""
    return [_p(check_frontmatter, c.id, "frontmatter が読めない: %s" % c.error)
            for c in ctx.wiki.broken] + \
           [_p(check_frontmatter, str(p.relative_to(ctx.wiki.root)),
               "ID がどの型にも当たらない")
            for p in ctx.wiki.stray]


@check("id-filename", ERROR)
def check_id_filename(ctx):
    """ID = ファイル名 = frontmatter の id を三者一致させる。"""
    out = []
    for c in ctx.sound:
        declared = c.get("id")
        if declared != c.filename_id:
            out.append(_p(check_id_filename, c.filename_id,
                          "ファイル名と frontmatter の id が違う（id: %s）" % (declared or "空")))
    return out


@check("dir-placement", ERROR)
def check_dir_placement(ctx):
    """type と置き場ディレクトリの対応。"""
    out = []
    for c in ctx.sound:
        expected = ctx.o.spec(c.type).get("type-value")
        actual = c.get("type")
        if actual != expected:
            out.append(_p(check_dir_placement, c.id,
                          "type が `%s` になっている（`%s` のはず）" % (actual or "空", expected)))
        if ctx.o.spec(c.type).get("nested-under") == "meetings":
            continue
        if c.path.parent.name != ctx.o.dir_of(c.type):
            out.append(_p(check_dir_placement, c.id,
                          "%s/ に置くべきカードが %s/ にある" % (ctx.o.dir_of(c.type), c.path.parent.name)))
    return out


@check("required-field", ERROR)
def check_required_field(ctx):
    """必須フィールドが空。"""
    out = []
    for c in ctx.sound:
        for name in ctx.o.required_fields(c.type):
            value = c.data.get(name, "")
            if value == "" or value == []:
                out.append(_p(check_required_field, c.id, "必須フィールド `%s` が空" % name))
    return out


@check("unknown-field", WARNING)
def check_unknown_field(ctx):
    """宣言にないキー。ほとんどはタイポ。"""
    out = []
    for c in ctx.sound:
        declared = set(ctx.o.field_specs(c.type))
        for name in c.data:
            if name not in declared:
                out.append(_p(check_unknown_field, c.id, "宣言にないキー `%s`" % name))
    return out


@check("vocab", ERROR)
def check_vocab(ctx):
    """語彙の外の値。"""
    out = []
    for c in ctx.sound:
        for name, spec in ctx.o.field_specs(c.type).items():
            if spec.get("enum") is None:
                continue
            value = c.get(name)
            if value == "" or ctx.o.allows_free_text(c.type, name):
                continue
            allowed = ctx.o.enum_values(spec["enum"])
            if value not in allowed:
                out.append(_p(check_vocab, c.id,
                              "`%s` の値 `%s` は語彙にない（%s）" % (name, value, " / ".join(allowed))))
    return out


@check("date-format", ERROR)
def check_date_format(ctx):
    """日付が YYYY-MM-DD でない。"""
    out = []
    for c in ctx.sound:
        for name in ctx.o.fields_of_kind(c.type, "date"):
            raw = (c.get(name) or "").strip()
            if raw and ctx.date(c, name) is None:
                out.append(_p(check_date_format, c.id,
                              "`%s` が YYYY-MM-DD でない: %s" % (name, raw)))
    return out


@check("struct-shape", ERROR)
def check_struct_shape(ctx):
    """構造化フィールドの行の形。キー過剰は warning に落とす。"""
    out = []
    for c in ctx.sound:
        for name, spec in ctx.o.field_specs(c.type).items():
            if spec.get("kind") != "struct-list":
                continue
            struct = ctx.o.structs.get(spec.get("struct"), {})
            keys = struct.get("keys", [])
            required = struct.get("required", [])
            enums = struct.get("enums", {})
            for i, row in enumerate(c.structs(name), start=1):
                if not isinstance(row, dict):
                    out.append(_p(check_struct_shape, c.id,
                                  "`%s` の%d件目がマッピングになっていない" % (name, i)))
                    continue
                if struct.get("free-key"):
                    continue
                for key in required:
                    if not row.get(key):
                        out.append(_p(check_struct_shape, c.id,
                                      "`%s` の%d件目に `%s` が無い" % (name, i, key)))
                for key in row:
                    if key not in keys:
                        out.append(_p(check_struct_shape, c.id,
                                      "`%s` の%d件目に宣言にないキー `%s`" % (name, i, key),
                                      level=WARNING))
                for key, enum_name in enums.items():
                    value = row.get(key)
                    if value and value not in ctx.o.enum_values(enum_name):
                        out.append(_p(check_struct_shape, c.id,
                                      "`%s` の%d件目の `%s` が語彙にない: %s" % (name, i, key, value)))
    return out


@check("id-sequence", WARNING)
def check_id_sequence(ctx):
    """ID の重複と欠番。欠番そのものは正常（取り下げた番号は再利用しない）。"""
    out, seen = [], {}
    for c in ctx.sound:
        seen.setdefault(c.get("id") or c.filename_id, []).append(c)
    for card_id, cards in sorted(seen.items()):
        if len(cards) > 1:
            out.append(_p(check_id_sequence, card_id,
                          "同じ id のカードが%d枚ある" % len(cards)))
    return out


# ============================================================ 参照整合

@check("ref-exists", ERROR)
def check_ref_exists(ctx):
    """参照先のカードが実在しない。"""
    out = []
    for c in ctx.sound:
        for name, _ in ctx.o.ref_fields(c.type):
            for target in c.list(name):
                if not target:
                    continue
                if not ctx.wiki.exists(target):
                    out.append(_p(check_ref_exists, c.id,
                                  "`%s` が存在しないカードを指している: %s" % (name, target)))
    return out


@check("ref-range", ERROR)
def check_ref_range(ctx):
    """参照先の型が宣言と違う。"""
    out = []
    for c in ctx.sound:
        for name, targets in ctx.o.ref_fields(c.type):
            for ref in c.list(name):
                if not ref or not ctx.wiki.exists(ref):
                    continue
                actual = ctx.o.type_of_id(ref)
                if actual not in targets:
                    out.append(_p(check_ref_range, c.id,
                                  "`%s` は %s を指すはずだが %s を指している"
                                  % (name, " / ".join(targets), ref)))
    return out


@check("log-ref", ERROR)
def check_log_ref(ctx):
    """引用を持つカードは、必ずどれかの LOG から生えている。"""
    out = []
    for c in ctx.of_type("DEC", "Q", "ACT", "CON", "ASM"):
        if not [r for r in c.list("derived_from") if ctx.o.type_of_id(r) == "LOG"]:
            out.append(_p(check_log_ref, c.id, "derived_from に LOG が無い"))
    return out


@check("inverse-sync", WARNING)
def check_inverse_sync(ctx):
    """逆リンクの片側だけが埋まっている状態。"""
    out = []
    for c in ctx.sound:
        for name, _ in ctx.o.ref_fields(c.type):
            inverse = ctx.o.inverse_of(name)
            if not inverse:
                continue
            for ref in c.list(name):
                other = ctx.wiki.get(ref)
                if other is None or other.error is not None:
                    continue
                if c.id not in other.list(inverse):
                    out.append(_p(check_inverse_sync, c.id,
                                  "`%s` は %s を指すが、%s の `%s` に %s が無い"
                                  % (name, ref, ref, inverse, c.id)))
    return out


@check("resolved-status", ERROR)
def check_resolved_status(ctx):
    """参照が埋まっているのに状態が追随していない。"""
    out = []
    for imp in ctx.o.status_implications:
        field, expected = imp["when-filled"], imp["status"]
        for c in ctx.of_type(imp["type"]):
            if not c.get(field):
                continue
            if c.get("status") != expected:
                out.append(_p(check_resolved_status, c.id,
                              "`%s` が埋まっているのに status が `%s` になっていない（現在: %s）"
                              % (field, expected, c.get("status") or "空")))
    return out


@check("log-format", ERROR)
def check_log_format(ctx):
    """LOG 本文の発言行の形。ここが崩れると引用検証の前提が崩れる。"""
    out = []
    for c in ctx.of_type("LOG"):
        for line_no, text in c.malformed_utterance_lines:
            out.append(_p(check_log_format, c.id,
                          "発言行が `- **役割**: 発言` の形でない（本文%d行目）: %s" % (line_no, text)))
        if not c.utterances:
            out.append(_p(check_log_format, c.id, "発言が1件も無い", level=WARNING))
    return out


# ================================================== Pass 1 の出力（segments.yaml）
#
# segments.yaml はカードではないが、Pass 2 以降すべての土台になる。
# ここが崩れたまま進むと LOG の分割ごとやり直しになり、後戻りが最も高くつく。
# 形式の点検はスキルの禁止事項として LLM の自制に賭けず、ここで見る。

TIME_RANGE = re.compile(r"^\d{2}:\d{2}:\d{2}\s*-\s*\d{2}:\d{2}:\d{2}$")


def _segment_rows(ctx, meeting_id):
    data, _, _ = ctx.wiki.segments[meeting_id]
    rows = (data or {}).get("segments") or []
    return [r for r in rows if isinstance(r, dict)]


@check("segment-format", ERROR)
def check_segment_format(ctx):
    """segments.yaml の形。seq の連番・見出し・種別・時刻。"""
    out = []
    kinds = ctx.o.enum_values("LOG種別")
    for meeting_id in sorted(ctx.wiki.segments):
        data, _, error = ctx.wiki.segments[meeting_id]
        if error is not None:
            out.append(_p(check_segment_format, meeting_id,
                          "segments.yaml が読めない: %s" % error))
            continue
        if data.get("meeting") and data["meeting"] != meeting_id:
            out.append(_p(check_segment_format, meeting_id,
                          "`meeting` がディレクトリと食い違う: %s" % data["meeting"]))
        rows = _segment_rows(ctx, meeting_id)
        for i, row in enumerate(rows, start=1):
            where = "%s#%s" % (meeting_id, row.get("seq") or i)
            if str(row.get("seq") or "") != str(i):
                out.append(_p(check_segment_format, where,
                              "`seq` が1からの連番になっていない（%s 番目が `%s`）"
                              % (i, row.get("seq"))))
            if not (row.get("title") or "").strip():
                out.append(_p(check_segment_format, where, "`title` が空"))
            kind = row.get("種別") or ""
            if kind not in kinds:
                out.append(_p(check_segment_format, where,
                              "`種別` が語彙にない: `%s`（%s）" % (kind, " / ".join(kinds))))
            time = (row.get("時刻") or "").strip()
            if time and not TIME_RANGE.match(time):
                out.append(_p(check_segment_format, where,
                              "`時刻` が `HH:MM:SS - HH:MM:SS` の形でない: %s" % time))
            topic = row.get("議題") or ""
            if topic:
                card = ctx.wiki.get(topic) if isinstance(topic, str) else None
                if card is None or card.type != "AGD":
                    out.append(_p(check_segment_format, where,
                                  "`議題` が実在する議題（AGD）を指していない: %s" % topic))
    return out


@check("segment-count", WARNING)
def check_segment_count(ctx):
    """論点の数。範囲外なら逸脱理由を書く規約になっている。"""
    out = []
    low = ctx.o.threshold("segment-count-min")
    high = ctx.o.threshold("segment-count-max")
    limit = ctx.o.threshold("segment-title-max")
    for meeting_id in sorted(ctx.wiki.segments):
        data, raw, error = ctx.wiki.segments[meeting_id]
        if error is not None:
            continue
        rows = _segment_rows(ctx, meeting_id)
        if not (low <= len(rows) <= high) and "逸脱理由" not in raw:
            out.append(_p(check_segment_count, meeting_id,
                          "論点が %d件（%d〜%d件を外れている）。"
                          "意図どおりなら末尾に `# 逸脱理由: <1行>` を書く"
                          % (len(rows), low, high)))
        for i, row in enumerate(rows, start=1):
            title = (row.get("title") or "").strip()
            if len(title) > limit:
                out.append(_p(check_segment_count, "%s#%s" % (meeting_id, row.get("seq") or i),
                              "`title` が %d文字を超える（%d文字）: %s"
                              % (limit, len(title), title)))
    return out


@check("segment-role", WARNING)
def check_segment_role(ctx):
    """`参加役割` に role-mapping.yaml へ未登録の役割が混じっていないか。

    LOG まで進んでから `role-unknown` で気づくと、その会議の抽出が
    一巡やり直しになる。Pass 1 の時点で出す。
    """
    out = []
    if not ctx.wiki.has_role_mapping:
        return out
    for meeting_id in sorted(ctx.wiki.segments):
        _, _, error = ctx.wiki.segments[meeting_id]
        if error is not None:
            continue
        unknown = set()
        for row in _segment_rows(ctx, meeting_id):
            roles = row.get("参加役割") or []
            if not isinstance(roles, list):
                roles = [roles]
            unknown.update(r for r in roles if r and not ctx.wiki.is_known_role(r))
        for role in sorted(unknown):
            out.append(_p(check_segment_role, meeting_id,
                          "`参加役割` の役割 `%s` が role-mapping.yaml に無い" % role))
    return out


# ================================================== 会議との多対多の整合

@check("meeting-anchor", WARNING)
def check_meeting_anchor(ctx):
    """日付が、実際に参照している会議の範囲と食い違っていないか。

    カード ↔ 会議は多対多で、`初出` / `最終言及` はそれを日付に射影したもの。
    2回目の会議で更新したのに `最終言及` を直し忘れる、が最も起きやすい。
    """
    out = []
    for c in ctx.sound:
        meetings = ctx.wiki.meetings_of(c)
        if not meetings or c.type == "LOG":
            continue
        dates = sorted(ctx.wiki.meetings[m].date for m in meetings if m in ctx.wiki.meetings)
        if not dates:
            continue
        for which, expected in (("first", dates[0]), ("last", dates[-1])):
            field = ctx.o.date_anchor(c.type, which)
            if not field:
                continue
            actual = (c.get(field) or "").strip()
            if actual and actual != expected:
                out.append(_p(check_meeting_anchor, c.id,
                              "`%s` が %s だが、参照している会議は %s（%s）"
                              % (field, actual, " / ".join(dates), "最古" if which == "first" else "最新")))
    return out


@check("meeting-orphan", WARNING)
def check_meeting_orphan(ctx):
    """LOG が実在しない会議に属している。"""
    out = []
    for c in ctx.of_type("LOG"):
        meeting = c.get("meeting")
        if meeting and meeting not in ctx.wiki.meetings:
            out.append(_p(check_meeting_orphan, c.id, "会議 %s のディレクトリが無い" % meeting))
    return out


# ================================================== 引用・信頼度

@check("quote-verbatim", ERROR)
def check_quote_verbatim(ctx):
    """引用が LOG に無いのに `推測` を名乗っていない。

    慎重側（既に `推測`）は問題にしない。水増しだけを弾く。
    """
    out = []
    for issue in quotes.check(ctx.wiki):
        if not issue.is_problem:
            continue
        out.append(_p(check_quote_verbatim, issue.card.id,
                      "%d行目の引用が照合できない（%s）: %s"
                      % (issue.line, issue.detail, issue.quote)))
    return out


@check("confidence-position", WARNING)
def check_confidence_position(ctx):
    """`信頼度` が `引用` の直後に無い。--fix が降格先を見つけられなくなる。"""
    return [_p(check_confidence_position, card.id,
               "%d行目の引用の直後に `信頼度` が無い（--fix が働かない）: %s" % (line, quote))
            for card, line, quote in quotes.confidence_out_of_position(ctx.wiki)]


@check("silence-confidence", WARNING)
def check_silence_confidence(ctx):
    """沈黙由来の却下は `推測` 固定という規約。

    却下理由が `記録なし` = 誰も却下理由を言わなかった、ということ。
    沈黙を根拠にした判定は、明示的な合意より弱い根拠でしかない。
    """
    out = []
    for c in ctx.of_type("DEC"):
        for i, row in enumerate(c.structs("代替案"), start=1):
            if not isinstance(row, dict):
                continue
            if row.get("却下理由") != "記録なし":
                continue
            if row.get("信頼度") not in ("", None, "推測"):
                out.append(_p(check_silence_confidence, c.id,
                              "代替案%d件目が `却下理由: 記録なし` なのに `信頼度: %s` を名乗っている"
                              % (i, row.get("信頼度"))))
    return out


@check("quote-missing", WARNING)
def check_quote_missing(ctx):
    """起票の根拠になる引用が無い。"""
    out = []
    for c in ctx.sound:
        field = ctx.o.quote_field(c.type)
        if field and ctx.o.has_quote(c.type) and not c.get(field):
            out.append(_p(check_quote_missing, c.id, "`%s` が空" % field))
    return out


# ================================================== 役割・導出

@check("role-mapping", ERROR)
def check_role_mapping(ctx):
    """案件に role-mapping.yaml が無い。

    キットのルートにフォールバックはしない（社名も決定権も案件ごとに違い、
    共有すると静かに間違う）。無ければ `決定の所在` から `種別` を導けず、
    `決定権` も見られないので、Pass 3 の判定が全部効かなくなる。
    """
    if ctx.wiki.has_role_mapping:
        return []
    return [_p(check_role_mapping, "role-mapping.yaml",
               "案件に role-mapping.yaml が無い"
               "（`cp templates/project/role-mapping.yaml <案件>/` で置く）")]


@check("role-unknown", WARNING)
def check_role_unknown(ctx):
    """role-mapping.yaml に無い役割。②の確認で追記する。"""
    out, fields = [], {"DEC": ["決定の所在"], "Q": ["確認先"], "AGD": ["提起者"]}
    for c in ctx.sound:
        names = []
        for field in fields.get(c.type, []):
            if c.get(field):
                names.append((field, c.get(field)))
        for role in c.list("参加役割"):
            names.append(("参加役割", role))
        for field, role in names:
            if role and not ctx.wiki.is_known_role(role):
                out.append(_p(check_role_unknown, c.id,
                              "`%s` の役割 `%s` が role-mapping.yaml に無い" % (field, role)))
    return out


@check("decision-authority", ERROR)
def check_decision_authority(ctx):
    """決定権のない役割の発言だけで DEC を起票していない。

    決定権がないなら Q に落とすべき。半年後の水掛け論の材料を作らないため。
    """
    out = []
    for c in ctx.of_type("DEC"):
        role = c.get("決定の所在")
        if not role or not ctx.wiki.is_known_role(role):
            continue
        if ctx.wiki.role(role).get("決定権") != "あり":
            out.append(_p(check_decision_authority, c.id,
                          "`決定の所在` の %s は決定権を持たない（Q に落とすべき）" % role))
    return out


@check("dec-type-derived", ERROR)
def check_dec_type_derived(ctx):
    """`種別` は role-mapping.yaml から導出される。手入力で食い違わせない。"""
    out = []
    for c in ctx.of_type("DEC"):
        role = c.get("決定の所在")
        if not role or not ctx.wiki.is_known_role(role):
            continue
        expected = ctx.wiki.role(role).get("決定の種別")
        actual = c.get("種別")
        if expected and actual and actual != expected:
            out.append(_p(check_dec_type_derived, c.id,
                          "`種別` が %s だが、%s の決定の種別は %s" % (actual, role, expected)))
    return out


@check("act-owner", WARNING)
def check_act_owner(ctx):
    """ACT の `担当` は社名。役割名が入っていたら取り違え。"""
    out = []
    companies = ctx.wiki.companies
    for c in ctx.of_type("ACT"):
        owner = c.get("担当")
        if not owner or not companies:
            continue
        if owner not in companies:
            hint = "（役割名ではなく社名で持つ）" if ctx.wiki.is_known_role(owner) else ""
            out.append(_p(check_act_owner, c.id,
                          "`担当` の %s が role-mapping.yaml の社名にない%s" % (owner, hint)))
    return out


@check("con-hardness", ERROR)
def check_con_hardness(ctx):
    """`硬度` は `種類` × `所在` から機械的に決まる。入力させない。"""
    out = []
    for c in ctx.of_type("CON"):
        kind, location, actual = c.get("種類"), c.get("所在"), c.get("硬度")
        if not kind or not location:
            continue
        expected = ctx.o.derive_hardness(kind, location)
        if expected is None:
            out.append(_p(check_con_hardness, c.id,
                          "`%s` × `%s` は導出表にない組み合わせ（ontology.yaml の derivations を確認する）"
                          % (kind, location), level=WARNING))
            continue
        if actual and actual != expected:
            out.append(_p(check_con_hardness, c.id,
                          "`硬度` が %s だが、%s × %s なら %s" % (actual, kind, location, expected)))
    return out


# ================================================== 二層構造・運用

@check("promote-gate", WARNING)
def check_promote_gate(ctx):
    """理由の書かれていない決定にしか紐づいていない制約・前提。

    **昇格の門そのものは lint では守れない。** カードには「どの決定から昇格したか」
    が残らず（残るのは derived_from の LOG だけ）、`影響する決定` /
    `崩れたら見直す決定` は昇格元ではなく影響先を指す。だから事後に門の破れを
    判定する根拠が無い。門は `kime promote-input` が `なぜ` 未記入の DEC を
    入力から落とすことで物理的に閉じる。

    ここで見るのはその副作用のほう — 紐づく決定がすべて `なぜ` 未記入なら、
    その制約は「なぜそれが効くのか」を辿れない。将来の議論で使えない。
    """
    out = []
    for c in ctx.of_type("CON", "ASM"):
        field = "影響する決定" if c.type == "CON" else "崩れたら見直す決定"
        refs = [r for r in c.list(field) if ctx.o.type_of_id(r) == "DEC"]
        if not refs:
            continue
        decisions = [ctx.wiki.get(r) for r in refs]
        decisions = [d for d in decisions if d is not None and d.error is None]
        if not decisions:
            continue
        if all(not d.get("なぜ") for d in decisions):
            out.append(_p(check_promote_gate, c.id,
                          "`%s` が指す決定（%s）はすべて `なぜ` が未記入。"
                          "この制約は理由を辿れず、将来の議論で効かない"
                          % (field, ", ".join(d.id for d in decisions))))
    return out


@check("scope-pending-q", WARNING)
def check_scope_pending_q(ctx):
    """`範囲: 判定保留` の DEC には Q が立っているはず。

    同じ LOG から生えた未決 Q があるかで見る。DEC → Q の直接の参照は
    設計上持たないので、これ以上厳密には判定できない。だから warning。

    対象は `種別: 交渉可能` / `契約制約` に限る。技術判断の範囲を顧客に
    問う Q は起票しない規約なので（`.claude/skills/extract/SKILL.md`）、
    ここで鳴らすと消せない warning になる。
    """
    ASKABLE = ("交渉可能", "契約制約")
    out = []
    pending_questions = [q for q in ctx.of_type("Q") if q.get("status") == "未決"]
    for c in ctx.of_type("DEC"):
        if c.get("範囲") != "判定保留":
            continue
        if c.get("status") == "覆された":
            continue          # 覆った決定の範囲は、もう誰にも聞かない
        if c.get("種別") not in ASKABLE:
            continue          # 技術判断の範囲は顧客に問わない
        logs = set(c.list("derived_from"))
        if any(logs & set(q.list("derived_from")) for q in pending_questions):
            continue
        out.append(_p(check_scope_pending_q, c.id,
                      "`範囲: 判定保留` だが、同じ論点に未決の Q が無い"))
    return out


@check("asm-loadbearing", ERROR)
def check_asm_loadbearing(ctx):
    """逆リンクの無い前提カードは飾りになる。"""
    out = []
    for c in ctx.of_type("ASM"):
        if c.get("脆弱性") != "高":
            continue
        if not c.list("崩れたら見直す決定"):
            out.append(_p(check_asm_loadbearing, c.id,
                          "`脆弱性: 高` なのに `崩れたら見直す決定` が空"))
    return out


@check("asm-signpost-empty", ERROR)
def check_asm_signpost_empty(ctx):
    """`脆弱性: 高` なのに signpost が無い。追跡できない前提になる。"""
    out = []
    for c in ctx.of_type("ASM"):
        if c.get("脆弱性") == "高" and not c.get("signpost"):
            out.append(_p(check_asm_signpost_empty, c.id, "`脆弱性: 高` なのに `signpost` が空"))
    return out


@check("asm-signpost-vague", WARNING)
def check_asm_signpost_vague(ctx):
    """signpost は事象または閾値でなければならない。

    「事象か閾値か」を機械で判定するのは原理的に無理なので、
    明らかに足りない言い回しだけを否定リストで拾う。語は運用で足す。
    """
    out = []
    words = ctx.o.signpost_vague_words
    for c in ctx.of_type("ASM"):
        signpost = c.get("signpost")
        if not signpost:
            continue
        if any(w in signpost for w in words) and not re.search(r"\d", signpost):
            out.append(_p(check_asm_signpost_vague, c.id,
                          "`signpost` が事象・閾値になっていない可能性: %s" % signpost))
    return out


@check("con-expiry", ERROR)
def check_con_expiry(ctx):
    """expectation は破られ得るので失効条件が要る。property は事実なので空でよい。"""
    out = []
    for c in ctx.of_type("CON"):
        if c.get("種類") == "expectation" and not c.get("失効条件"):
            out.append(_p(check_con_expiry, c.id, "`種類: expectation` なのに `失効条件` が空"))
    return out


@check("term-variant-conflict", ERROR)
def check_term_variant_conflict(ctx):
    """表記揺れの衝突。Pass 2 の正規化がどちらに寄せるか決められなくなる。"""
    out, owner = [], {}
    for c in ctx.of_type("TERM"):
        for value in [c.get("正式")] + c.list("表記揺れ"):
            if not value:
                continue
            if value in owner and owner[value] != c.id:
                out.append(_p(check_term_variant_conflict, c.id,
                              "`%s` が %s と重複している" % (value, owner[value])))
            else:
                owner[value] = c.id
    return out


@check("why-missing", WARNING)
def check_why_missing(ctx):
    """`なぜ` の未記入。**error にしない。**

    必須フィールドにすると人間が作話する。代わりに次回アジェンダへの掲示と
    昇格の門でコストを付ける。ここは計器であって、消す対象ではない。
    """
    return [_p(check_why_missing, c.id, "`なぜ` が未記入（次回アジェンダに掲示される）")
            for c in ctx.of_type("DEC") if not c.get("なぜ") and c.get("status") != "覆された"]


@check("dec-deferral", WARNING)
def check_dec_deferral(ctx):
    """「前向きに検討します」の類が DEC になっていないか。

    これらを DEC にすると、半年後に「合意したはずだ」という水掛け論の材料になる。
    """
    out = []
    for c in ctx.of_type("DEC"):
        quote = c.get("引用")
        for phrase in ctx.o.deferral_phrases:
            if phrase in quote:
                out.append(_p(check_dec_deferral, c.id,
                              "引用が保留の表現を含む（DEC ではなく Q では）: %s" % quote))
                break
    return out


@check("act-open-fields", WARNING)
def check_act_open_fields(ctx):
    """未完了 ACT の担当・期限。空欄が正常な出力で、②の確認で人間が埋める。"""
    out = []
    for c in ctx.of_type("ACT"):
        if c.get("status") in ("完了", "取り下げ"):
            continue
        missing = [f for f in ("担当", "期限") if not c.get(f)]
        if missing:
            out.append(_p(check_act_open_fields, c.id,
                          "未完了だが %s が空" % " と ".join("`%s`" % m for m in missing)))
    return out


@check("act-overdue", WARNING)
def check_act_overdue(ctx):
    """期限を過ぎて未完了のアクション。"""
    out = []
    for c in ctx.of_type("ACT"):
        if c.get("status") in ("完了", "取り下げ"):
            continue
        days = ctx.days_since(c, "期限")
        if days is not None and days > 0:
            out.append(_p(check_act_overdue, c.id,
                          "期限（%s）を過ぎて status が `%s`" % (c.get("期限"), c.get("status"))))
    return out


@check("asm-review-due", WARNING)
def check_asm_review_due(ctx):
    """`次回確認日` を過ぎた前提。四半期の棚卸しの対象。"""
    out = []
    limit = ctx.o.threshold("asm-review-overdue-days")
    for c in ctx.of_type("ASM"):
        if c.get("status") != "有効":
            continue
        days = ctx.days_since(c, "次回確認日")
        if days is not None and days > limit:
            out.append(_p(check_asm_review_due, c.id,
                          "`次回確認日`（%s）を過ぎている" % c.get("次回確認日")))
    return out


@check("q-stale", WARNING)
def check_q_stale(ctx):
    """未決のまま言及されなくなった Q。次回アジェンダに積まれているはず。"""
    out = []
    limit = ctx.o.threshold("q-stale-days")
    for c in ctx.of_type("Q"):
        if c.get("status") != "未決":
            continue
        days = ctx.days_since(c, "最終言及")
        if days is not None and days > limit:
            out.append(_p(check_q_stale, c.id,
                          "未決のまま %d 日 言及がない（最終言及: %s）" % (days, c.get("最終言及"))))
    return out


@check("dec-unconfirmed", WARNING)
def check_dec_unconfirmed(ctx):
    """みなし確定の取りこぼし。異議なく確定した日を書き戻す運用が回っているか。"""
    out = []
    limit = ctx.o.threshold("dec-unconfirmed-days")
    for c in ctx.of_type("DEC"):
        if c.get("status") != "決定" or c.get("確定日"):
            continue
        days = ctx.days_since(c, "決定日")
        if days is not None and days > limit:
            out.append(_p(check_dec_unconfirmed, c.id,
                          "決定から %d 日たつが `確定日` が空（みなし確定の書き戻し漏れ）" % days))
    return out


@check("log-barren", WARNING)
def check_log_barren(ctx):
    """議論・確認の LOG から何も生えていない。

    docs/design.md が「最大のエラー源は幻覚ではなく欠落（89% 対 26%）」とする穴を
    事後に拾う。引用検証は幻覚しか捕まえないので、こちら側が要る。

    `meetings/*/extraction-notes.yaml` に理由が書かれている LOG は鳴らさない。
    「何も生えないのが正常」と判断した記録があるなら、それ以上言うことはない。
    ただし `review_required: true` は、判断がついていないという記録なので鳴らす。
    """
    out = []
    referenced = set()
    for c in ctx.of_type("DEC", "Q", "ACT", "CON", "ASM"):
        referenced.update(c.list("derived_from"))
    notes = ctx.wiki.extraction_notes
    for c in ctx.of_type("LOG"):
        if c.get("種別") not in ("議論", "確認"):
            continue
        if c.id in referenced:
            continue
        note = notes.get(c.id) or {}
        if str(note.get("review_required", "")).lower() in ("true", "yes"):
            out.append(_p(check_log_barren, c.id,
                          "カードが1枚も生えておらず、`review_required: true` "
                          "が立っている（人間の確認待ち）"))
            continue
        if (note.get("extraction_empty_reason") or "").strip():
            continue
        out.append(_p(check_log_barren, c.id,
                      "`種別: %s` だがカードが1枚も生えていない（欠落の可能性）。"
                      "正常なら extraction-notes.yaml に理由を書く" % c.get("種別")))
    return out


@check("issue-orphan", WARNING)
def check_issue_orphan(ctx):
    """閉じた ACT に Issue が紐づいたまま。"""
    return [_p(check_issue_orphan, c.id,
               "status が `%s` だが `issue` が残っている: %s" % (c.get("status"), c.get("issue")))
            for c in ctx.of_type("ACT")
            if c.get("issue") and c.get("status") in ("完了", "取り下げ")]


# ============================================================ 議題

@check("agd-meeting-id", ERROR)
def check_agd_meeting_id(ctx):
    """`予定会議` が会議 ID の形でない。

    未来の会議はまだディレクトリが無いので、実在は見ない。形だけを見る
    （形が崩れていると、どの会議のアジェンダにも載らず黙って消える）。
    """
    out = []
    for c in ctx.of_type("AGD"):
        for value in c.list("予定会議"):
            if not ctx.o.is_meeting_id(str(value)):
                out.append(_p(check_agd_meeting_id, c.id,
                              "`予定会議` が会議 ID の形でない: %s" % value))
    return out


@check("agd-closed-open", WARNING)
def check_agd_closed_open(ctx):
    """`決着` の議題の下に、未決の問いか未完了のアクションが残っている。

    決着にすると次回のアジェンダから外れる。残った子は「議題に紐づかない」節に
    落ちるので消えはしないが、何の話の続きかが見えなくなる。
    """
    out = []
    for c in ctx.of_type("AGD"):
        if c.get("status") != "決着":
            continue
        rest = [x.id for x in ctx.wiki.children_of(c)
                if (x.type == "Q" and x.get("status") == "未決")
                or (x.type == "ACT" and x.get("status") not in ("完了", "取り下げ"))]
        if rest:
            out.append(_p(check_agd_closed_open, c.id,
                          "`決着` だが、下に閉じていないカードが残っている: %s" % " / ".join(rest)))
    return out


# ============================================================ 実行

def run(wiki, today=None, only=None):
    ctx = Context(wiki, today)
    selected = [f for f in CHECKS if not only or f.check_id in only]
    problems = []
    for func in selected:
        problems.extend(func(ctx))
    order = {ERROR: 0, WARNING: 1}
    problems.sort(key=lambda p: (order.get(p.level, 9), p.check, p.where))
    return problems


def check_ids():
    return sorted(f.check_id for f in CHECKS)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kime lint", description="カードの整合性を機械的に検査する")
    ap.add_argument("--root", default=None, help="案件ディレクトリ")
    ap.add_argument("--format", choices=["text", "json"], default="text")
    ap.add_argument("--check", default=None, help="チェック ID をカンマ区切りで指定")
    ap.add_argument("--today", default=None, help="基準日（YYYY-MM-DD。テスト用）")
    ap.add_argument("--list-checks", action="store_true", help="チェック ID の一覧を出す")
    args = ap.parse_args(argv)

    if args.list_checks:
        for func in sorted(CHECKS, key=lambda f: f.check_id):
            summary = ((func.__doc__ or "").strip().splitlines() or [""])[0]
            print("%-22s %-7s %s" % (func.check_id, func.level, summary))
        return 0

    only = set(args.check.split(",")) if args.check else None
    if only:
        unknown = only - set(check_ids())
        if unknown:
            print("未知のチェック ID: %s" % ", ".join(sorted(unknown)), file=sys.stderr)
            return 2

    today = datetime.date.fromisoformat(args.today) if args.today else None
    wiki = Wiki(resolve_root(args.root), schema.load())
    problems = run(wiki, today, only)

    errors = [p for p in problems if p.level == ERROR]
    warnings = [p for p in problems if p.level == WARNING]

    if args.format == "json":
        print(json.dumps({"root": str(wiki.root),
                          "problems": [p.as_dict() for p in problems],
                          "error": len(errors), "warning": len(warnings)},
                         ensure_ascii=False, indent=2))
    else:
        for p in problems:
            print("%-7s %-22s %-18s %s" % (p.level, p.check, p.where, p.message))
        if problems:
            print()
        print("error %d / warning %d（%s）" % (len(errors), len(warnings), wiki.root))
        if warnings and not errors:
            print("warning は真の未達を映す計器。0 を目指すものではない。error 0 だけが不変条件。")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
