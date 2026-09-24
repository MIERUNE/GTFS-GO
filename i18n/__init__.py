"""Lightweight translation utility.

Qt の .ts/.qm パイプラインの代わりに、原文(英語)をキーにした JSON 辞書を引く。
ロケール検出は呼び出し側の責務とし、ここは「辞書ロード + ルックアップ」だけを担う。
.ui ファイルの文字列は ``translate_widget()`` でロード後に差し替える。
"""

import json
import os

# 現在ロード中の翻訳辞書（原文 -> 訳文）。未ロード時は空 = 全て原文フォールバック。
_translations: dict = {}

# .ui 由来の文字列を持つウィジェットのプロパティ
_UI_PROPERTIES = ("windowTitle", "text", "title", "placeholderText", "toolTip")


def load(locale: str) -> None:
    """同ディレクトリの ``<locale>.json`` を読み込む。

    locale は QGIS のロケール文字列。"ja" のことも "ja_JP" のこともあるため、
    完全一致 → 言語部分（"ja"）の順に探す。どれも無ければ辞書を空にし、tr() は
    原文をそのまま返す（英語フォールバック）。
    """
    global _translations
    here = os.path.dirname(__file__)
    candidates = [locale]
    lang = locale.split("_")[0]
    if lang != locale:
        candidates.append(lang)
    for name in candidates:
        path = os.path.join(here, f"{name}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                _translations = json.load(f)
            return
    _translations = {}


def tr(message: str) -> str:
    """原文をキーに訳文を引く。未登録または空訳なら原文を返す。

    抽出ツールは未翻訳キーを空文字 "" として JSON に追加するため、空訳も
    「未翻訳」とみなして原文（英語）にフォールバックする。

    プレースホルダは原文側にそのまま書き（例 ``i18n.tr("count: {}").format(n)``）、
    .format() 等は呼び出し側で適用する。
    """
    return _translations.get(message) or message


def translate_widget(root) -> None:
    """``uic.loadUi()`` したウィジェットとその子孫の .ui 由来の文字列を訳す。

    訳がある文字列だけを差し替えるので、QGIS 側で訳されたウィジェット内部の
    文字列などには触れない。
    """
    from qgis.PyQt.QtWidgets import QWidget

    for widget in [root, *root.findChildren(QWidget)]:
        for name in _UI_PROPERTIES:
            value = widget.property(name)
            if isinstance(value, str) and _translations.get(value):
                widget.setProperty(name, _translations[value])
