import json

from qgis.core import QgsNetworkAccessManager
from qgis.PyQt.QtCore import QT_VERSION_STR, QEventLoop, QTextStream, QUrl
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest

QT_VERSION_INT = int(QT_VERSION_STR.split(".")[0])

DPF_API_URL = "https://api.gtfs-data.jp/v2"

if QT_VERSION_INT <= 5:
    no_error = QNetworkReply.NoError
else:
    no_error = QNetworkReply.NetworkError.NoError


def __fetch(url: str) -> dict:
    """
    Fetch data via http in QGIS-manner
    reponse must be  JSON-text

    Args:
        url (str): [description]

    Raises:
        Exception: [description]

    Returns:
        dict: decode JSON-text as python-dictionary
    """
    event_loop = QEventLoop()
    nam = QgsNetworkAccessManager.instance()
    req = QNetworkRequest(QUrl(url))
    reply = nam.get(req)
    reply.finished.connect(event_loop.quit)
    if QT_VERSION_INT <= 5:
        event_loop.exec_()
    else:
        event_loop.exec(QEventLoop.ProcessEventsFlag.AllEvents)
    if reply.error() == no_error:
        text_stream = QTextStream(reply)
        if QT_VERSION_INT <= 5:
            text_stream.setCodec("UTF-8")
        else:
            from qgis.PyQt.QtCore import QStringConverter

            text_stream.setEncoding(QStringConverter.Encoding.Utf8)
        text = text_stream.readAll()
        return json.loads(text)
    else:
        raise Exception(reply.error())


def get_feeds(target_date: str, extent=None, pref=None) -> list:
    url = DPF_API_URL + "/files?"
    url += f"target_date={target_date}"
    url += "" if extent is None else "&extent=" + extent
    url += "" if pref is None else f"&pref={pref}"

    res = __fetch(url)
    feeds = res.get("body", [])
    return feeds
