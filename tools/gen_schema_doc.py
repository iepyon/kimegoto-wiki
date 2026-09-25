#!/usr/bin/env python3
"""ontology.yaml → schema.md の生成ブロックを生成し、散文とサンプルを照合する。

**schema.md を全面生成はしない。** このファイルの価値の大半は「なぜ `スコープ` が
要るか」「van Lamsweerde の一文がそのまま判定テストになる」といった散文の論証で、
それを YAML の文字列に押し込むと読み物として壊れる。論証は型やフィールドに
1対1で乗らない（判定テストは CON / ASM / ACT / DEC にまたがる）うえ、
ontology.yaml はスキルが読むので、長くするとその分コンテキストを食う。

そこで分担を決める。**事実は ontology.yaml、論証は schema.md。**
機械で決まる記述（型一覧・ID 形式・フィールド表・導出表・語のリスト）は
マーカーで囲んで生成する:

    <!-- generated:fields DEC — ontology.yaml から生成。手編集禁止 -->
    （フィールド表）
    <!-- /generated -->

マーカーの種類は `RENDERERS` にある。`fields` 以外は自動で差し込まない
（どこに置くかは散文の流れで人が決める）。

散文とサンプル frontmatter はマーカーの外にあり、人が書いたまま残る。
事実を写さないのが原則だが、散文は語彙やフィールド名に触れずには書けないので、
その触れ方を --check-samples で照合する:

- サンプル frontmatter のキーと、語彙フィールドの値
- 散文中の `フィールド: 値` と、日本語だけのコード表記（フィールド名・語彙の値のはず）

改名で散文に旧語が残ると、ここで落ちる。照合側に例外リストは持たない
（例外リストは第二の写しになる）。誤検知したら散文の書き方を直す。

使い方:
    python3 tools/gen_schema_doc.py --render          # schema.md を書き換える
    python3 tools/gen_schema_doc.py --check           # 差分があれば終了コード 1
    python3 tools/gen_schema_doc.py --check-samples   # サンプル・散文と宣言の食い違い
    python3 tools/gen_schema_doc.py --check-templates # 雛形と宣言の食い違い
"""

import argparse
import re
import sys

from tools import schema
from tools.miniyaml import MiniYamlError, parse

MARKER_OPEN = "<!-- generated:%s — ontology.yaml から生成。手編集禁止 -->"
MARKER_CLOSE = "<!-- /generated -->"
# 本文は空でもよく（置いたばかりのマーカー）、次のマーカーをまたがない。
# またぐと、閉じ忘れや空のブロックで間の散文ごと置き換えてしまう。
BLOCK_RE = re.compile(
    r"<!-- generated:(?P<kind>[\w-]+)(?: (?P<arg>[^\s—]+))? [^>]*-->\n"
    r"(?:(?!<!-- generated:).)*?"
    + re.escape(MARKER_CLOSE) + r"\n",
    re.DOTALL)

KIND_LABEL = {
    "id": "ID", "text": "自由記述", "enum": "語彙", "date": "日付",
    "ref": "参照", "ref-list": "参照の配列", "str-list": "文字列の配列",
    "struct-list": "構造化配列", "quote": "引用", "time-range": "時刻範囲",
}

LAYER_LABEL = {"flow": "フロー", "stock": "ストック"}

# ID の正規表現を人が読む形に直す。
ID_PLACEHOLDERS = [(r"\d{8}", "YYYYMMDD"), (r"\d{3}", "NNN"), (r"\d{2}", "NN")]


def _type_heading_re(type_name):
    return re.compile(r"^## %s\b.*$" % re.escape(type_name), re.MULTILINE)


def id_pattern(regex):
    text = regex.strip("^$")
    for pattern, placeholder in ID_PLACEHOLDERS:
        text = text.replace(pattern, placeholder)
    return text


# ------------------------------------------------------------ 生成

