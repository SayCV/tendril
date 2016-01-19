# Copyright (C) 2015 Chintalagiri Shashank
#
# This file is part of Tendril.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
Device Test Runner Script (``tendril-runtest``)
===============================================

This script runs tests for a device.

.. hint::

     - The test definitions are retrieved from the corresponding
       projects's ``configs.yaml`` file.
     - The serial number to device type mappings are determined
       from the serial number database.
     - The detect infrastructure is based on the device's MAC and
       the corresponding detection code.

.. seealso::
    :mod:`tendril.testing.testrunner`
    :mod:`tendril.entityhub.macs`

.. rubric:: Script Usage

.. argparse::
    :module: tendril.scripts.runtest
    :func: _get_parser
    :prog: tendril-runtest
    :nodefault:

"""

import argparse

from tendril.entityhub import macs
from tendril.entityhub import serialnos
from tendril.testing import testrunner
from tendril.utils import log
logger = log.get_logger("runtest", log.DEFAULT)


def _get_parser():
    """
    Constructs the CLI argument parser for the tendril-runtest script.
    """
    parser = argparse.ArgumentParser(
        description='Run device tests for a device',
        prog='tendril-runtest'
    )
    parser.add_argument(
        'serialno', metavar='SNO', type=str, nargs='?',
        help='Device serial number'
    )
    parser.add_argument(
        '--detect', '-d', metavar=('MACTYPE'), type=str, nargs=1,
        help='Autodetect serial number using the specified MACTYPE. '
             'No effect if serial number specified.'
    )
    parser.add_argument(
        '--stale', '-s', metavar=('DAYS'), type=str, nargs='?', default=5,
        help='Number of days to have passed for a test result to '
             'be considered stale. Default 5.'
    )
    parser.add_argument(
        '--force', '-f', action='store_true', default=False,
        help="Re-run all tests, even if fresh test passed."
    )
    return parser


def run(serialno, force, stale):
    """
    Run tests for device.

    :param serialno: The serial number of the device.
    :param force: Re-run all test suites, even if fresh passed results exist.
    :param stale: Minimum age of test result to consider it stage.

    """
    if serialno is None:
        raise AttributeError("serialno cannot be None")

    devicetype = serialnos.get_serialno_efield(sno=serialno)
    logger.info(serialno + " is device : " + devicetype)

    testrunner.run_test(serialno, force=force, stale=stale)


def main():
    """
    The tendril-runtest script entry point.
    """
    parser = _get_parser()
    args = parser.parse_args()
    if not args.serialno and not args.detect:
        parser.print_help()
        return
    if not args.serialno:
        try:
            mactype = args.detect[0]
            sno = macs.get_sno_from_device(mactype)
        except:
            logger.error("Got exception when trying to detect serialno")
            raise
    else:
        sno = args.serialno
    run(sno, args.force, args.stale)


if __name__ == '__main__':
    main()
