import os

FILENAME_ROUTES_GEOJSON = "routes.geojson"
FILENAME_STOPS_GEOJSON = "stops.geojson"

LAYERNAME_ROUTES = "routes"
LAYERNAME_STOPS = "stops"

STOPS_LABEL_FONT = "Arial"
STOPS_LABEL_SIZE_MM = 9
STOPS_LABEL_BUFFER_SIZE_MM = 1
STOPS_LABEL_BUFFER_COLOR = "white"
STOPS_LABEL_DIST_MM = 4.0
STOPS_LABEL_MINUMUM_VISIBLE_SCALE = 50000

STOPS_MINIMUM_VISIBLE_SCALE = 100000
STOPS_ICON_SIZE_MM = 6
STOPS_ICON_HALO_WIDTH_MM = 0.8
STOPS_SVG_PATH = os.path.join(
    os.path.dirname(__file__), "imgs", "busstop.svg")

ROUTES_LINE_WIDTH_MM = 1.2
ROUTES_OUTLINE_WIDTH_MM = 2.0
ROUTES_OUTLINE_COLOR = "white"
ROUTES_COLOR_LIST = [
    # Usable color names are defined in following webpage
    # https://www.w3.org/TR/SVG11/types.html#ColorKeywords
    "orangered",
    "blue",
    "green",
    "orange",
    "salmon",
    "greenyellow",
    "yellowgreen",
    "blueviolet",
    "lightskyblue",
    "lightpink",
    "royalblue",
    "palevioletred",
    "gold"
]