def render_fields(ontology, type_name):
    if type_name not in ontology.type_names():
        return None
    rows = ["| フィールド | 意味 | 種類 | 必須 | 値 | 記入主体 |", "|---|---|---|---|---|---|"]
    for name, spec in ontology.field_specs(type_name).items():
        kind = KIND_LABEL.get(spec.get("kind"), spec.get("kind", ""))
        required = "○" if str(spec.get("required", "")).lower() == "true" else "—"
        if spec.get("enum"):
            values = " / ".join("`%s`" % v for v in ontology.enum_values(spec["enum"]))
            if ontology.allows_free_text(type_name, name):
                values += " / 自由記述"
        elif spec.get("kind") in ("ref", "ref-list"):
            targets = ontology.ref_targets(type_name, name)
            values = " / ".join("`%s`" % t for t in targets)
        elif spec.get("kind") == "struct-list":
            struct = ontology.structs.get(spec.get("struct"), {})
            values = " / ".join("`%s`" % k for k in struct.get("keys", []))
        else:
            values = "—"
        rows.append("| `%s` | %s | %s | %s | %s | %s |"
                    % (name, spec.get("description", ""), kind, required, values,
                       spec.get("記入主体", "")))
    return "\n".join(rows)


def render_types(ontology, _arg):
    rows = ["| 層 | 型 | 名前 | ID 形式 | 何を表すか | 閉じた status |",
            "|---|---|---|---|---|---|"]
    for type_name in ontology.type_names():
        spec = ontology.spec(type_name)
        closed = " / ".join("`%s`" % s for s in ontology.closed_status(type_name)) or "—"
        rows.append("| %s | %s | %s | `%s` | %s | %s |"
                    % (LAYER_LABEL.get(spec.get("layer"), spec.get("layer", "")), type_name,
                       ontology.label(type_name), id_pattern(spec["id"]),
                       spec.get("summary", ""), closed))
    rows.append("")
    rows.append("会議の ID は `%s`。" % id_pattern(ontology.meetings.get("id", "")))
    return "\n".join(rows)


def render_derivation(ontology, name):
    spec = ontology.derivations.get(name)
    if not spec or "table" not in spec:
        return None
    columns = list(spec["from"])
    rows = ["| %s | %s |" % (" | ".join(columns), name),
            "|" + "---|" * (len(columns) + 1)]
    for key, value in spec["table"].items():
        rows.append("| %s | %s |" % (" | ".join(key.split("/")), value))
    return "\n".join(rows)


def render_words(ontology, key):
    words = ontology._d.get(key)
    if not isinstance(words, list):
        return None
    return "```\n%s\n```" % " / ".join(words)


def render_files(ontology, _arg):
    """周辺ファイル（カードではない YAML）の書式。"""
    out = []
    for name, spec in ontology.files.items():
        out.append("### `%s`" % spec.get("path", name))
        out.append("")
        out.append(spec.get("summary", ""))
        out.append("")
        out.append("| キー | 場所 | 意味 | 値 |")
        out.append("|---|---|---|---|")
        for key, k in ontology.file_keys(name).items():
            values = "—"
            if k.get("enum"):
                values = " / ".join("`%s`" % v for v in ontology.enum_values(k["enum"]))
            out.append("| `%s` | %s | %s | %s |"
                       % (key, "`%s`" % k["in"] if k.get("in") else "最上位",
                          k.get("description", ""), values))
        out.append("")
    return "\n".join(out).rstrip("\n")


# マーカーの種類 → (ontology, 引数) → 本文。None を返したら未知として触らない。
RENDERERS = {
    "fields": render_fields,
    "types": render_types,
    "derivation": render_derivation,
    "words": render_words,
    "files": render_files,
}


def _marker_arg(kind, arg):
    return "%s %s" % (kind, arg) if arg else kind


