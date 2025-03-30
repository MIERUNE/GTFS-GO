from qgis.PyQt.QtCore import QT_VERSION_STR, QAbstractTableModel, Qt

QT_VERSION_INT = int(QT_VERSION_STR.split(".")[0])

if QT_VERSION_INT <= 5:
    display_role = Qt.DisplayRole
    orientation_horizontal = Qt.Horizontal
    item_is_enabled = Qt.ItemIsEnabled
    item_is_selectable = Qt.ItemIsSelectable
else:
    display_role = Qt.ItemDataRole.DisplayRole
    orientation_horizontal = Qt.Orientation.Horizontal
    item_is_enabled = Qt.ItemFlag.ItemIsEnabled
    item_is_selectable = Qt.ItemFlag.ItemIsSelectable

HEADERS = (
    "organization_id",
    "organization",
    "organization_web_url",
    "organization_email",
    "feed_id",
    "feed",
    "feed_pref_id",
    "pref",
    "feed_license_url",
    "feed_url",
    "feed_page_url",
    "file_uid",
    "file_rid",
    "from_date",
    "to_date",
    "license",
    "file_url",
    "file_stop_url",
    "file_route_url",
    "file_tracking_url",
    "file_last_updated_at",
)

HEADER_TO_DATAHEADER = {
    "organization_id": "organization_id",
    "organization": "organization_name",
    "organization_web_url": "organization_web_url",
    "organization_email": "organization_email",
    "feed_id": "feed_id",
    "feed": "feed_name",
    "feed_pref_id": "feed_pref_id",
    "pref": "feed_pref",
    "license": "feed_license_id",
    "feed_license_url": "feed_license_url",
    "feed_url": "feed_url",
    "feed_page_url": "feed_page_url",
    "file_uid": "file_uid",
    "file_rid": "file_rid",
    "from_date": "file_from_date",
    "to_date": "file_to_date",
    "file_url": "file_url",
    "file_stop_url": "file_stop_url",
    "file_route_url": "file_route_url",
    "file_tracking_url": "file_tracking_url",
    "file_last_updated_at": "file_last_updated_at",
}

HEADERS_TO_HIDE = (
    "organization_id",
    "organization_web_url",
    "organization_email",
    "feed_id",
    "feed_pref_id",
    "feed_license_url",
    "feed_url",
    "feed_page_url",
    "file_uid",
    "file_rid",
    "file_url",
    "file_stop_url",
    "file_route_url",
    "file_tracking_url",
    "file_last_updated_at",
)


class Model(QAbstractTableModel):
    def __init__(self, datalist: list, parent=None):
        QAbstractTableModel.__init__(self, parent)
        self.datalist = datalist
        self.headers = HEADERS

    def rowCount(self, parent):
        return len(self.datalist)

    def columnCount(self, parent):
        return len(self.headers)

    def flags(self, index):
        # return Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable
        return item_is_enabled | item_is_selectable

    def data(self, index, role):
        """
        if role == Qt.EditRole:
            row = index.row()
            column = index.column()
            return self.list[row][column]
        """

        if role == display_role:
            row = index.row()
            column = index.column()
            key = self.headers[column]
            dataheader = HEADER_TO_DATAHEADER[key]
            return self.datalist[row].get(dataheader, "")

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

    def headerData(self, section, orientation, role):
        if role == display_role:
            if orientation == orientation_horizontal:
                if section < len(self.headers):
                    return self.headers[section]
                else:
                    return "not implemented"
            else:
                return section + 1
