import os
import sys

# to import modules as non-relative
sys.path.append(os.path.dirname(__file__))


def classFactory(iface):  # pylint: disable=invalid-name
    """Load GTFSGo class from file GTFSGo.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .gtfs_go import GTFSGo

    return GTFSGo(iface)
