#!/usr/bin/env python3
"""ビュー射影 — カードから決定論的に導く一覧。

カードが唯一の真実で、ビューはその射影。だから **ビューは生成物であって、
手で編集しない**。編集すると次の再生成で消えるだけでなく、どちらが正かが
分からなくなる。

lint に依存させない。ビュー生成が lint を import すると、チェックを1つ足した
だけでビューが壊れうる。共有するのは記録層（cards.py）までにとどめる。

使い方:
    python3 tools/giji.py views                    # 全部生成
    python3 tools/giji.py views --only open-items  # 1つだけ
    python3 tools/giji.py views --check            # 差分があれば終了コード 1
"""

import argparse
import datetime
import sys

from tools import schema
from tools.cards import Wiki, resolve_root

HEADER = ("<!-- 生成物: gen_views.py %s による機械生成。手編集禁止。"
          "生成基準日: %s / ontology-version: %s -->")

EMPTY = "（なし）"


def _header(name, ctx):
    return HEADER % (name, ctx.today.isoformat(), ctx.o.version)


class Ctx:
    def __init__(self, wiki, today=None):
        self.wiki = wiki
        self.o = wiki.ontology
        self.today = today or datetime.date.today()

    def of(self, *types):
        return [c for c in self.wiki.by_type(*types) if c.error is None]

    def date(self, card, field):
        try:
            return datetime.date.fromisoformat((card.get(field) or "").strip())
        except ValueError:
            return None

    def overdue(self, card, field):
        d = self.date(card, field)
        return d is not None and d < self.today

    def head(self, card):
        return card.headline(self.o)

    def meetings_label(self, card):
        return " / ".join(self.wiki.meetings_of(card)) or "—"


def _table(header, rows):
    if not rows:
        return EMPTY
    out = ["| %s |" % " | ".join(header), "|%s|" % "|".join(["---"] * len(header))]
    for row in rows:
        out.append("| %s |" % " | ".join(str(cell) if cell not in (None, "") else "—"
                                         for cell in row))
    return "\n".join(out)


def _section(title, body, note=None):
    parts = ["## %s" % title, ""]
    if note:
        parts += [note, ""]
    parts += [body, ""]
    return "\n".join(parts)


# ------------------------------------------------------------ 個別の束

def _why_missing(ctx):
    """`なぜ` 未記入の決定。書かないことに付けたコストの実体。"""
    rows = []
    for c in sorted(ctx.of("DEC"), key=lambda c: c.id):
        if c.get("なぜ") or c.get("status") == "覆された":
            continue
        rows.append([c.id, ctx.head(c), c.get("決定の所在"), c.get("決定日"), ctx.meetings_label(c)])
    return _table(["ID", "決定", "決定の所在", "決定日", "会議"], rows), len(rows)


def _open_questions(ctx):
    """未決の問い。確認先ごとに束ねる（誰に聞けばよいかが引けるように）。"""
    by_owner = {}
    for c in ctx.of("Q"):
        if c.get("status") != "未決":
            continue
        by_owner.setdefault(c.get("確認先") or "（確認先なし）", []).append(c)
    if not by_owner:
        return EMPTY, 0
    parts, total = [], 0
    for owner in sorted(by_owner):
        rows = []
        for c in sorted(by_owner[owner], key=lambda c: c.id):
            conflict = " / ".join(c.list("対立当事者")) or "—"
            rows.append([c.id, ctx.head(c), conflict, c.get("初出"), c.get("最終言及")])
        total += len(rows)
        parts.append("### 確認先: %s\n\n%s" % (owner, _table(
            ["ID", "未決の内容", "対立当事者", "初出", "最終言及"], rows)))
    return "\n\n".join(parts), total


def _open_actions(ctx):
    """未完了のアクション。担当社ごとに束ね、期限の早い順に並べる。"""
    by_owner = {}
    for c in ctx.of("ACT"):
        if c.get("status") in ("完了", "取り下げ"):
            continue
        by_owner.setdefault(c.get("担当") or "（担当なし）", []).append(c)
    if not by_owner:
        return EMPTY, 0
    parts, total = [], 0
    for owner in sorted(by_owner):
        cards = sorted(by_owner[owner], key=lambda c: (c.get("期限") or "9999-99-99", c.id))
        rows = []
        for c in cards:
            mark = "**超過**" if ctx.overdue(c, "期限") else c.get("status")
            rows.append([c.id, ctx.head(c), c.get("期限"), mark, c.get("issue")])
        total += len(rows)
        parts.append("### 担当: %s\n\n%s" % (owner, _table(
            ["ID", "アクション", "期限", "状態", "Issue"], rows)))
    return "\n\n".join(parts), total


