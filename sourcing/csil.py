"""
CSIL Sourcing Module documentation (:mod:`sourcing.csil`)
=========================================================
"""

from utils import log
logger = log.get_logger(__name__, log.INFO)

import time
import locale
import os
import yaml
from collections import OrderedDict

import splinter

import utils.fs
import vendors
import utils.currency

from utils.config import NETWORK_PROXY_IP
from utils.config import NETWORK_PROXY_PORT

from utils.config import VENDORS_DATA

import gedaif.projfile
import entityhub.projects


user = None
pw = None


def get_credentials():
    global user
    global pw
    for vendor in VENDORS_DATA:
        if vendor['name'] == 'csil':
            user = vendor['user']
            pw = vendor['pw']

get_credentials()


locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

exparams = {
    'pcbname': 'QASC-',
    'layers': 2,
    'dX': '109',
    'dY': '151',
    'qty': range(70),
    'time': 10,      # 5, 7, 10, 12, 15, 18, 21, 25, 30
    'finish': 'Au',  # HAL, Ag, Au, PBFREE, NP, I, OC
}


def get_csil_prices(params=exparams):
    delivery_codes = {
        3: '3#333',
        5: '5#334',
        7: '7#529',
        10: '10#1452',
        12: '12#7271',
        15: '15#1453',
        18: '18#7272',
        21: '21#7273'
    }

    delivery_times = sorted(delivery_codes.keys())

    layers_codes = {
        1: '2180',
        2: '2181',
        4: '2183',
        6: '2184',
    }

    proxyIP = NETWORK_PROXY_IP
    proxyPort = int(NETWORK_PROXY_PORT)

    # proxy_settings = {'network.proxy.type': 1,
    #                   'network.proxy.http': proxyIP,
    #                   'network.proxy.http_port': proxyPort,
    #                   'network.proxy.ssl': proxyIP,
    #                   'network.proxy.ssl_port': proxyPort,
    #                   'network.proxy.socks': proxyIP,
    #                   'network.proxy.socks_port':proxyPort,
    #                   'network.proxy.ftp': proxyIP,
    #                   'network.proxy.ftp_port':proxyPort
    #                   }

    # browser = splinter.Browser('firefox', profile_preferences=proxy_settings)
    browser = splinter.Browser('firefox')
    url = 'http://www.pcbpower.com:8080'
    browser.visit(url)
    values = {
        'ctl00$ContentPlaceHolder1$txtUserName': user,
        'ctl00$ContentPlaceHolder1$txtPassword': pw
    }
    browser.fill_form(values)
    button = browser.find_by_name('ctl00$ContentPlaceHolder1$btnlogin')
    button.click()
    link = browser.find_by_id('ctl00_aPlaceOrder')
    link.click()

    values = OrderedDict()
    values['ctl00$ContentPlaceHolder1$txtPCBName'] = params['pcbname']
    values['ctl00$ContentPlaceHolder1$ddlLayers'] = layers_codes[params['layers']]
    values['ctl00$ContentPlaceHolder1$txtDimX'] = params['dX']
    values['ctl00$ContentPlaceHolder1$txtDimY'] = params['dY']
    if 'qty' in params.keys():
        values['ctl00$ContentPlaceHolder1$txtQuantity'] = str(params['qty'][1])
    else:
        values['ctl00$ContentPlaceHolder1$txtQuantity'] = '1'
    values['ctl00$ContentPlaceHolder1$DDLsurfacefinish'] = params['finish']
    if 'time' in params.keys():
        values['ctl00$ContentPlaceHolder1$ddlDelTerms'] = delivery_codes[params['time']]
    else:
        values['ctl00$ContentPlaceHolder1$ddlDelTerms'] = delivery_codes[5]

    if not browser.is_element_present_by_id('shortNotiText', wait_time=100):
        raise Exception
    ready = False
    timeout = 10
    while not ready and timeout:
        el = browser.find_by_id('shortNotiText')
        if el[0].text == u"We're online":
            ready = True
        timeout -= 1
        time.sleep(1)
    time.sleep(5)
    browser.fill_form(values)

    browser.fill_form(values)

    try:
        oldt = browser.find_by_id('ctl00_ContentPlaceHolder1_lblUnitPrc').text
    except AttributeError:
        oldt = ''
    qty = str(params['qty'][1])
    oldv = qty
    time.sleep(2)
    button = browser.find_by_id('ctl00_ContentPlaceHolder1_btnCalculate')

    button.click()
    time.sleep(2)
    button = browser.find_by_id('ctl00_ContentPlaceHolder1_btnCalculate')

    button.click()

    try:
        newt = browser.find_by_id('ctl00_ContentPlaceHolder1_lblUnitPrc').text
    except AttributeError:
        newt = ''
    try:
        newtt = browser.find_by_id('ctl00_ContentPlaceHolder1_lblTotalPrice').text
    except AttributeError:
        newtt = ''
    while oldt == newt:
        try:
            newt = browser.find_by_id('ctl00_ContentPlaceHolder1_lblUnitPrc').text
        except AttributeError:
            newt = ''
        try:
            newtt = browser.find_by_id('ctl00_ContentPlaceHolder1_lblTotalPrice').text
        except AttributeError:
            newtt = ''
        time.sleep(0.5)
    rval = {}
    oldt = newt
    oldtt = newtt

    for qty in params['qty'][2:]:
        # time.sleep(2)
        lined = {}
        # for char in oldv:
        while browser.find_by_name('ctl00$ContentPlaceHolder1$txtQuantity')[0].value != '':
            browser.type('ctl00$ContentPlaceHolder1$txtQuantity', '\b')
            time.sleep(0.1)
        browser.type('ctl00$ContentPlaceHolder1$txtQuantity', str(qty))
        time.sleep(0.1)
        browser.type('ctl00$ContentPlaceHolder1$txtQuantity', '\t')
        if qty > 4:
            loi = [10]
        else:
            loi = [5, 10]
        for dt_s in loi:
            dt_idx = delivery_times.index(dt_s)
            dts = delivery_times[dt_idx:dt_idx+3]
            browser.select('ctl00$ContentPlaceHolder1$ddlDelTerms', delivery_codes[dt_s])
            time.sleep(0.1)

            print 'Waiting for ... ' + str(qty) + ' ... ' + str(dt_s)

            time.sleep(2)
            try:
                newt = browser.find_by_id('ctl00_ContentPlaceHolder1_lblUnitPrc').text
                newt1 = browser.find_by_id('ctl00_ContentPlaceHolder1_lblnextunitprc1').text
                newt2 = browser.find_by_id('ctl00_ContentPlaceHolder1_lblnextunitprc2').text
            except AttributeError:
                newt = ''
                newt1 = ''
                newt2 = ''

            timeout = 25
            while oldt == newt and oldtt == newtt and newt is not '' and timeout > 0:
                timeout -= 1
                time.sleep(0.5)
                try:
                    newt = browser.find_by_id('ctl00_ContentPlaceHolder1_lblUnitPrc').text
                    newt1 = browser.find_by_id('ctl00_ContentPlaceHolder1_lblnextunitprc1').text
                    newt2 = browser.find_by_id('ctl00_ContentPlaceHolder1_lblnextunitprc2').text
                except AttributeError:
                    newt = ''
                try:
                    newtt = browser.find_by_id('ctl00_ContentPlaceHolder1_lblTotalPrice').text
                except AttributeError:
                    newtt = ''
            lined[dts[0]] = locale.atof(newt)
            lined[dts[1]] = locale.atof(newt1)
            lined[dts[2]] = locale.atof(newt2)
            oldt = newt
            oldtt = newtt
        print lined
        rval[qty] = lined
    browser.quit()
    return rval


