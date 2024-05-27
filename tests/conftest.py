from typing import Iterable

import pytest
from pytest_mock import MockerFixture
from qgis.gui import QgisInterface
from qgis.PyQt.QtCore import QSettings

from ..__init__ import classFactory


@pytest.fixture()
def plugin(qgis_iface: QgisInterface, mocker: MockerFixture) -> Iterable[None]:
    # mock
    mocker.patch.object(QSettings, "value", return_value="en")
    qgis_iface.addPluginToWebMenu = lambda x, y: None  # pytest-qgisで未実装

    _plugin = classFactory(qgis_iface)
    _plugin.initGui()

    yield _plugin

    # _plugin.unload() QgisInterface.removePluginMenu()がpytest-qgisで未実装
