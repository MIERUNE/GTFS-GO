"""Tests for the i18n package (load / tr / translate_widget)."""

import json
import os

import pytest
from qgis.PyQt.QtWidgets import QLabel, QWidget

import i18n

I18N_DIR = os.path.dirname(i18n.__file__)


@pytest.fixture(autouse=True)
def _restore_translations():
    saved = dict(i18n._translations)
    yield
    i18n._translations = saved


def test_tr_returns_translation_when_present():
    i18n._translations = {"Search": "検索"}
    assert i18n.tr("Search") == "検索"


def test_tr_falls_back_to_source_when_missing():
    i18n._translations = {"Search": "検索"}
    assert i18n.tr("Unknown String") == "Unknown String"


def test_tr_falls_back_to_source_when_translation_empty():
    i18n._translations = {"Search": ""}
    assert i18n.tr("Search") == "Search"


@pytest.mark.parametrize("locale", ["ja", "ja_JP", "fr"])
def test_load_reads_locale_json(locale):
    i18n.load(locale)
    assert i18n.tr("Error") != "Error"


def test_load_missing_locale_falls_back_to_source():
    i18n.load("__nonexistent_locale__")
    assert i18n._translations == {}
    assert i18n.tr("Error") == "Error"


@pytest.mark.parametrize("locale", ["ja", "fr"])
def test_all_keys_translated(locale):
    with open(os.path.join(I18N_DIR, f"{locale}.json"), encoding="utf-8") as f:
        translations = json.load(f)
    assert [k for k, v in translations.items() if not v] == []


def test_translate_widget(qgis_app):
    i18n._translations = {"Search": "検索"}
    root = QWidget()
    root.setWindowTitle("Search")
    translated = QLabel("Search", root)
    untouched = QLabel("Other", root)
    i18n.translate_widget(root)
    assert root.windowTitle() == "検索"
    assert translated.text() == "検索"
    assert untouched.text() == "Other"