class VendorCSIL(vendors.VendorBase):
    def __init__(self, name, dname, pclass, mappath=None,
                 currency_code=None, currency_symbol=None,
                 username=None, password=None):
        self._username = username
        self._password = password
        self._devices = ['PCB']
        super(VendorCSIL, self).__init__(name, dname, pclass, mappath, currency_code, currency_symbol)

    def search_vpnos(self, ident):
        pass

    def get_vpart(self, vpartno, ident=None):
        return CSILPart(vpartno, ident, self)

    def get_optimal_pricing(self, ident, rqty):
        # return super(VendorCSIL, self).get_optimal_pricing(ident, rqty)
        candidate_names = self.get_vpnos(ident)
        candidates = [self.get_vpart(x) for x in candidate_names]

        if len(candidates) == 0:
            return self, None, None, None, None, None

        candidate = candidates[0]
        if len(candidate._prices) == 0:
            return self, None, None, None, None, None
        ubprice, nbprice, urationale, olduprice = candidate.get_price(rqty)
        oqty = ubprice.moq
        effprice = self.get_effective_price(ubprice)
        return self, candidate.vpno, oqty, nbprice, ubprice, effprice, urationale, olduprice

    def get_effective_price(self, price):
        effective_unitp = price.unit_price.source_value * 112.68 / 100
        return vendors.VendorPrice(price.moq, effective_unitp, self.currency)


