#!/usr/bin/env python
# encoding: utf-8

# Copyright (C) 2016 Chintalagiri Shashank
#
# This file is part of tendril.
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
Docstring for helpers
"""


def add_project_selector_options(parser):
    parser.add_argument(
        'projfolders', metavar='PATH', type=str, nargs='*',
        help='gEDA Project Folder(s), ignored for --all.'
    )
    parser.add_argument(
        '--recurse', '-r', action='store_true', default=False,
        help='Recursively search for projects under each provided folder.'
    )
    parser.add_argument(
        '--all', '-a', action='store_true', default=False,
        help='All recognized projects.'
    )


def add_vendor_selection_options(parser):
    parser.add_argument(
        'vendor_name', metavar='VENDOR_NAME', type=str, nargs='?',
        help='Name of the vendor. Ignored for --all.'
    )
    parser.add_argument(
        '--all', '-a', action='store_true', default=False,
        help='Run for all vendors.'
    )