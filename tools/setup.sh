#!/bin/sh
# 初回セットアップ — 門を立て、対象の案件を指し、一度通す。
#
# **`git config core.hooksPath .githooks` を忘れると、門は立たない。**
# README は `.githooks/pre-commit` を「5段の門」として案内しているので、
# 設定し忘れた人は「門がある」と思ったまま門の無い状態で作業することになる。
# 手で打たせずに済ませるために置いている。
#
#   sh tools/setup.sh              門を立てるだけ
#   sh tools/setup.sh demo-kb      あわせて .env に案件を書き、Obsidian の設定を置く
#
# Obsidian は案件ごとに vault として開く（docs/obsidian.md）。置くのは
# templates/obsidian/ の事故防止の設定だけで、既に .obsidian/ があれば触らない
# （個人の設定を上書きしない。.obsidian/ は gitignore 済み）。
set -e

root=$(git rev-parse --show-toplevel)
cd "$root"

git config core.hooksPath .githooks
echo "1. pre-commit を有効にした（core.hooksPath = .githooks）"

if [ -n "$1" ]; then
    if [ ! -d "projects/$1" ]; then
        echo "   projects/$1 が無い。雛形から作る:" >&2
        echo "     cp -r templates/project projects/$1" >&2
        exit 1
    fi
    echo "CURRENT_PROJECT=$1" > .env
    echo "2. .env を書いた（CURRENT_PROJECT=$1）"
    if [ -d "projects/$1/.obsidian" ]; then
        echo "   Obsidian: projects/$1/.obsidian は既にある。触らない"
        echo "   （「内部リンクを自動更新」はオフにしておく。ID = ファイル名が崩れる）"
    else
        cp -r templates/obsidian "projects/$1/.obsidian"
        echo "   Obsidian: projects/$1/.obsidian に設定を置いた（vault は projects/$1）"
    fi
elif [ -f .env ]; then
    echo "2. .env は既にある: $(tr -d '\n' < .env)"
else
    echo "2. .env が無い。対象の案件を決めたら:"
    echo "     echo \"CURRENT_PROJECT=<案件名>\" > .env"
fi

echo "3. 門を一度通す"
sh .githooks/pre-commit --all
