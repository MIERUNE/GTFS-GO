#!/usr/bin/env python3
"""翻訳キーの抽出・更新ツール (Qt の pylupdate 代替)。

ソース中の ``tr("...")`` / ``i18n.tr("...")`` 呼び出しの文字列リテラルを ast で、
.ui ファイルの ``<string>`` を XML として収集し、`i18n/<locale>.json` を更新する:

  - コードに在るが JSON に無いキー  -> 空訳 "" を追加（未翻訳として）
  - JSON に在るがコードに無いキー    -> 「未使用」として報告（削除はしない）
  - 既存の訳は保持

リテラルでない引数（f-string・変数渡し）は静的に拾えないため警告する。
.ui の ``<string notr="true">`` は翻訳対象外。

使い方:
    python3 i18n/extract.py            # i18n/ja.json を更新
    python3 i18n/extract.py --locale en
    python3 i18n/extract.py --check    # 変更が必要なら非0終了（CI用）
"""

import argparse
import ast
import json
import os
import sys
import xml.etree.ElementTree as ET  # nosec B405

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 走査対象外。翻訳対象は実行コードのみ（テスト/依存/i18n自身は除外）。
# gtfs_parser はサブモジュールで UI 文字列を持たない。
EXCLUDE_DIRS = {
    ".venv",
    ".git",
    ".claude",
    "tests",
    "i18n",
    "__pycache__",
    "gtfs_parser",
}


def _iter_files(root: str, ext: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for name in filenames:
            if name.endswith(ext):
                yield os.path.join(dirpath, name)


def _is_tr_call(node: ast.Call) -> bool:
    """``tr(...)`` または ``i18n.tr(...)`` の呼び出しか。"""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "tr"
    if isinstance(func, ast.Attribute):
        return func.attr == "tr"
    return False


def collect(root: str):
    """(翻訳キー集合, 動的引数の警告リスト) を返す。"""
    keys: set[str] = set()
    warnings: list[str] = []
    for path in _iter_files(root, ".py"):
        with open(path, encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read(), filename=path)
            except SyntaxError as e:
                warnings.append(f"{path}: parse error: {e}")
                continue
        rel = os.path.relpath(path, root)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and _is_tr_call(node) and node.args):
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                keys.add(first.value)
            else:
                warnings.append(
                    f"{rel}:{node.lineno}: tr() に非リテラル引数（抽出不可）"
                )
    for path in _iter_files(root, ".ui"):
        tree = ET.parse(path)  # nosec B314
        for string in tree.iter("string"):
            if string.text and string.get("notr") != "true":
                keys.add(string.text)
    return keys, warnings


def update(locale: str, check: bool) -> int:
    keys, warnings = collect(ROOT)
    path = os.path.join(ROOT, "i18n", f"{locale}.json")
    existing = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            existing = json.load(f)

    # 既存の訳を保持し、コードにある新規キーを空訳 "" で追加する。
    # コードから消えたキーは「未使用」として報告するだけで削除しない（破壊的変更を避ける）。
    merged = dict(existing)
    for k in keys:
        merged.setdefault(k, "")
    unused = sorted(set(existing) - keys)
    added = sorted(k for k in keys if k not in existing)

    # 未使用キーが在るだけでは --check を失敗させない。新規キー追加時のみ更新が必要。
    changed = merged != existing
    if check:
        if changed:
            print(
                "i18n: 更新が必要です。`python3 i18n/extract.py` を実行してください。"
            )
        for k in added:
            print(f"  + 新規キー（未翻訳）: {k!r}")
    else:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        print(f"i18n: {path} を更新（{len(merged)} キー, 新規 {len(added)}）")

    for k in unused:
        print(f"  - 未使用（コードに無い）: {k!r}")
    for w in warnings:
        print(f"  ! {w}")

    untranslated = [k for k in keys if not merged.get(k)]
    if untranslated:
        print(f"i18n: 未翻訳 {len(untranslated)} キー")

    return 1 if (check and changed) else 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--locale", default="ja")
    p.add_argument("--check", action="store_true", help="変更が必要なら非0終了（CI用）")
    args = p.parse_args()
    return update(args.locale, args.check)


if __name__ == "__main__":
    sys.exit(main())