class CSILPart(vendors.VendorPartBase):
    def __init__(self, vpartno, ident, vendor):
        if vendor is None:
            vendor = VendorCSIL('csil', 'transient', 'electronics_pcb')
            vendor.currency = utils.currency.CurrencyDefinition('INR', 'INR')
        self._vendor = vendor
        if ident is None:
            ident = self._vendor.map.get_canonical(vpartno)
        super(CSILPart, self).__init__(ident, vendor)
        if vpartno is not None:
            self.vpno = vpartno
        else:
            logger.error("Not enough information to create a CSIL Part")
        self._pcbname = vpartno
        if self._pcbname not in entityhub.projects.pcbs.keys():
            raise ValueError("Unrecognized PCB")
        self._projectfolder = entityhub.projects.pcbs[self._pcbname]
        self._load_prices()

        self._manufacturer = self._vendor.name
        self._vqtyavail = None

    def _load_prices(self):
        gpf = gedaif.projfile.GedaProjectFile(self._projectfolder)
        pricingfp = os.path.join(gpf.configsfile.projectfolder, 'pcb', 'sourcing.yaml')
        if not os.path.exists(pricingfp):
            logger.debug("PCB does not have sourcing file. Not loading prices : " + self._pcbname)
            return None
        with open(pricingfp, 'r') as f:
            data = yaml.load(f)
        for qty, prices in data['pricing'].iteritems():
            if 10 not in prices.keys():
                logger.warning("Default Delivery Time not in prices. Quantity pricing not imported : " +
                               str([qty, self._pcbname]))
            else:
                price = vendors.VendorPrice(qty, prices[10], self._vendor.currency)
                self._prices.append(price)

    def get_price(self, qty):
        possible_prices = []
        base_price, next_base_price = super(CSILPart, self).get_price(qty)
        for price in self._prices:
            if price.moq > qty and \
                    price.extended_price(price.moq).native_value < base_price.extended_price(qty).native_value:
                possible_prices.append(price)
        if len(possible_prices) == 0:
            return base_price, next_base_price, "GUIDELINE", None
        else:
            mintot = base_price.extended_price(qty).native_value
            selprice = base_price
            rationale = "GUIDELINE"
            for price in possible_prices:
                if price.extended_price(price.moq).native_value < mintot:
                    selprice = price
                    mintot = price.extended_price(price.moq).native_value
                    rationale = "TC Reduction"
            return selprice, super(CSILPart, self).get_price(selprice.moq+1)[0], rationale, base_price


def generate_pcb_pricing(projfolder, noregen=True):
    gpf = gedaif.projfile.GedaProjectFile(projfolder)

    try:
        pcbparams = gpf.configsfile.configdata['pcbdetails']['params']
    except KeyError:
        logger.warning('Geda project does not seem have pcb details. Not generating PCB pricing information : ' + projfolder)
        return None

    pricingfp = os.path.join(gpf.configsfile.projectfolder, 'pcb', 'sourcing.yaml')

    if noregen is True:
        pcb_mtime = utils.fs.get_file_mtime(os.path.join(gpf.configsfile.projectfolder, 'pcb', gpf.pcbfile + '.pcb'))
        outf_mtime = utils.fs.get_file_mtime(pricingfp)
        if outf_mtime is not None and outf_mtime > pcb_mtime:
            logger.info('Skipping up-to-date ' + pricingfp)
            return pricingfp

    pcbparams['qty'] = range(9)
    sourcingdata = get_csil_prices(pcbparams)
    dumpdata = {'params': pcbparams,
                'pricing': sourcingdata}
    with open(pricingfp, 'w') as pricingf:
        pricingf.write(yaml.dump(dumpdata))

    return pricingfp
