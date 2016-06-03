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
Mouser Vendor Module (:mod:`tendril.sourcing.mouser`)
=====================================================

"""

import traceback
import re
from suds.sax.element import Element

from tendril.conventions.electronics import check_for_std_val
from tendril.conventions.electronics import parse_ident
from tendril.utils import www
from tendril.utils import log

from .vendors import VendorBase
from .vendors import VendorElnPartBase
from .vendors import VendorPrice
from .vendors import SearchPart
from .vendors import SearchResult

logger = log.get_logger(__name__, log.DEFAULT)


class MouserElnPart(VendorElnPartBase):
    def __init__(self, vpno, **kwargs):
        super(MouserElnPart, self).__init__(vpno, **kwargs)

    def _get_data(self):
        c = self._vendor.api_client
        r = c.service.SearchByPartNumber(mouserPartNumber=self.vpno)
        if not r.NumberOfResult:
            raise ValueError(
                'Unable to retrieve part information for part number.'
            )

        part_data = None
        for part in r.Parts[0]:
            if part.MouserPartNumber == self.vpno:
                part_data = part

        if not part_data:
            raise ValueError(
                'Unable to retrieve part information for part number.'
            )

        self._load_from_response(part_data)

    def _load_from_response(self, part_data):
        self.manufacturer = part_data.Manufacturer
        self.mpartno = part_data.ManufacturerPartNumber
        self.datasheet = part_data.DataSheetUrl
        self.package = None
        self.vqtyavail = int(part_data.Availability.split()[0])
        self.vpartdesc = part_data.Description
        self.vparturl = part_data.ProductDetailUrl

        for price in part_data.PriceBreaks[0]:
            self.add_price(VendorPrice(
                price.Quantity,
                float(re.findall(r'\d+\.*\d*', price.Price)[0]),
                self._vendor.currency)
            )

    def load_from_response(self, response):
        self._load_from_response(part_data=response)


class VendorMouser(VendorBase):
    _partclass = MouserElnPart

    #: Supported Device Classes
    #:
    #: .. hint::
    #:      This handles instance-specific tweaks, and should be
    #:      modified to match your instance's nomenclature guidelines.
    #:
    _devices = [
        'IC SMD', 'IC THRU', 'IC PLCC',
        'FERRITE BEAD SMD', 'TRANSISTOR THRU', 'TRANSISTOR SMD',
        'CONN DF13', 'CONN DF13 HOUS', 'CONN DF13 WIRE', 'CONN DF13 CRIMP',
        'CONN MODULAR', 'DIODE SMD', 'DIODE THRU', 'BRIDGE RECTIFIER',
        'VARISTOR', 'RES SMD', 'RES THRU',  # 'RES ARRAY SMD',
        'CAP CER SMD', 'CAP AL SMD', 'CAP MICA SMD',  # 'CAP TANT SMD',
        'TRANSFORMER SMD', 'INDUCTOR SMD', 'RELAY',
        'CRYSTAL AT', 'CRYSTAL OSC', 'CRYSTAL VCXO', 'ZENER SMD'
    ]

    _type = 'Mouser SOAP API'

    _url_base = 'http://www.mouser.com/'
    _api_endpoint = 'http://www.mouser.in/service/searchapi.asmx?WSDL'

    def __init__(self, apikey=None, **kwargs):
        self._api_key = apikey
        self._client = self._build_api_client()
        super(VendorMouser, self).__init__(**kwargs)
        self.add_order_additional_cost_component("Customs", 12.85)

    def _build_mouser_header(self):
        header_partnerid = Element('PartnerID').setText(self._api_key)
        header_accountinfo = Element('AccountInfo')
        header_accountinfo.insert(header_partnerid)
        header = Element('MouserHeader')
        header.insert(header_accountinfo)
        header.set('xmlns', 'http://api.mouser.com/service')
        return header

    def _build_api_client(self):
        c = www.get_soap_client(self._api_endpoint,
                                cache_requests=True,
                                max_age=600000,
                                minimum_spacing=5)
        header = self._build_mouser_header()
        c.set_options(soapheaders=header)
        c.set_options(prefixes=False)
        c.set_options(service='SearchAPI', port='SearchAPISoap12')
        return c

    @property
    def api_client(self):
        return self._client

    def search_vpnos(self, ident):
        parts, strategy = self._search_vpnos(ident)
        if parts is None:
            return None, strategy

        try:
            for part in parts:
                partobj = self._partclass(part.pno, ident=ident,
                                          vendor=self, max_age=None,
                                          shell_only=True)
                partobj.load_from_response(part.raw)
                partobj.commit()
        except:
            pass

        pnos = [x.pno for x in parts]
        return pnos, strategy

    def _search_vpnos(self, ident):
        device, value, footprint = parse_ident(ident)
        if device not in self._devices:
            return None, 'NODEVICE'
        try:
            if device.startswith('RES') or device.startswith('POT') or \
                    device.startswith('CAP') or device.startswith('CRYSTAL'):
                if check_for_std_val(ident) is False:
                    return self._get_search_vpnos(device, value, footprint)
                try:
                    return self._get_pas_vpnos(device, value, footprint)
                except NotImplementedError:
                    return None, 'NOT_IMPL'
            if device in self._devices:
                return self._get_search_vpnos(device, value, footprint)
            else:
                return None, 'FILTER_NODEVICE'
        except Exception:
            logger.error(traceback.format_exc())
            logger.error('Fatal Error searching for : ' + ident)
            return None, None

    @staticmethod
    def _process_response_part(rpart):
        ns = True
        try:
            if int(rpart.Availability.split()[0]) > 0:
                ns = False
        except:
            pass
        return SearchPart(pno=rpart.MouserPartNumber,
                          mfgpno=rpart.ManufacturerPartNumber,
                          package=rpart.Category, ns=ns, unitp=None,
                          minqty=rpart.Min, raw=rpart
                          )

    @staticmethod
    def _get_device_catstrings(device):
        if device.startswith('DIODE'):
            catstrings = ['Rectifiers',
                          'Schottky Diodes & Rectifiers',
                          'Diodes - General Purpose, Power, Switching',
                          'TVS Diodes',
                          ]
        elif device.startswith('IC'):
            catstrings = [
                'Analog to Digital Converters - ADC',
                'Special Purpose Amplifiers',
                'Voltage References',
                'Analog Switch ICs',
                'Gate Drivers',
                'High Speed Operational Amplifiers',
                'Digital to Analog Converters - DAC',
                'Flip Flops',
                'Logic Gates',
                'Translation - Voltage Levels',
                'Encoders, Decoders, Multiplexers & Demultiplexers',
                'Analog Comparators',
                'Board Mount Hall Effect / Magnetic Sensors',
                'Board Mount Temperature Sensors',
                'Digital Potentiometer ICs',
                'Counter ICs',
                'Delay Lines / Timing Elements',
                'Analog & Digital Crosspoint ICs',
                'Logic Comparators',
                'Digital Isolators',
                # 'Adafruit Accessories',
                'LDO Voltage Regulators',
                'Accelerometers',
                'EEPROM',
                '16-bit Microcontrollers - MCU',
                'Linear Voltage Regulators',
                'Voltage Regulators - Switching Regulators',
                # 'LED Mounting Hardware',
                # 'Power Management IC Development Tools',
                'Switching Controllers',
                'Board Mount Pressure Sensors',
                'Precision Amplifiers',
                'Data Acquisition ADCs/DACs - Specialized',
                # 'Development Boards & Kits - MSP430',
                'Instrumentation Amplifiers',
                'UART Interface IC',
                'Multiplexer Switch ICs',
                'Operational Amplifiers - Op Amps',
                # 'Aluminum Electrolytic Capacitors - Leaded',
                # 'Basic / Snap Action Switches',
                'USB Interface IC',
                'Switch ICs - Various',
                'Inverters',
                'Bus Transceivers',
                'Sensor Interface',
                # 'Data Conversion IC Development Tools',
                # 'Headers & Wire Housings',
                # 'Circuit Board Hardware - PCB',
                # 'Circular MIL Spec Backshells',
                # 'Automotive Connectors',
                # 'RF Adapters - In Series',
                # 'Ethernet Cables / Networking Cables',
                # 'Coaxial Cables',
                # 'Heat Shrink Tubing and Sleeves',
                'Buffers & Line Drivers',
                # 'Sockets & Adapters',
                'RS-232 Interface IC',
                # 'Interface Development Tools',
                # 'MOSFET',
                # 'Non-Isolated DC/DC Converters',
                # 'Standard LEDs - SMD',
                # 'Resettable Fuses - PPTC',
                # 'Pluggable Terminal Blocks',
                # 'I/O Connectors',
                # 'High Speed / Modular Connectors',
                # 'FFC & FPC Connectors',
                # 'LED Circuit Board Indicators',
                # 'Printers',
                'Latches',
                # 'Daughter Cards & OEM Boards',
                'Standard Clock Oscillators',
                'Power Switch ICs - Power Distribution',
                'Differential Amplifiers',
                'Power Factor Correction - PFC',
                'Clock Synthesizer / Jitter Cleaner',
                'Transistor Output Optocouplers',
                'Interface - Specialized',
                'RS-485 Interface IC',
                'SRAM',
                # 'RF Connectors / Coaxial Connectors',
                # 'CPU - Central Processing Units',
                # 'Anti-Static Control Products',
                'FIFO',
                'I/O Controller Interface IC',
                'Interface - I/O Expanders',
                # 'Amplifier IC Development Tools',
                'Multipliers / Dividers',
                'Active Filters',
                'Motor / Motion / Ignition Controllers & Drivers',
                'Timers & Support Products',
                'Phase Locked Loops - PLL',
                'CAN Interface IC',
                'Battery Management',
                'Clock Generators & Support Products',
                'LVDS Interface IC',
                'ARM Microcontrollers - MCU',
                'Ethernet ICs',
                # 'Ethernet Modules',
                # 'Film Capacitors',
                # 'Wirewound Resistors - Through Hole',
                'Counter Shift Registers',
                # 'DIMM Connectors',
                # 'Fixed Inductors',
                # 'Coupled Inductors',
                # 'High Power LEDs - Single Color',
                'Modulator / Demodulator',
                # 'RF Development Tools',
                # 'D-Sub Standard Connectors',
                # 'Digital Signal Processors & Controllers - DSP, DSC',
                # 'RF Amplifier',
                # 'Heavy Duty Power Connectors',
                # 'Multi-Conductor Cables',
                # 'Varactor Diodes',
                # 'Hook-up Wire',
                # 'Blowers',
                # 'Terminals',
                # 'Rack & Panel Connectors',
                'Isolated DC/DC Converters',
                # 'JFET',
                # 'Modular Connectors / Ethernet Connectors',
                # 'Fan Accessories',
                'Programmable Oscillators',
                # 'D-Sub High Density Connectors',
                # 'Non-Heat Shrink Tubing and Sleeves',
                # 'LED Lighting Reflectors',
                # 'Circular DIN Connectors',
                # 'Thick Film Resistors - SMD',
                # 'Thin Film Resistors - SMD',
                # 'Specialized Cables',
                # 'Solder & Shield Tubing',
                # 'Switch Hardware',
                'High Speed Optocouplers',
                'Triac & SCR Output Optocouplers',
                'LED Lighting Drivers',
                # 'USB Connectors',
                # 'Phone Connectors',
                # 'Optically Isolated Amplifiers',
                # 'D-Sub Backshells',
                # 'DIN Rail Terminal Blocks',
                # 'High Power LEDs - White',
                # 'Fixed Terminal Blocks',
                # 'Adhesive Tapes',
            ]
        elif device.startswith('ZENER'):
            catstrings = ['Zener Diodes',]
        elif device.startswith('TRANSISTOR'):
            catstrings = ['Bipolar Transistors - BJT',
                          'Bipolar Transistors - Pre-Biased',
                          'Darlington Transistors',
                          'MOSFET',
                          'JFET']
        else:
            return False, None
        return True, catstrings

    # @staticmethod
    # def _get_majority_category(parts):
    #     cats = {}
    #     for part in parts:
    #         if part.package not in cats.keys():
    #             cats[part.package] = 0
    #         cats[part.package] += 1
    #     scats = [(x, cats[x]) for x in cats.keys()]
    #     scats.sort(key=lambda y: cats[y], reverse=True)
    #     return scats[0][1]
    #
    # def _filter_results_by_majority_category(self, parts):
    #     mcategory = self._get_majority_category(parts)
    #     if mcategory is not None:
    #         parts = [x for x in parts if x.package == mcategory]
    #         return SearchResult(True, parts, 'MAJORITYCAT')
    #     return SearchResult(True, parts, 'UNFILTERED')

    def _filter_results_by_category(self, parts, device):
        r, catstrings = self._get_device_catstrings(device)
        if not r:
            # return self._filter_results_by_majority_category(parts)
            return SearchResult(True, parts, 'UNFILTERED')
        parts = [x for x in parts if x.package in catstrings]
        return SearchResult(True, parts, 'CATFILTER')

    def _get_search_vpnos(self, device, value, footprint):
        # TODO Allow non-stocked parts and filter them later?
        r = self.api_client.service.SearchByKeyword(
            keyword=value, records=50, startingRecord=0, searchOptions=4
        )

        nresults = r.NumberOfResult
        if not nresults:
            return None, 'NORESULTS'
        rparts = r.Parts[0]
        parts = [self._process_response_part(x) for x in rparts]
        parts = self._remove_duplicates(parts)
        sr = self._filter_results_by_category(parts, device)
        # pnos = [x.pno for x in sr.parts]
        return sr.parts, sr.strategy

    def _get_pas_vpnos(self, device, value, footprint):
        raise NotImplementedError


def __get_api_key():
    from tendril.utils.config import VENDORS_DATA
    vopts = None
    for v in VENDORS_DATA:
        if v['name'] == 'mouser':
            vopts = v
            break
    if vopts is not None:
        return vopts['apikey']
    return None


dvobj = VendorMouser(name='mouser', dname='Mouser Electronics, Inc',
                     pclass='electronics', mappath=None,
                     currency_code='USD', currency_symbol='US$',
                     apikey=__get_api_key())


def __analyze_categories(devices):
    from tendril.gedaif.gsymlib import gsymlib_idents
    catstrings = {}
    for ident in gsymlib_idents:
        try:
            d, v, f = parse_ident(ident)
        except IndexError:
            print "Malformed Ident {0}".format(ident)
            continue
        if not d:
            print "Device Not Extracted for {0}".format(ident)
            continue
        if d not in devices:
            continue
        if d not in dvobj._devices:
            continue
        if not v:
            print "Value Not Extracted for {0}".format(ident)
            continue
        # print "Searching for {0}".format(v)
        r = dvobj.api_client.service.SearchByKeyword(
            keyword=v, records=50, startingRecord=0, searchOptions=4
        )
        if not r.NumberOfResult:
            print " No results for {0}".format(v)
            continue
        for part in r.Parts[0]:
            if part.Category not in catstrings:
                print "Found new category : {0}".format(part.Category)
                catstrings[part.Category] = []
            catstrings[part.Category].append(v)
    return catstrings
