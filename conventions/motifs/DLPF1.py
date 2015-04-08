"""
This file is part of koala
See the COPYING, README, and INSTALL files for more information

This file needs to be refactored quite a bit
"""

from math import pi

from conventions.motifs.motifbase import MotifBase
from conventions import electronics
from conventions import iec60063
from gedaif import gsymlib


class MotifDLPF1(MotifBase):
    def __init__(self, identifier):
        super(MotifDLPF1, self).__init__(identifier)
        self._configdict = None

    def configure(self, configdict):
        # Set Resistances
        self.get_elem_by_idx('R1').data['value'] = electronics.construct_resistor(configdict['R1'], '0.125W')
        self.get_elem_by_idx('R2').data['value'] = electronics.construct_resistor(configdict['R1'], '0.125W')
        # Set Frequency
        self._configdict = configdict
        self.Fdiff = float(configdict['Fdiff'][:-2])
        self.validate()

    def add_element(self, bomline):
        self._elements.append(bomline)

    @property
    def Fdiff(self):
        return (10**9) / (2 * pi * float(self.R1) * float(2 * self.C1 + self.C2))

    @property
    def Fcm(self):
        return (10**9) / (2 * pi * float(self.R1) * float(self.C2))

    @Fdiff.setter
    def Fdiff(self, value):
        c1_dev = self.get_elem_by_idx('C1').data['device']
        c1_fp = self.get_elem_by_idx('C1').data['footprint']
        if c1_fp[0:3] == "MY-":
            c1_fp = c1_fp[3:]

        allowed_cap_vals = iec60063.gen_vals(self._configdict['Cseries'],
                                             iec60063.cap_ostrs,
                                             self._configdict['Cmin'],
                                             self._configdict['Cmax'])

        fcm_est = value * 21
        required_cap_val = (10**9) / (2 * pi * float(self.R1) * fcm_est)

        cval = None
        lastval = None
        for val in allowed_cap_vals:
            lastval = cval
            cval = electronics.parse_capacitance(val)
            if cval >= required_cap_val:
                self.get_elem_by_idx('C2').data['value'] = gsymlib.find_capacitor(lastval, c1_fp, c1_dev).value
                self.get_elem_by_idx('C3').data['value'] = gsymlib.find_capacitor(lastval, c1_fp, c1_dev).value
                break

        if cval is None:
            raise ValueError

        required_cap_val = lastval * 10
        for val in allowed_cap_vals:
            cval = electronics.parse_capacitance(val)
            if cval >= required_cap_val:
                self.get_elem_by_idx('C1').data['value'] = gsymlib.find_capacitor(cval, c1_fp, c1_dev).value
                break

    @property
    def R1(self):
        elem = self.get_elem_by_idx('R1')
        assert elem.data['device'] in ['RES SMD', 'RES THRU']
        return electronics.parse_resistance(electronics.parse_resistor(elem.data['value'])[0])

    @property
    def R2(self):
        elem = self.get_elem_by_idx('R2')
        assert elem.data['device'] in ['RES SMD', 'RES THRU']
        return electronics.parse_resistance(electronics.parse_resistor(elem.data['value'])[0])

    @property
    def C1(self):
        elem = self.get_elem_by_idx('C1')
        assert elem.data['device'] in ['CAP CER SMD', 'CAP CER THRU']
        return electronics.parse_capacitance(electronics.parse_capacitor(elem.data['value'])[0])

    @property
    def C2(self):
        elem = self.get_elem_by_idx('C2')
        assert elem.data['device'] in ['CAP CER SMD', 'CAP CER THRU']
        return electronics.parse_capacitance(electronics.parse_capacitor(elem.data['value'])[0])

    @property
    def C3(self):
        elem = self.get_elem_by_idx('C3')
        assert elem.data['device'] in ['CAP CER SMD', 'CAP CER THRU']
        return electronics.parse_capacitance(electronics.parse_capacitor(elem.data['value'])[0])

    def validate(self):
        assert self.R1 == self.R2
        assert self.C3 == self.C2
        assert self.C1 >= 10 * self.C2

    @property
    def config_stub(self):
        return 'Fdiff=0Hz;R1=0E'
