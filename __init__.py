def classFactory(iface):
    from .gtfs_go import GTFSGo

    return GTFSGo(iface)
