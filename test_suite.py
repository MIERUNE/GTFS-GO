"""
Test Suite.
"""

import os
import sys
import tempfile
import unittest

from osgeo import gdal
from qgis.core import Qgis

try:
    from pip import main as pipmain
except ImportError:
    from pip._internal import main as pipmain

try:
    import coverage
except ImportError:
    pipmain(["install", "coverage"])
    import coverage

__author__ = "Alessandro Pasotti"
__revision__ = "$Format:%H$"
__date__ = "30/04/2018"
__copyright__ = "Copyright 2018, North Road"


def _run_tests(test_suite, package_name, with_coverage=False):
    """Core function to test a test suite."""
    count = test_suite.countTestCases()
    print("########")
    print("%s tests has been discovered in %s" % (count, package_name))
    print("Python GDAL : %s" % gdal.VersionInfo("VERSION_NUM"))
    print("QGIS version : {}".format(Qgis.version()))
    print("########")
    if with_coverage:
        cov = coverage.Coverage(
            source=["/processing_r"],
            omit=["*/test/*"],
        )
        cov.start()

    unittest.TextTestRunner(verbosity=3, stream=sys.stdout).run(test_suite)

    if with_coverage:
        cov.stop()
        cov.save()

        with tempfile.NamedTemporaryFile(delete=False) as report:
            cov.report(file=report)
            # Produce HTML reports in the `htmlcov` folder and open index.html
            # cov.html_report()
            report.close()

            with open(report.name, "r", encoding="utf8") as fin:
                print(fin.read())


def test_package(package="felt"):
    """Test package.
    This function is called by travis without arguments.

    :param package: The package to test.
    :type package: str
    """
    test_loader = unittest.defaultTestLoader
    try:
        test_suite = test_loader.discover(package)
    except ImportError:
        test_suite = unittest.TestSuite()
    _run_tests(test_suite, package)


def test_environment():
    """Test package with an environment variable."""
    package = os.environ.get("TESTING_PACKAGE", "felt")
    test_loader = unittest.defaultTestLoader
    test_suite = test_loader.discover(package)
    _run_tests(test_suite, package)


if __name__ == "__main__":
    test_package()
