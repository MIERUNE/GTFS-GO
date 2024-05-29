import configparser
import os
import unittest


class TestInit(unittest.TestCase):
    """Test that the plugin init is usable for QGIS.
    reference: https://github.com/felt/qgis-plugin/blob/main/felt/test/test_init.py
    """

    def test_read_init(self):
        """Test that the plugin __init__ will validate on plugins.qgis.org."""

        # You should update this list according to the latest in
        # https://github.com/qgis/qgis-django/blob/master/qgis-app/
        #        plugins/validator.py

        required_metadata = [
            "name",
            "description",
            "version",
            "qgisMinimumVersion",
            "email",
            "author",
        ]

        file_path = os.path.abspath(
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "metadata.txt")
        )
        metadata = []
        parser = configparser.ConfigParser()
        parser.optionxform = str
        parser.read(file_path)
        message = 'Cannot find a section named "general" in %s' % file_path
        assert parser.has_section("general"), message
        metadata.extend(parser.items("general"))
        for expectation in required_metadata:
            message = 'Cannot find metadata "%s" in metadata source (%s).' % (
                expectation,
                file_path,
            )

            self.assertIn(expectation, dict(metadata), message)


if __name__ == "__main__":
    unittest.main()
