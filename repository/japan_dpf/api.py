import json

from PyQt5.QtCore import QEventLoop, QTextStream, QUrl
from PyQt5.QtNetwork import QNetworkReply, QNetworkRequest
from qgis.core import QgsNetworkAccessManager

DPF_API_URL = "https://api.gtfs-data.jp/v2"


def fetch(url: str) -> dict:
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
    event_loop.exec_()
    if reply.error() == QNetworkReply.NoError:
        text_stream = QTextStream(reply)
        text_stream.setCodec("UTF-8")
        text = text_stream.readAll()
        return json.loads(text)
    else:
        raise Exception(reply.error())


def get_feeds(target_date: str, extent=None, pref=None):
    url = DPF_API_URL + "/files?"
    url += f"target_date={target_date}"
    url += "" if extent is None else "&extent=" + extent
    url += "" if pref is None else f"&pref={pref}"

    res = fetch(url)
    feeds = res.get("body", [])
    return feeds