def _fragile_assumptions(ctx):
    """棚卸しの対象になる前提だけ。全件は追跡しない（2週25分では破綻する）。"""
    rows = []
    for c in sorted(ctx.of("ASM"), key=lambda c: c.id):
        if c.get("status") != "有効" or c.get("脆弱性") != "高":
            continue
        if not c.list("崩れたら見直す決定"):
            continue
        due = "**期限超過**" if ctx.overdue(c, "次回確認日") else c.get("次回確認日")
        rows.append([c.id, ctx.head(c), c.get("signpost"),
                     " / ".join(c.list("崩れたら見直す決定")), due])
    return _table(["ID", "前提", "signpost", "崩れたら見直す決定", "次回確認日"], rows), len(rows)


def _pending_scope(ctx):
    """受託開発では最優先で見る欄。ここで無理に判定すると追加請求の根拠を失う。"""
    rows = [[c.id, ctx.head(c), c.get("種別"), c.get("決定日")]
            for c in sorted(ctx.of("DEC"), key=lambda c: c.id)
            if c.get("範囲") == "判定保留"]
    return _table(["ID", "決定", "種別", "決定日"], rows), len(rows)


def _guessed(ctx):
    """`信頼度: 推測` のカード。人間が確認するまで昇格させない。"""
    rows = []
    for c in sorted(ctx.of("DEC", "Q", "ACT", "CON", "ASM"), key=lambda c: (c.type, c.id)):
        if c.get("信頼度") == "推測":
            rows.append([c.id, ctx.o.label(c.type), ctx.head(c), c.get("引用")])
    return _table(["ID", "種別", "内容", "引用"], rows), len(rows)


def _unconfirmed(ctx):
    """みなし確定の書き戻し待ち。"""
    rows = [[c.id, ctx.head(c), c.get("決定日"), c.get("会議体")]
            for c in sorted(ctx.of("DEC"), key=lambda c: c.id)
            if c.get("status") == "決定" and not c.get("確定日")]
    return _table(["ID", "決定", "決定日", "会議体"], rows), len(rows)


# ------------------------------------------------------------ ビュー

def view_open_items(ctx):
    """横断ビュー — いま開いているものを1枚に集める。"""
    why, n_why = _why_missing(ctx)
    questions, n_q = _open_questions(ctx)
    actions, n_act = _open_actions(ctx)
    assumptions, n_asm = _fragile_assumptions(ctx)
    pending, n_pending = _pending_scope(ctx)
    guessed, n_guess = _guessed(ctx)
    unconfirmed, n_unconf = _unconfirmed(ctx)

    out = [_header("open-items", ctx), "", "# 開いているもの", "",
           "会議をまたいで「まだ閉じていないもの」を集めたビュー。"
           "カードから毎回生成する。", "",
           _table(["区分", "件数"],
                  [["`なぜ` 未記入の決定", n_why],
                   ["未決の問い", n_q],
                   ["未完了のアクション", n_act],
                   ["棚卸し対象の前提", n_asm],
                   ["`範囲: 判定保留` の決定", n_pending],
                   ["`信頼度: 推測` のカード", n_guess],
                   ["`確定日` 未記入の決定", n_unconf]]), ""]

    out.append(_section("範囲が判定保留の決定", pending,
                        "受託開発では最優先。ここで無理に判定すると、"
                        "後で追加請求の根拠を失う。"))
    out.append(_section("`なぜ` が未記入の決定", why,
                        "次回アジェンダの冒頭に掲示される。"
                        "未記入のあいだ、この決定は制約・前提へ昇格できない。"))
    out.append(_section("未決の問い", questions))
    out.append(_section("未完了のアクション", actions,
                        "status の更新は定例会議でのみ行う"
                        "（相手社のアクションの完了を自社では判定できない）。"))
    out.append(_section("棚卸し対象の前提", assumptions,
                        "`脆弱性: 高` かつ逆リンクを持つものだけ。四半期に1回、5分で確認する。"))
    out.append(_section("信頼度が推測のカード", guessed,
                        "引用が照合できなかったか、沈黙を根拠にした判定。"
                        "人間が確認するまで昇格させない。"))
    out.append(_section("確定日が未記入の決定", unconfirmed,
                        "顧客提出版の送付後、異議なく確定した日を書き戻す。"))
    return "\n".join(out).rstrip() + "\n"


