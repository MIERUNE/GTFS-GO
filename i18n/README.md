# 翻訳ガイド (Translation Guide)

このプラグインは Qt の .ts/.qm パイプラインを使わず、**原文(英語)をキーにした
JSON 辞書**で翻訳する（[kumoy-qgis-plugin](https://github.com/MIERUNE/kumoy-qgis-plugin) と同じ方式）。
`i18n/__init__.py` が辞書のロードとルックアップを担う。

## ファイル構成

```
i18n/
├── __init__.py   # load(locale) / tr(message) / translate_widget(widget)
├── extract.py    # コードの tr("...") と .ui の <string> を抽出して JSON を更新（pylupdate 相当）
├── ja.json       # 日本語訳（原文 -> 訳文）
└── fr.json       # フランス語訳
```

## 仕組み

1. **翻訳関数**: コード側は `i18n.tr("英語原文")` を呼ぶ。`tr()` は辞書を引き、未登録または
   空訳なら原文をそのまま返す（＝英語フォールバック）。コンテキスト名は無い。
2. **言語検出**: プラグイン初期化時に `i18n.load(QgsApplication.instance().locale())` を
   1回呼び、`<locale>.json` を読み込む。QGIS のロケール変更は QGIS 再起動で反映される。
3. **.ui ファイル**: `uic.loadUi()` の直後に `i18n.translate_widget(self)` を呼び、
   ウィジェットの `text` / `title` / `windowTitle` などを辞書で差し替える。
   翻訳不要な文字列（初期値や製品名など）は .ui 側で `<string notr="true">` にする。
4. プレースホルダは原文側に書き、`.format()` は呼び出し側で適用する:
   `i18n.tr("count: {}").format(n)`

## 使い方

```python
import i18n

label.setText(i18n.tr("Output directory"))
```

新しい文字列を追加したら抽出スクリプトを実行する。コードに在って JSON に無いキーは
空訳 `""` で追加され、JSON に在ってコードに無いキーは「未使用」として報告される
（自動削除はしない）:

```bash
python3 i18n/extract.py --locale ja            # i18n/ja.json を更新
python3 i18n/extract.py --locale fr            # i18n/fr.json を更新
python3 i18n/extract.py --locale ja --check    # 未更新なら非0終了（CI 用）
```

その後 JSON の空訳を埋める（エディタで直接編集。コンパイル不要）。

## 対応言語

- 英語 (en) — デフォルト（原文）
- 日本語 (ja) — `ja.json`
- フランス語 (fr) — `fr.json`
