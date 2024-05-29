from pytest_mock import MockerFixture
from qgis.core import (
    QgsCategorizedSymbolRenderer,
    QgsSingleSymbolRenderer,
    QgsVectorLayer,
)

from gtfs_go_renderer import Renderer


def test_renderer_point():
    target_layer = QgsVectorLayer(r"""{
      "type": "Feature",
      "geometry": {
        "type": "Point",
        "coordinates": [0.0, 0.0]
      },
      "properties": {
        "testname": "Null Island"
      }
    }""")
    renderer = Renderer(target_layer, "testname")
    symbol_renderer = renderer.make_renderer()
    assert isinstance(symbol_renderer, QgsSingleSymbolRenderer)


def test_renderer_polygon(mocker: MockerFixture):
    # in QGIS-API there are some classes which crash on test environment
    # -> mock methods using them
    mocker.patch("gtfs_go_renderer.Renderer._make_categories_by", return_value=[])
    mocker.patch("gtfs_go_renderer.Renderer._make_symbol", return_value=None)

    polygon_layer = QgsVectorLayer(r"""{
      "type": "Feature",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[
          0.0, 0.0,
          0.0, 1.0,
          1.0, 1.0,
          1.0, 0.0,
          0.0, 0.0
        ]]]
      },
      "properties": {
        "testname": "Null Square"
      }
    }""")

    p_renderer = Renderer(polygon_layer, "testname")
    p_symbol_renderer = p_renderer.make_renderer()
    # when input is polygon, QgsCategorizedSymbolRenderer is used
    assert isinstance(p_symbol_renderer, QgsCategorizedSymbolRenderer)
