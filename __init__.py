def classFactory(iface):  # pylint: disable=invalid-name
    """Load GTFSGo class from file GTFSGo.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .gtfs_go import GTFSGo

    return GTFSGo(iface)
