import os

DATAS_DIR = os.path.join(os.path.dirname(__file__), 'datas')
BUSSTOP_PNG_PATH = os.path.join(
    os.path.dirname(__file__), "imgs", "busstop.png")

STOPS_MINIMUM_VISIBLE_SCALE = 100000

ROUTES_LINE_WIDTH = 1.2
ROUTES_OUTLINE_WIDTH = 2.0
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