def render_block(ontology, kind, arg=None):
    body = RENDERERS[kind](ontology, arg)
    if body is None:
        return None
    return "%s\n\n%s\n\n%s\n" % (MARKER_OPEN % _marker_arg(kind, arg), body, MARKER_CLOSE)


def apply(text, ontology):
    """schema.md の生成ブロックを挿入 / 更新した全文を返す。"""
    # まず既存ブロックを更新する。
    def replace(m):
        kind, arg = m.group("kind"), m.group("arg")
        if kind not in RENDERERS:
            return m.group(0)
        return render_block(ontology, kind, arg) or m.group(0)

    text = BLOCK_RE.sub(replace, text)

    # フィールド表だけは、まだブロックが無い型の見出しの直後に差し込む。
    for type_name in ontology.type_names():
        if re.search(r"<!-- generated:fields %s\b" % type_name, text):
            continue
        heading = _type_heading_re(type_name).search(text)
        if not heading:
            continue
        insert_at = heading.end()
        block = render_block(ontology, "fields", type_name)
        text = text[:insert_at] + "\n\n" + block.rstrip("\n") + text[insert_at:]
    return text


# ------------------------------------------------------- サンプルの照合

SAMPLE_RE = re.compile(r"```yaml\n(?P<body>.*?)```", re.DOTALL)


def _sections(text, ontology):
    """型ごとの節の本文を切り出す。"""
    positions = []
    for type_name in ontology.type_names():
        m = _type_heading_re(type_name).search(text)
        if m:
            positions.append((m.start(), type_name))
    positions.sort()
    out = {}
    for i, (start, type_name) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        out[type_name] = text[start:end]
    return out


def check_samples(text, ontology):
    """サンプル frontmatter のキーが宣言と食い違っていないか。"""
    problems = []
    for type_name, section in _sections(text, ontology).items():
        m = SAMPLE_RE.search(section)
        if not m:
            continue
        body = m.group("body")
        if body.lstrip().startswith("---"):
            body = body.split("---", 2)[1]
        try:
            data = parse(body)
        except MiniYamlError as exc:
            problems.append("%s のサンプルが読めない: %s" % (type_name, exc))
            continue
        if not isinstance(data, dict):
            continue
        declared = set(ontology.field_specs(type_name))
        for key in data:
            if key not in declared:
                problems.append("%s のサンプルに宣言にないキー `%s` がある" % (type_name, key))
        for key in ontology.required_fields(type_name):
            if key not in data:
                problems.append("%s のサンプルに必須フィールド `%s` が無い" % (type_name, key))
        problems.extend(_check_sample_values(type_name, data, ontology))
    return problems


def _check_sample_values(type_name, data, ontology):
    """語彙フィールドの値が語彙にあるか。空と自由記述を許すフィールドは通す。"""
    problems = []
    for key, value in data.items():
        spec = ontology.field_specs(type_name).get(key, {})
        enum = spec.get("enum")
        if enum and value and not ontology.allows_free_text(type_name, key) \
                and value not in ontology.enum_values(enum):
            problems.append("%s のサンプルの `%s: %s` は語彙 %s に無い" % (type_name, key, value, enum))
        if spec.get("kind") == "struct-list" and isinstance(value, list):
            enums = ontology.structs.get(spec.get("struct"), {}).get("enums", {})
            for item in value:
                if not isinstance(item, dict):
                    continue
                for sub, sub_enum in enums.items():
                    if item.get(sub) and item[sub] not in ontology.enum_values(sub_enum):
                        problems.append("%s のサンプルの `%s[].%s: %s` は語彙 %s に無い"
                                        % (type_name, key, sub, item[sub], sub_enum))
    return problems


# --------------------------------------------------------- 散文の照合

