# Copyright 2016 Cisco Systems, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import mock
from oslo_config import cfg

from ironic_inspector.plugins import base
from ironic_inspector.test import base as test_base

from cisco_ironic_contrib.ironic_inspector.plugins import lldp

CONF = cfg.CONF

LLDP_TLV_TYPE_NON_ESSENTIAL = 1


class TestLldpHook(test_base.NodeTest):
    def setUp(self):
        super(TestLldpHook, self).setUp()
        self.hook = lldp.LldpHook()
        self.data = {
            'inventory': {},
            'interfaces': {
                'eth0': {'mac': '11:11:11:11:11:11', 'ip': '1.1.1.1'},
                'eth1': {'mac': '22:22:22:22:22:22', 'ip': '2.2.2.2'}
            }
        }
        self.node_cache = mock.Mock()

    def test_hook_loadable(self):
        CONF.set_override('processing_hooks', 'nexus_lldp', 'processing')
        ext = base.processing_hooks_manager()['nexus_lldp']
        self.assertIsInstance(ext.obj, lldp.LldpHook)

    def test_no_lldp_info(self):
        self.hook.before_update(self.data, self.node_cache)
        self.assertFalse(self.node_cache.called)

    def test_lldp_no_port_id(self):
        self.data['inventory'] = {'lldp_info': {
            'eth0': [
                (LLDP_TLV_TYPE_NON_ESSENTIAL, '0430f70d9ca644'),
                (lldp.LLDP_TLV_TYPE_SYSTEM_NAME, '73772d6c61622d6e336b2d32'),
                (lldp.LLDP_TLV_TYPE_MGMT_ADDR, '05010a560177020500000000')]}
        }
        self.hook.before_update(self.data, self.node_cache)
        self.assertFalse(self.node_cache.called)

    def test_lldp_no_switch_id(self):
        self.data['inventory'] = {'lldp_info': {
            'eth0': [
                (LLDP_TLV_TYPE_NON_ESSENTIAL, '0430f70d9ca644'),
                (lldp.LLDP_TLV_TYPE_PORT_ID, '0545746865726e6574312f3239'),
                (lldp.LLDP_TLV_TYPE_SYSTEM_NAME, '73772d6c61622d6e336b2d32')]}
        }
        self.hook.before_update(self.data, self.node_cache)
        self.assertFalse(self.node_cache.called)

    def _normalize_patches(self, patches):
        new_patches = sorted(patches, key=lambda p: p['path'])
        for patch in new_patches:
            if 'switch_info' in patch['path']:
                patch['value'] = json.loads(patch['value'])
        return new_patches

    def test_lldp_patch_port(self):
        self.data['inventory'] = {'lldp_info': {
            'eth0': [
                (LLDP_TLV_TYPE_NON_ESSENTIAL, '0430f70d9ca644'),
                (lldp.LLDP_TLV_TYPE_PORT_ID, '0545746865726e6574312f3239'),
                (lldp.LLDP_TLV_TYPE_PORT_DESC,
                    '636f6e6e656374656420746f206278622d6'
                    '4732d34342056494320706f72742031'),
                (lldp.LLDP_TLV_TYPE_SYSTEM_NAME, '73772d6c61622d6e336b2d32'),
                (lldp.LLDP_TLV_TYPE_SYSTEM_DESC,
                    '436973636f204e65787573204f7065726174696e672053797374656d2'
                    '0284e582d4f532920536f66747761726520362e302832294136283229'
                    '0a54414320737570706f72743a20687474703a2f2f7777772e6369736'
                    '36f2e636f6d2f7461630a436f70797269676874202863292032303032'
                    '2d323031352c20436973636f2053797374656d732c20496e632e20416'
                    'c6c207269676874732072657365727665642e'),
                (lldp.LLDP_TLV_TYPE_MGMT_ADDR, '05010a560177020500000000'),
                (lldp.LLDP_TLV_TYPE_MGMT_ADDR,
                    '070630f70d9ca644020500000000')],
            'eth1': []}
        }
        patches = [
            {'path': '/local_link_connection/switch_info',
             'value': '{"system_name": "sw-lab-n3k-2",'
                      ' "switch_ip": "10.86.1.119",'
                      ' "is_native": true,'
                      ' "system_desc": "Cisco Nexus Operating System (NX-OS)'
                      ' Software 6.0(2)A6(2)\\nTAC support: http://www.cisco'
                      '.com/tac\\nCopyright (c) 2002-2015, Cisco Systems,'
                      ' Inc. All rights reserved.",'
                      ' "port_desc": "connected to bxb-ds-44 VIC port 1"}',
             'op': 'add'},

            {'path': '/local_link_connection/port_id',
             'value': 'Ethernet1/29',
             'op': 'add'},

            {'path': '/local_link_connection/switch_id',
             'value': '11:11:11:11:11:11',
             'op': 'add'}
        ]

        self.hook.before_update(self.data, self.node_cache)
        expected = self._normalize_patches(patches)
        actual = self._normalize_patches(
            self.node_cache.patch_port.call_args[0][1])
        self.assertEqual('11:11:11:11:11:11',
                         self.node_cache.patch_port.call_args[0][0])
        self.assertEqual(expected, actual)
