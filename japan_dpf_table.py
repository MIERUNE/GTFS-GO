from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from qgis.core import *
from qgis.gui import *

HEADERS = (
    "agency_prefecture",
    "agency_name",
    "gtfs_name",
    "from_date",
    "to_date",
    "gtfs_url",
    "stops_url",
    "route_url",
    "tracking_url",
    "gtfs_id",
    "agency_id",
)

HEADERS_TO_HIDE = (
    "gtfs_url",
    "stops_url",
    "route_url",
    "tracking_url",
    "gtfs_id",
    "agency_id",
)


class Model(QAbstractTableModel):
    def __init__(self, datalist: list, parent=None):
        QAbstractTableModel.__init__(self, parent)
        self.datalist = datalist
        self.headers = HEADERS

    # テーブルの行数
    def rowCount(self, parent):
        return len(self.datalist)

    # テーブルの列数
    def columnCount(self, parent):
        return len(self.headers)

    def flags(self, index):
        # 編集可能(Editable)とすることも可能
        # return Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    # 表示すべきデータ定義
    # Roleごとに書き分けないと表示が崩れる
    def data(self, index, role):
        """
        if role == Qt.EditRole:
            row = index.row()
            column = index.column()
            return self.list[row][column]
        """

        if role == Qt.DisplayRole:
            row = index.row()
            column = index.column()
            key = self.headers[column]
            return self.datalist[row].get(key, "")

    # 編集可能にする場合必要な関数
    # 編集されたセルの値を取得し、シグナルをemitする
    """
    def setData(self, index, value, role=Qt.EditRole):
        row = index.row()
        column = index.column()
        
        if role == Qt.EditRole:
            self.list[row][column] = value
            self.dataChanged.emit(index, index)
            return True
        return False
    """

    # テーブルのヘッダー設定
    def headerData(self, section, orientation, role):
        if role == Qt.DisplayRole:
            # テーブル上部のヘッダー設定
            if orientation == Qt.Horizontal:
                if section < len(self.headers):
                    return self.headers[section]
                else:
                    return "not implemented"
            # テーブル左部のヘッダー設定
            else:
                return section + 1