def view_agenda_next(ctx):
    """次回アジェンダ — 「引く動機」を作るためのビュー。"""
    why, n_why = _why_missing(ctx)
    questions, n_q = _open_questions(ctx)
    actions, n_act = _open_actions(ctx)
    assumptions, n_asm = _fragile_assumptions(ctx)

    latest = ctx.wiki.latest_meeting()
    out = [_header("agenda-next", ctx), "", "# 次回アジェンダ（案）", ""]
    out.append("前回: %s" % (latest.id if latest else "（記録なし）"))
    out.append("")
    out.append("溜める動機より引く動機を先に作る。"
               "このアジェンダが読まれない記録は死んでいる。")
    out.append("")

    out.append(_section("0. `なぜ` が未記入の決定（冒頭で確認）", why,
                        "書かないことに付けたコスト。ここが埋まるまで"
                        "制約・前提への昇格ができない。"))
    out.append(_section("1. 前回からの未完了アクション", actions))
    out.append(_section("2. 未決の問い", questions))
    out.append(_section("3. 前提の棚卸し（四半期に1回・5分）", assumptions,
                        "signpost に照らして「崩れたか」だけを見る。"))
    out.append("---\n")
    out.append("所要の目安: 決定の理由 %d件 / アクション %d件 / 問い %d件 / 前提 %d件"
               % (n_why, n_act, n_q, n_asm))
    return "\n".join(out).rstrip() + "\n"


def view_index(ctx):
    """全カードの一覧。"""
    out = [_header("index", ctx), "", "# カード一覧", ""]

    rows = []
    for meeting_id in sorted(ctx.wiki.meetings):
        logs = ctx.wiki.logs_of(meeting_id)
        cards = ctx.wiki.cards_of_meeting(meeting_id, "DEC", "Q", "ACT", "CON", "ASM")
        rows.append([meeting_id, ctx.wiki.meetings[meeting_id].date, len(logs), len(cards)])
    out.append(_section("会議", _table(["会議", "日付", "LOG", "生成・更新されたカード"], rows),
                        "1枚のカードが複数の会議に現れるのは正常"
                        "（会議をまたいで更新されたということ）。"))

    for type_name in ctx.o.type_names():
        cards = sorted(ctx.of(type_name), key=lambda c: c.id)
        if type_name == "LOG":
            rows = [[c.id, ctx.head(c), c.get("種別"), c.get("meeting")] for c in cards]
            body = _table(["ID", "論点", "種別", "会議"], rows)
        else:
            rows = [[c.id, ctx.head(c), c.get("status"), ctx.meetings_label(c)] for c in cards]
            body = _table(["ID", "内容", "status", "会議"], rows)
        out.append(_section("%s — %s（%d件）" % (type_name, ctx.o.label(type_name), len(cards)),
                            body))
    return "\n".join(out).rstrip() + "\n"