FENCE_RE = re.compile(r"^```.*?^```\n", re.DOTALL | re.MULTILINE)
CODE_RE = re.compile(r"`([^`\n]+)`")
PAIR_RE = re.compile(r"^(\w+): (\S+)$")
# 日本語だけの語（かな・カナ・漢字と長音・々）。英字・空白・記号を含むものは見ない。
JAPANESE_RE = re.compile(r"^[\u3040-\u30ff\u3400-\u9fff々ー]+$")
YAML_FENCE_RE = re.compile(r"^```yaml\n(.*?)^```\n", re.DOTALL | re.MULTILINE)
YAML_KEY_RE = re.compile(r"^[ ]*(?:- )?([^\s#:\-][^:\n]*):(?: |$)", re.MULTILINE)


def _prose(text):
    """生成ブロックとコードフェンスを除いた散文。"""
    return FENCE_RE.sub("", BLOCK_RE.sub("", text))


def _example_keys(text):
    """文書自身の ```yaml の例に現れるキー。

    会議ディレクトリの YAML（segments.yaml など）の書式の正本は、それを書くスキルの例。
    その文書の散文は、自分の例にあるキーに触れてよい。
    """
    return {key for block in YAML_FENCE_RE.findall(text) for key in YAML_KEY_RE.findall(block)}


def _known_names(ontology):
    """散文が日本語だけのコード表記で触れてよい名前。"""
    names = set(ontology.enums)
    for values in ontology.enums.values():
        names.update(values)
    for type_name in ontology.type_names():
        names.add(ontology.label(type_name))
        names.update(ontology.field_specs(type_name))
    for struct in ontology.structs.values():
        names.update(struct.get("keys", []))
    for file_name in ontology.files:
        names.update(ontology.file_keys(file_name))
    # 議事録・アジェンダの節の見出し（`確認事項` など）
    for edition in ontology.edition_names():
        names.update(title for title, _ in ontology.sections_of(edition))
    names.update(title for _, title, _ in ontology.agenda_sections())
    names.update(v for v in (ontology.unverified_confidence, ontology.no_record_value,
                             ontology.unknown_value) if v)
    return names


def _file_key_enums(ontology, field):
    return [k["enum"] for name in ontology.files
            for key, k in ontology.file_keys(name).items() if key == field and k.get("enum")]


def _enums_of_field(ontology, field):
    """そのフィールド名に付いた語彙の一覧。同名のフィールドが型ごとに別の語彙を持つことがある
    （`種別` は LOG では LOG種別、DEC では決定種別）。どれかで自由記述を許すなら None
    （値を照合しようがない）。語彙を持たなければ空。"""
    out = []
    for type_name in ontology.type_names():
        spec = ontology.field_specs(type_name).get(field, {})
        if spec.get("enum"):
            if ontology.allows_free_text(type_name, field):
                return None
            out.append(spec["enum"])
    for struct in ontology.structs.values():
        if field in struct.get("enums", {}):
            out.append(struct["enums"][field])
    out.extend(_file_key_enums(ontology, field))
    return list(dict.fromkeys(out))


def check_prose(text, ontology):
    """散文中のコード表記が ontology.yaml の名前と食い違っていないか。

    - `フィールド: 値` … フィールドが宣言され、語彙フィールドなら値が語彙にある
    - 日本語だけの語 … フィールド名・語彙の値・語彙名・型の名前のどれか
    """
    known = _known_names(ontology) | _example_keys(text)
    problems = []
    seen = set()
    for token in CODE_RE.findall(_prose(text)):
        if token in seen:
            continue
        seen.add(token)
        pair = PAIR_RE.match(token)
        if pair:
            field, value = pair.groups()
            if field not in known:
                problems.append("`%s` のフィールド `%s` が宣言に無い" % (token, field))
                continue
            enums = _enums_of_field(ontology, field)
            if enums and not any(value in ontology.enum_values(e) for e in enums):
                problems.append("`%s` の値 `%s` が語彙 %s に無い"
                                % (token, value, " / ".join(enums)))
        elif JAPANESE_RE.match(token) and token not in known:
            problems.append("`%s` がフィールド名・語彙のどれにも無い" % token)
    return problems


