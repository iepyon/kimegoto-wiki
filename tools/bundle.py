#!/usr/bin/env python3
"""入力バンドル — LLM に渡す材料を決定論的に組み立てる。

CLI と LLM の境界をここで引く。

**CLI がやること**: どのカードが対象かを決め、逐語のまま並べる。
  「対象の選定」は決定論で決まる。LLM に判断させると取りこぼす
  （会議要約のエラー内訳は 欠落 89% / 幻覚 26%。最大のエラー源は欠落）。

**CLI がやること その2**: 顧客提出版で出せない情報を落とす。
  漏れたら契約上の事故になる。LLM の遵守に賭けない。除外規則は
  ontology.yaml の editions に宣言として置き、ここはそれを実行するだけ。

**LLM がやること**: 残った情報の文章化だけ。

議事録はファイルに保存しない。保存するとカードを更新したときに古くなり、
二重管理が復活する。カードが唯一の真実で、議事録はその射影。
"""

import argparse
import datetime
import sys

from tools import schema
from tools.cards import Wiki, resolve_root

EMPTY = "（なし）"


class Bundle:
    def __init__(self, wiki, today=None):
        self.wiki = wiki
        self.o = wiki.ontology
        self.today = today or datetime.date.today()
        self.dropped = []   # 顧客提出版で落としたもの（脚注に出す）

    # ------------------------------------------------------------ 補助

    def head(self, card):
        return card.headline(self.o)

    def company_of(self, role):
        """役割を社名に丸める。顧客提出版でのみ使う。

        **すでに社名である値はそのまま返す。** ACT の `担当` は
        `schema.md` の定義どおり社名で持っており、役割として引き当てると
        `unknown_role_default` に落ちて「不明」になってしまう
        （顧客に出す文書から約束の主体が消える）。
        """
        if not role:
            return role
        if role in self.wiki.companies:
            return role
        info = self.wiki.role(role) or {}
        return info.get("社名") or role

    def note_drop(self, what, why):
        self.dropped.append((what, why))

    # -------------------------------------------------- 顧客版のフィルタ

    def _excluded(self, card, edition):
        """このカードを丸ごと落とすか。"""
        for rule in self.o.edition(edition).get("exclude", []):
            if card.type != rule.get("type"):
                continue
            if card.get(rule.get("field")) == rule.get("value"):
                self.note_drop("%s（%s）" % (card.id, self.head(card)),
                               rule.get("reason") or "")
                return True
        return False

    def _alternatives(self, card, edition):
        """代替案のうち、出してよい行だけ。"""
        rules = self.o.edition(edition).get("exclude-alternatives", [])
        out = []
        for row in card.structs("代替案"):
            if not isinstance(row, dict):
                continue
            hit = next((r for r in rules if row.get(r.get("field")) == r.get("value")), None)
            if hit:
                self.note_drop("%s の代替案「%s」" % (card.id, row.get("案") or "?"),
                               hit.get("reason") or "")
                continue
            out.append(row)
        return out

    def _fields(self, card, edition):
        """出してよいフィールドだけを順序を保って返す。"""
        spec = self.o.edition(edition)
        drop = set(spec.get("drop-fields", []))
        drop_values = {(r.get("field"), r.get("value"))
                       for r in spec.get("drop-field-values", [])}
        out = []
        for name, value in card.data.items():
            if name in drop or name == "type":
                continue
            if isinstance(value, str) and (name, value) in drop_values:
                continue
            out.append((name, value))
        return out

    # ------------------------------------------------------ 議事録の材料

    def minutes_input(self, meeting_id, edition="internal"):
        if meeting_id not in self.wiki.meetings:
            raise KeyError("会議 %s が無い" % meeting_id)
        meeting = self.wiki.meetings[meeting_id]
        self.dropped = []
        customer = edition == "customer"

        logs = sorted(self.wiki.logs_of(meeting_id), key=lambda c: c.id)
        current = self.wiki.cards_of_meeting(meeting_id, "DEC", "Q", "ACT", "CON", "ASM")
        carried = [c for c in self.wiki.by_type("ACT")
                   if c.error is None
                   and c.get("status") not in ("完了", "取り下げ")
                   and meeting_id not in self.wiki.meetings_of(c)]

        out = ["# 議事録の材料 — %s（%s版）" % (meeting_id, "顧客提出" if customer else "社内"), ""]
        out.append("この束は `kime minutes-input` が機械的に集めたもの。"
                   "**ここに無いことを書かない。空欄は空欄として扱う。**")
        out.append("")
        out.append("- 会議: %s（%s）" % (meeting_id, meeting.date))
        roles = sorted({r for c in logs for r in c.list("参加役割")})
        if customer:
            roles = sorted({self.company_of(r) for r in roles})
        out.append("- 参加: %s" % (" / ".join(roles) or "—"))
        body = next((c.get("会議体") for c in current if c.get("会議体")), "")
        if body:
            out.append("- 会議体: %s" % body)
        out.append("")

        sections = [("決定事項", "DEC"), ("未決事項", "Q"), ("今回のアクション", "ACT"),
                    ("新たに記録した制約", "CON"), ("新たに記録した前提", "ASM")]
        for title, type_name in sections:
            cards = [c for c in current if c.type == type_name]
            if customer:
                cards = [c for c in cards if not self._excluded(c, edition)]
            out.append("## %s" % title)
            out.append("")
            if not cards:
                out.append(EMPTY)
                out.append("")
                continue
            for card in sorted(cards, key=lambda c: c.id):
                out.extend(self._render_card(card, edition, customer))
            out.append("")

        out.append("## 前回からの繰越アクション")
        out.append("")
        if carried:
            for card in sorted(carried, key=lambda c: c.id):
                out.extend(self._render_card(card, edition, customer))
        else:
            out.append(EMPTY)
        out.append("")

        if not customer:
            out.append("## 議論の経緯（LOG）")
            out.append("")
            for log in logs:
                out.append("### %s %s（%s・%s）"
                           % (log.id, self.head(log), log.get("種別"), log.get("時刻") or "—"))
                out.append("")
                for role, text in log.utterances:
                    out.append("- **%s**: %s" % (role, text))
                out.append("")

        out.extend(self._footer(edition, customer))
        return "\n".join(out).rstrip() + "\n"

    def _render_card(self, card, edition, customer):
        out = []
        title = self.head(card)
        out.append("### %s" % (title if customer else "%s %s" % (card.id, title)))
        out.append("")
        for name, value in self._fields(card, edition):
            if name in ("title", "内容", "正式", "代替案"):
                continue
            if value in ("", [], None):
                continue
            if customer and name in ("決定の所在", "確認先", "担当"):
                value = self.company_of(value)
            if isinstance(value, list):
                value = " / ".join(str(v) for v in value if not isinstance(v, dict))
                if not value:
                    continue
            out.append("- %s: %s" % (name, value))
        alternatives = self._alternatives(card, edition) if card.type == "DEC" else []
        if alternatives:
            out.append("- 代替案:")
            for row in alternatives:
                line = "    - %s — %s" % (row.get("案", "?"), row.get("却下理由", "?"))
                if not customer and row.get("引用"):
                    line += "（引用: %s / %s）" % (row.get("引用"), row.get("信頼度", ""))
                out.append(line)
        out.append("")
        return out

    def _skeleton(self, edition):
        """議事録の節構成。正本は ontology.yaml の editions.<版>.sections。

        散文でスキルに持たせると、版を足したときに必ず片方が古くなる。
        """
        sections = self.o.sections_of(edition)
        if not sections:
            return []
        out = ["## 議事録の骨格（この見出しを、この順で使う）", ""]
        for i, (title, note) in enumerate(sections, start=1):
            out.append("%d. **%s**%s" % (i, title, " — %s" % note if note else ""))
        out.append("")
        return out

    def _footer(self, edition, customer):
        out = ["---", ""]
        out.extend(self._skeleton(edition))
        if customer:
            out.append("## 顧客提出版で守ること")
            out.append("")
            out.append("- 役割は社名に丸める。カード ID と逐語引用は出さない")
            out.append("- 「却下」→「採用しなかった」、「作らない」→「本フェーズの対象外」")
            out.append("- 未確定のものは断定せず `確認事項` に移す")
            if self.o.edition(edition).get("deemed-confirmation"):
                days = self.o.threshold("deemed-confirmation-business-days")
                out.append("")
                out.append("末尾に次の一文を必ず入れる:")
                out.append("")
                out.append("> 本議事録は、送付後%d営業日以内にご異議のない場合、"
                           "記載内容をもって確定とさせていただきます。" % days)
            out.append("")
            out.append("### 機械的に落としたもの（%d件）" % len(self.dropped))
            out.append("")
            # **中身をここに書かない。** この束はそのまま顧客提出版の材料になる。
            # 落としたカードの ID や代替案の名前を脚注に残すと、LLM がそれを本文に
            # 混ぜうる。何が落ちたかは標準エラーに出し、社内で確認する。
            if self.dropped:
                reasons = {}
                for _, why in self.dropped:
                    reasons[why] = reasons.get(why, 0) + 1
                for why in sorted(reasons):
                    out.append("- %s: %d件" % (why or "（理由の記載なし）", reasons[why]))
                out.append("")
                out.append("内訳は標準エラーに出している（この束には含めない）。")
            else:
                out.append(EMPTY)
        else:
            out.append("社内版はすべて出す。リーダのレビュー後、"
                       "必要なら `--edition customer` で顧客提出版を作る。")
        return out

    # ------------------------------------------------ Pass 4 の入力

    def _assumption_hits(self, card):
        """`なぜ` と却下理由に現れた前提のトリガー語。

        語リストの正本は `ontology.yaml` の `assumption-trigger-words`。
        **検出は機械、昇格の可否は人間。** ここは印を付けるだけで、
        前提カードの候補にするかどうかは Pass 4 が判断する。
        """
        haystack = [("なぜ", card.get("なぜ") or "")]
        for row in card.structs("代替案"):
            if isinstance(row, dict) and row.get("却下理由"):
                haystack.append(("代替案「%s」の却下理由" % (row.get("案") or "?"),
                                 row["却下理由"]))
        hits = []
        for where, text in haystack:
            for word in self.o.assumption_trigger_words:
                if word and word in text:
                    hits.append((where, word, text))
        return hits

    @staticmethod
    def _recorded_reasons(card):
        """`却下理由` が実際に記録されている代替案。`記録なし` と空は数えない。"""
        return [row for row in card.structs("代替案")
                if isinstance(row, dict)
                and (row.get("却下理由") or "").strip() not in ("", "記録なし")]

    def promote_input(self, meeting_id):
        """昇格候補を出すための材料。

        **理由がどこにも記録されていない決定はここで落とす。** プロンプトの
        注意書きではなく、入力の欠落で門を閉じる。理由の書かれていない決定から
        制約が生まれると、将来の議論でその制約だけが効いてしまう。

        門を通す条件は `なぜ` **または** `代替案[].却下理由` のどちらかがあること。
        CON の中身は「採った案の理由（`なぜ`）」ではなく「捨てた案の理由
        （`却下理由`）」なので、`なぜ` だけで閉じると、逐語で却下理由が取れている
        制約まで落ちてしまう（`decision-guide.md` も両者を別物と定めている）。
        """
        if meeting_id not in self.wiki.meetings:
            raise KeyError("会議 %s が無い" % meeting_id)
        decisions = [c for c in self.wiki.cards_of_meeting(meeting_id, "DEC")]
        passed = [c for c in decisions
                  if c.get("なぜ") or self._recorded_reasons(c)]
        blocked = [c for c in decisions
                   if not c.get("なぜ") and not self._recorded_reasons(c)]
        logs = sorted(self.wiki.logs_of(meeting_id), key=lambda c: c.id)
        terms = sorted(self.wiki.by_type("TERM"), key=lambda c: c.id)

        out = ["# 昇格候補の材料 — %s" % meeting_id, "",
               "制約（CON）・前提（ASM）・用語（TERM）の候補を出すための材料。",
               "**カードは作らない。** 候補を挙げるところまでで、"
               "承認は人間が yes/no で行う。", ""]

        out.append("## 決定と却下理由（昇格の門を通ったもの）")
        out.append("")
        if passed:
            for c in sorted(passed, key=lambda c: c.id):
                out.append("### %s %s" % (c.id, self.head(c)))
                out.append("")
                out.append("- なぜ: %s" % (c.get("なぜ") or "（未記入）"))
                if c.get("受容した不利"):
                    out.append("- 受容した不利: %s" % c.get("受容した不利"))
                out.append("- derived_from: %s" % " / ".join(c.list("derived_from")))
                for row in c.structs("代替案"):
                    if isinstance(row, dict):
                        out.append("- 代替案: %s — 却下理由: %s（引用: %s / %s）"
                                   % (row.get("案", "?"), row.get("却下理由", "?"),
                                      row.get("引用", "—"), row.get("信頼度", "—")))
                out.append("")
        else:
            out.append(EMPTY)
            out.append("")

        out.append("## 前提のトリガー語が出ている決定")
        out.append("")
        out.append("`なぜ` と却下理由を機械で走査した結果。**これだけでは前提ではない。**")
        out.append("前提カードにするかは Pass 4 が判断し、"
                   "`崩れたら見直す決定` が特定できないものは候補に出さない。")
        out.append("")
        flagged = [(c, hits) for c in sorted(passed, key=lambda c: c.id)
                   for hits in [self._assumption_hits(c)] if hits]
        if flagged:
            for card, hits in flagged:
                for where, word, text in hits:
                    out.append("- %s の %s に `%s`: %s" % (card.id, where, word, text))
        else:
            out.append(EMPTY)
        out.append("")

        out.append("## 会話ログ")
        out.append("")
        for log in logs:
            out.append("### %s %s（%s）" % (log.id, self.head(log), log.get("種別")))
            out.append("")
            for role, text in log.utterances:
                out.append("- **%s**: %s" % (role, text))
            out.append("")

        out.append("## 既存の用語（表記揺れの追記先）")
        out.append("")
        if terms:
            for c in terms:
                out.append("- %s `%s`: %s" % (c.id, c.get("正式"),
                                              " / ".join(c.list("表記揺れ")) or "—"))
        else:
            out.append(EMPTY)
        out.append("")

        out.append("---")
        out.append("")
        out.append("## 候補の上限")
        out.append("")
        out.append("1回の会議で出す候補は **%d件まで**（根拠の強い順）。"
                   "人間が承認しきれない量を出さないための上限で、"
                   "取りこぼしても次回以降に拾える。量より確度を優先する。"
                   % self.o.threshold("promote-candidates-max"))
        out.append("")
        out.append("## 昇格の門で落とした決定（%d件）" % len(blocked))
        out.append("")
        if blocked:
            out.append("`なぜ` も `代替案[].却下理由` も記録されていないため、"
                       "この材料には含めていない。"
                       "理由が書かれるまで制約・前提へ昇格できない。")
            out.append("")
            for c in sorted(blocked, key=lambda c: c.id):
                out.append("- %s %s" % (c.id, self.head(c)))
        else:
            out.append(EMPTY)
        return "\n".join(out).rstrip() + "\n"

    # ------------------------------------------------ 確認②の25分

    def review(self, meeting_id):
        """確認②のチェックリスト。該当するカードだけを、順番と時間配分つきで出す。"""
        if meeting_id not in self.wiki.meetings:
            raise KeyError("会議 %s が無い" % meeting_id)
        current = self.wiki.cards_of_meeting(meeting_id, "DEC", "Q", "ACT", "CON", "ASM")

        def of(type_name):
            return sorted([c for c in current if c.type == type_name], key=lambda c: c.id)

        pending = [c for c in of("DEC") if c.get("範囲") == "判定保留"]
        guessed = [c for c in current if c.get("信頼度") == "推測"]
        no_why = [c for c in of("DEC") if not c.get("なぜ")]
        no_reason = [(c, row) for c in of("DEC") for row in c.structs("代替案")
                     if isinstance(row, dict) and row.get("却下理由") == "記録なし"]
        actions = [c for c in self.wiki.by_type("ACT")
                   if c.error is None and c.get("status") not in ("完了", "取り下げ")]

        out = ["# 確認② — %s（25分）" % meeting_id, "",
               "この25分は「書く」ではなく**判定**に使う。",
               "**`なぜ` と却下理由を LLM に書かせない。**"
               "書けない場合は `記録なし` を入れる。空欄は情報であり、埋めるべき穴ではない。", ""]

        out += self._step("2-0", "`範囲: 判定保留` の決定", "3分",
                          "受託開発では最優先。他を飛ばしてもここは見る。"
                          "無理に判定すると追加請求の根拠を失う。",
                          [["ID", "決定", "種別", "決定日"]] +
                          [[c.id, self.head(c), c.get("種別"), c.get("決定日")] for c in pending])

        out += self._step("2-1", "`信頼度: 推測` のカード", "4分",
                          "引用が照合できなかったか、沈黙を根拠にした判定。"
                          "拾い漏れが無いかもここで見る。",
                          [["ID", "種別", "内容", "引用"]] +
                          [[c.id, self.o.label(c.type), self.head(c), c.get("引用")]
                           for c in guessed])

        rows = [["ID", "決定", "なぜ（Y-statement の穴埋め）"]]
        rows += [[c.id, self.head(c), "〈場面〉で〈懸念〉に直面し、〈採った案〉を選んだ。"
                                      "〈狙い〉のためであり、〈受容した不利〉を受け入れる。"]
                 for c in no_why]
        out += self._step("2-2", "決定の `なぜ` を1行書く", "8分",
                          "全部書けなくてよい。1つでも埋まれば空欄より価値がある。"
                          "未記入のあいだ、この決定は制約・前提へ昇格できない。", rows)

        if no_reason:
            out.append("  `却下理由: 記録なし` の代替案（埋められるなら埋める。"
                       "思い出せないなら `記録なし` のままにする）:")
            out.append("")
            for card, row in no_reason:
                out.append("  - %s: %s（引用: %s）"
                           % (card.id, row.get("案", "?"), row.get("引用") or "—"))
            out.append("")

        rows = [["ID", "アクション", "担当", "期限", "status"]]
        rows += [[c.id, self.head(c), c.get("担当"), c.get("期限"), c.get("status")]
                 for c in sorted(actions, key=lambda c: c.id)]
        out += self._step("2-3", "アクションの担当・期限・status", "4分",
                          "空欄が正常な出力。ここで人間が埋める。"
                          "前回アクションの status もこの場で更新する。", rows)

        out += self._step("2-4", "昇格候補の承認", "6分",
                          "`kime promote-input` の材料から Pass 4 を回し、"
                          "出てきた候補を yes/no で承認する。"
                          "前提は `脆弱性: 高` のものだけ。迷ったら昇格させない。", [])

        out.append("---")
        out.append("")
        out.append("この確認を飛ばすと、捏造された Wiki ができる。"
                   "25分が払えない週は、Pass 3 で止めて翌週まとめて行うほうがまだよい。")
        return "\n".join(out).rstrip() + "\n"

    def _step(self, number, title, minutes, note, rows):
        out = ["## %s %s（%s）" % (number, title, minutes), "", note, ""]
        if not rows:
            out += ["", ""]
            return out
        header, body = rows[0], rows[1:]
        if not body:
            out += ["0件", ""]
            return out
        out.append("| %s |" % " | ".join(header))
        out.append("|%s|" % "|".join(["---"] * len(header)))
        for row in body:
            out.append("| %s |" % " | ".join(str(c) if c else "—" for c in row))
        out.append("")
        return out