def view_metrics(ctx):
    """判定基準のうち、機械で算出できる分だけ。"""
    decisions = ctx.of("DEC")
    n_dec = len(decisions)
    with_why = sum(1 for c in decisions if c.get("なぜ"))
    alternatives = [row for c in decisions for row in c.structs("代替案")
                    if isinstance(row, dict)]
    no_reason = sum(1 for row in alternatives if row.get("却下理由") == "記録なし")
    silent_alt = sum(1 for row in alternatives if row.get("信頼度") == "推測")
    guessed = sum(1 for c in ctx.of("DEC", "Q", "ACT", "CON", "ASM")
                  if c.get("信頼度") == "推測")
    broken_asm = sum(1 for c in ctx.of("ASM") if c.get("status") == "崩れた")
    derived = sum(1 for c in ctx.of("DEC") if c.get("確定日"))

    def pct(a, b):
        return "—" if not b else "%d%% (%d/%d)" % (round(100 * a / b), a, b)

    out = [_header("metrics", ctx), "", "# 指標", "",
           "README「判定基準」のうち、機械で数えられる分だけ。"
           "残り（網羅性、アジェンダが使われた回数、矛盾検出の発火）は人が見る。", ""]

    out.append(_section("土台", _table(["指標", "値"], [
        ["決定", n_dec],
        ["未決の問い（未決のみ）", sum(1 for c in ctx.of("Q") if c.get("status") == "未決")],
        ["未完了のアクション", sum(1 for c in ctx.of("ACT")
                                   if c.get("status") not in ("完了", "取り下げ"))],
        ["`確定日` が入った決定", pct(derived, n_dec)],
    ])))

    out.append(_section("上乗せ", _table(["指標", "読み方", "値"], [
        ["`なぜ` の記入率", "低いままなら上乗せ層が育っていない", pct(with_why, n_dec)],
        ["`却下理由: 記録なし` の比率", "高いままなら、会議で代替案が言語化されていない。"
                                        "Wiki の問題ではなく意思決定の仕方の問題",
         pct(no_reason, len(alternatives))],
        ["沈黙由来の代替案", "口に出たが誰も反応しなかった案。"
                               "議事録には残らない、この仕組みでしか取れない分", silent_alt],
        ["昇格した制約", "却下理由から環境の性質が抽出できているか", len(ctx.of("CON"))],
        ["昇格した前提", "うち棚卸し対象のみが運用される", len(ctx.of("ASM"))],
        ["前提の「崩れた」判定", "逆リンクが機能しているか。1件でも出れば元は取れている", broken_asm],
        ["OpenSpec が `derived_from` で引いた決定", "第2次まで 0 のまま（連携は未実装）", 0],
    ])))

    out.append(_section("共通", _table(["指標", "値"], [
        ["`信頼度: 推測` のカード", guessed],
        ["用語", len(ctx.of("TERM"))],
        ["LOG", len(ctx.of("LOG"))],
    ]), "**引用一致率をここに置かない。** これはグラウンディングの健全性チェックで"
        "あって、議事録の品質指標ではない。自動指標を品質指標に昇格させると"
        "AutoMin 2025 と同じ罠に落ちる（同一システムの BART-F1 が年をまたいで"
        "負の相関を示した）。"))
    return "\n".join(out).rstrip() + "\n"


VIEWS = {
    "open-items": view_open_items,
    "agenda-next": view_agenda_next,
    "index": view_index,
    "metrics": view_metrics,
}


def render(wiki, name, today=None):
    return VIEWS[name](Ctx(wiki, today))


def generate(wiki, only=None, today=None, check=False):
    """ビューを書き出す。check なら書かずに差分の有無だけを返す。"""
    ctx = Ctx(wiki, today)
    names = [only] if only else list(VIEWS)
    stale, written = [], []
    directory = wiki.views_dir
    if not check:
        directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        text = VIEWS[name](ctx)
        path = directory / ("%s.md" % name)
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == text:
            continue
        if check:
            stale.append(name)
        else:
            path.write_text(text, encoding="utf-8")
            written.append(name)
    return written, stale


def main(argv=None):
    ap = argparse.ArgumentParser(prog="giji views", description="カードからビューを生成する")
    ap.add_argument("--root", default=None, help="案件ディレクトリ")
    ap.add_argument("--only", choices=sorted(VIEWS), default=None)
    ap.add_argument("--check", action="store_true", help="書かずに鮮度だけを見る")
    ap.add_argument("--today", default=None, help="生成基準日（YYYY-MM-DD）")
    ap.add_argument("--out", default=None, help="- を渡すと標準出力へ（--only と併用）")
    args = ap.parse_args(argv)

    today = datetime.date.fromisoformat(args.today) if args.today else None
    wiki = Wiki(resolve_root(args.root), schema.load())

    if args.out == "-":
        if not args.only:
            print("--out - は --only と併用する", file=sys.stderr)
            return 2
        print(render(wiki, args.only, today), end="")
        return 0

    written, stale = generate(wiki, args.only, today, args.check)
    if args.check:
        for name in stale:
            print("views/%s.md が古い（`giji views` で再生成する）" % name)
        print("ビュー: %d件が古い" % len(stale))
        return 1 if stale else 0
    for name in written:
        print("views/%s.md を生成した" % name)
    print("ビュー: %d件を更新（変更なし %d件）" % (len(written), len(VIEWS) - len(written)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