# 散文の照合をかける文書。スキルと規約は ontology.yaml の語に触れずには書けないので、
# schema.md と同じく触れ方を見る。docs/ は経緯の記録で、旧い語が残っているのが正しい。
DOC_GLOBS = [".claude/skills/*/SKILL.md", "CLAUDE.md", "README.md", "decision-guide.md",
             "templates/**/*.md"]


def check_docs(ontology):
    """スキル・規約の散文を照合する。[(相対パス, 問題), ...]。"""
    out = []
    for pattern in DOC_GLOBS:
        for path in sorted(schema.KIT_ROOT.glob(pattern)):
            text = path.read_text(encoding="utf-8")
            rel = str(path.relative_to(schema.KIT_ROOT))
            out.extend((rel, p) for p in check_prose(text, ontology))
    return out


def check_templates(ontology):
    """templates/card/*.md の雛形が宣言と食い違っていないか。"""
    from tools.cards import parse_card

    problems = []
    directory = schema.KIT_ROOT / "templates" / "card"
    if not directory.is_dir():
        return problems
    for path in sorted(directory.glob("*.md")):
        type_name = path.stem.upper()
        if type_name not in ontology.type_names():
            problems.append("%s は既知の型に対応しない" % path.name)
            continue
        card = parse_card(path, ontology)
        if card.error is not None:
            problems.append("%s が読めない: %s" % (path.name, card.error))
            continue
        declared = set(ontology.field_specs(type_name))
        for key in card.data:
            if key not in declared:
                problems.append("%s に宣言にないキー `%s` がある" % (path.name, key))
        for key in ontology.required_fields(type_name):
            if key not in card.data:
                problems.append("%s に必須フィールド `%s` が無い" % (path.name, key))
    return problems


# ------------------------------------------------------------ CLI

def main(argv=None):
    ap = argparse.ArgumentParser(prog="kime schema",
                                 description="ontology.yaml と schema.md / 雛形の同期")
    ap.add_argument("--render", action="store_true", help="schema.md の生成ブロックを書き換える")
    ap.add_argument("--check", action="store_true", help="生成ブロックが最新かを見る")
    ap.add_argument("--check-samples", action="store_true", help="サンプル frontmatter を照合する")
    ap.add_argument("--check-templates", action="store_true", help="templates/card/ を照合する")
    args = ap.parse_args(argv)

    if not any([args.render, args.check, args.check_samples, args.check_templates]):
        args.check = True

    ontology = schema.load()
    path = schema.KIT_ROOT / "schema.md"
    text = path.read_text(encoding="utf-8")
    failed = False

    if args.render:
        updated = apply(text, ontology)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            print("schema.md の生成ブロックを更新した")
        else:
            print("schema.md は既に最新")
        text = updated

    if args.check:
        if apply(text, ontology) != text:
            print("schema.md の生成ブロックが ontology.yaml と一致しない"
                  "（`python3 tools/gen_schema_doc.py --render` で更新する）")
            failed = True
        else:
            print("schema.md: 最新")

    if args.check_samples:
        problems = check_samples(text, ontology)
        for p in problems:
            print("サンプル: %s" % p)
        print("サンプル: %d件の食い違い" % len(problems))
        failed = failed or bool(problems)
        problems = check_prose(text, ontology)
        for p in problems:
            print("散文: %s" % p)
        print("散文: %d件の食い違い" % len(problems))
        failed = failed or bool(problems)
        problems = check_docs(ontology)
        for path_, p in problems:
            print("文書: %s: %s" % (path_, p))
        print("文書: %d件の食い違い" % len(problems))
        failed = failed or bool(problems)

    if args.check_templates:
        problems = check_templates(ontology)
        for p in problems:
            print("雛形: %s" % p)
        print("雛形: %d件の食い違い" % len(problems))
        failed = failed or bool(problems)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