# ------------------------------------------------------------ CLI

def _run(argv, kind):
    ap = argparse.ArgumentParser(prog="kime %s" % kind)
    ap.add_argument("--meeting", default=None, help="会議 ID（既定: 最新）")
    ap.add_argument("--root", default=None, help="案件ディレクトリ")
    ap.add_argument("--today", default=None)
    if kind == "minutes-input":
        ap.add_argument("--edition", choices=["internal", "customer"], default="internal")
    args = ap.parse_args(argv)

    wiki = Wiki(resolve_root(args.root), schema.load())
    today = datetime.date.fromisoformat(args.today) if args.today else None
    meeting_id = args.meeting
    if not meeting_id:
        latest = wiki.latest_meeting()
        if latest is None:
            print("会議が1つも無い", file=sys.stderr)
            return 2
        meeting_id = latest.id

    bundle = Bundle(wiki, today)
    try:
        if kind == "minutes-input":
            print(bundle.minutes_input(meeting_id, args.edition), end="")
            if bundle.dropped:
                print("\n顧客提出版で落としたもの（%d件）:" % len(bundle.dropped),
                      file=sys.stderr)
                for what, why in bundle.dropped:
                    print("  - %s — %s" % (what, why), file=sys.stderr)
        elif kind == "promote-input":
            print(bundle.promote_input(meeting_id), end="")
        else:
            print(bundle.review(meeting_id), end="")
    except KeyError as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0


def main_minutes(argv=None):
    return _run(argv or [], "minutes-input")


def main_promote(argv=None):
    return _run(argv or [], "promote-input")


def main_review(argv=None):
    return _run(argv or [], "review")
