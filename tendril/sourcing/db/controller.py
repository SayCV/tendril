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
This file is part of tendril
See the COPYING, README, and INSTALL files for more information
"""

from sqlalchemy.sql import exists
from sqlalchemy.orm.exc import MultipleResultsFound
from sqlalchemy.orm.exc import NoResultFound

from tendril.utils.db import with_db
from tendril.utils.db import get_session

from model import SourcingVendor
from model import VendorPartMap
from model import VendorPartNumber

from tendril.utils.config import VENDORS_DATA

from tendril.utils import log
logger = log.get_logger(__name__, log.DEFAULT)


# Argument Processors
@with_db
def _get_vendor(vendor=None, session=None):
    if not vendor:
        raise AttributeError("vendor needs to be defined")
    if isinstance(vendor, str):
        vendor = get_vendor(name=vendor, session=session)
        if not vendor:
            raise ValueError("Could not find vendor {0}".format(vendor))
    assert isinstance(vendor, SourcingVendor)
    return vendor


@with_db
def _get_ident(ident=None, session=None):
    if not ident:
        raise AttributeError('ident needs to be defined')
    if not isinstance(ident, str):
        raise TypeError('ident needs to be a string')
    return ident.strip()


@with_db
def _get_vpno_obj(vendor=None, ident=None, vpno=None,
                  type=None, session=None):

    if isinstance(vpno, VendorPartNumber):
        return vpno

    vendor = _get_vendor(vendor=vendor, session=session)
    ident = _get_ident(ident=ident, session=session)

    map_obj = get_map(vendor=vendor, ident=ident, session=session)

    q = session.query(VendorPartNumber)
    q = q.filter(VendorPartNumber.vpmap_id == map_obj.id)
    q = q.filter(VendorPartMap.type == type)
    q = q.filter(VendorPartMap.vpno == vpno)
    return q.one()


@with_db
def _create_map(vendor=None, ident=None, strategy=None, session=None):
    vendor = _get_vendor(vendor=vendor, session=session)
    ident = _get_ident(ident=ident, session=session)

    mobj = VendorPartMap(ident=ident,
                         vendor_id=vendor.id,
                         strategy=strategy)
    session.add(mobj)
    session.flush()

    return mobj


# Core Sourcing Getters
@with_db
def get_vendor(name=None, create=False, session=None):
    if not name:
        raise ValueError("Name can't be none.")
    try:
        return session.query(
            SourcingVendor).filter_by(name=name).one()
    except MultipleResultsFound:
        logger.warning("Found Multiple Objects for Vendor : " +
                       name)
    except NoResultFound:
        if create is True:
            obj = SourcingVendor(name=name)
            session.add(obj)
            return obj
        else:
            return None


# Vendor Map Getters
@with_db
def get_map(vendor=None, ident=None, session=None):
    vendor = _get_vendor(vendor=vendor, session=session)
    ident = _get_ident(ident=ident, session=session)

    q = session.query(VendorPartMap)
    q = q.filter(VendorPartMap.ident == ident)
    q = q.join(SourcingVendor)
    try:
        q = q.filter(VendorPartMap.vendor == vendor).one()
        return q
    except NoResultFound:
        return _create_map(vendor=vendor, ident=ident, session=session)
    except MultipleResultsFound:
        logger.error("Found multiple maps for {0} on {1}"
                     "".format(ident, vendor))
        raise


@with_db
def get_map_vpnos(vendor=None, ident=None, type=None, session=None):
    vendor = _get_vendor(vendor=vendor, session=session)
    ident = _get_ident(ident=ident, session=session)

    map_obj = get_map(vendor=vendor, ident=ident, session=session)

    q = session.query(VendorPartNumber)
    q = q.filter(VendorPartNumber.vpmap_id == map_obj.id)
    q = q.filter(VendorPartNumber.type == type)
    return q.all()


# Vendor Map Setters
@with_db
def set_strategy(vendor=None, ident=None, strategy=None, session=None):
    vendor = _get_vendor(vendor=vendor, session=session)
    ident = _get_ident(ident=ident, session=session)

    map_obj = get_map(vendor=vendor, ident=ident, session=session)
    map_obj.strategy = strategy
    return map_obj


@with_db
def add_map_vpno(vendor=None, ident=None, vpno=None, type=None, session=None):
    vendor = _get_vendor(vendor=vendor, session=session)
    ident = _get_ident(ident=ident, session=session)

    map_obj = get_map(vendor=vendor, ident=ident, session=session)

    vpno_obj = VendorPartNumber(vpno=vpno, type=type, vpmap_id=map_obj.id)
    session.add(vpno_obj)
    session.flush()

    return vpno_obj


@with_db
def remove_map_vpno(vendor=None, ident=None, vpno=None, type=None, session=None):
    vendor = _get_vendor(vendor=vendor, session=session)
    ident = _get_ident(ident=ident, session=session)
    vpno_obj = _get_vpno_obj(vendor=vendor, ident=ident, vpno=vpno,
                             type=type, session=session)

    session.delete(vpno_obj)
    session.flush()


@with_db
def clear_map(vendor=None, ident=None, type=None, session=None):
    vendor = _get_vendor(vendor=vendor, session=session)
    ident = _get_ident(ident=ident, session=session)

    vpnos = get_map_vpnos(vendor=vendor, ident=ident,
                          type=type, session=session)

    for vpno in vpnos:
        remove_map_vpno(vendor=vendor, ident=ident, vpno=vpno,
                        type=type, session=session)


@with_db
def set_map_vpnos(vendor=None, ident=None, vpnos=None,
                  type=None, session=None):
    vendor = _get_vendor(vendor=vendor, session=session)
    ident = _get_ident(ident=ident, session=session)

    clear_map(vendor=vendor, ident=ident, type=type, session=session)

    for vpno in vpnos:
        add_map_vpno(vendor=vendor, ident=ident, vpno=vpno,
                     type=type, session=session)


@with_db
def set_amap_vpnos(vendor=None, ident=None, vpnos=None, session=None):
    set_map_vpnos(vendor=vendor, ident=ident, vpnos=vpnos,
                  type='auto', session=session)


@with_db
def clear_amap(vendor=None, ident=None, session=None):
    clear_map(vendor=vendor, ident=ident, type='auto', session=session)


@with_db
def add_amap_vpno(vendor=None, ident=None, vpno=None, session=None):
    add_map_vpno(vendor=vendor, ident=ident,
                 vpno=vpno, type='auto', session=session)


@with_db
def remove_amap_vpno(vendor=None, ident=None, vpno=None, session=None):
    remove_map_vpno(vendor=vendor, ident=ident,
                    vpno=vpno, type='auto', session=session)


@with_db
def set_umap_vpnos(vendor=None, ident=None, vpnos=None, session=None):
    set_map_vpnos(vendor=vendor, ident=ident, vpnos=vpnos,
                  type='manual', session=session)


@with_db
def clear_umap(vendor=None, ident=None, session=None):
    clear_map(vendor=vendor, ident=ident, type='manual', session=session)


@with_db
def add_umap_vpno(vendor=None, ident=None, vpno=None, session=None):
    remove_map_vpno(vendor=vendor, ident=ident,
                    vpno=vpno, type='manual', session=session)


@with_db
def remove_umap_vpno(vendor=None, ident=None, vpno=None, session=None):
    remove_map_vpno(vendor=vendor, ident=ident,
                    vpno=vpno, type='manual', session=session)


# Maintenance Functions
def populate_vendors():
    logger.info("Populating Sourcing Vendors")
    for vendor in VENDORS_DATA:
        with get_session() as session:
            if not session.query(
                    exists().where(
                        SourcingVendor.name == vendor['name'])
            ).scalar():
                logger.info("Creating vendor entry for : " + vendor['name'])
                obj = SourcingVendor(name=vendor['name'],
                                     dname=vendor['dname'],
                                     type=vendor['type'],
                                     mapfile_base=vendor['name'],
                                     pclass=vendor['pclass'],
                                     status='active')
                session.add(obj)
            else:
                logger.debug("Found preexisting vendor entry for : " +
                             vendor['name'])
