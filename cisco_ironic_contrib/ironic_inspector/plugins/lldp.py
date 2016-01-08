# Copyright 2016 Cisco Systems, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import binascii
import json
import socket
import struct

from oslo_log import log

from ironic_inspector.common.i18n import _LI
from ironic_inspector.plugins import base

LOG = log.getLogger('ironic_inspector.plugins.standard')
LLDP_TLV_TYPE_PORT_ID = 2
LLDP_TLV_TYPE_PORT_DESC = 4
LLDP_TLV_TYPE_SYSTEM_NAME = 5
LLDP_TLV_TYPE_SYSTEM_DESC = 6
LLDP_TLV_TYPE_MGMT_ADDR = 8
MGMT_ADDR_SUBTYPE_IPV4 = 1
PORT_ID_SUBTYPE_IFNAME = 5


def get_port_id(switch_port_info, port_id):
    port_id = bytearray(port_id)
    if port_id[0] == 5:
        switch_port_info['port_id'] = port_id[1:].decode('utf-8')


def get_port_description(switch_port_info, port_desc):
    switch_port_info['switch_info']['port_desc'] = port_desc.decode('utf-8')


def get_system_name(switch_port_info, system_name):
    switch_port_info['switch_info']['system_name'] = (
        system_name.decode('utf-8'))


def get_system_description(switch_port_info, system_desc):
    switch_port_info['switch_info']['system_desc'] = (
        system_desc.decode('utf-8'))


def get_mgmt_addr(switch_port_info, mgmt_addr):
    (ma_len, ma_subtype) = struct.unpack("!BB", mgmt_addr[:2])
    # ipv4 subtype
    if ma_subtype == MGMT_ADDR_SUBTYPE_IPV4:
        ip = socket.inet_ntoa(mgmt_addr[2: (1 + ma_len)])
        switch_port_info['switch_info']['switch_ip'] = ip


def ignore(switch_port_info, tlv_value):
    pass


class LldpHook(base.ProcessingHook):
    """Hook to process LLDP tlvs and populate local_link_connection"""

    tlv_hdlrs = {LLDP_TLV_TYPE_PORT_ID: get_port_id,
                 LLDP_TLV_TYPE_PORT_DESC: get_port_description,
                 LLDP_TLV_TYPE_SYSTEM_NAME: get_system_name,
                 LLDP_TLV_TYPE_SYSTEM_DESC: get_system_description,
                 LLDP_TLV_TYPE_MGMT_ADDR: get_mgmt_addr}

    def before_update(self, introspection_data, node_info, **kwargs):
        lldp_info = introspection_data['inventory'].get('lldp_info', {})
        LOG.info(_LI("received LLDP TLVs: %s"), lldp_info)

        for ifname, tlvs in lldp_info.items():
            port = introspection_data['interfaces'].get(ifname)
            if not tlvs or not port:
                continue
            switch_port_info = {
                "switch_id": port['mac'],
                "switch_info": {
                    "is_native": True,
                }
            }
            for (tlv_type, tlv_value) in tlvs:
                tlv_hdlr = self.tlv_hdlrs.get(tlv_type, ignore)
                tlv_hdlr(switch_port_info, binascii.unhexlify(tlv_value))

            patches = []
            # Check mandatory fields
            switch_id = switch_port_info.get('switch_id', '')
            if not switch_id:
                LOG.info(_LI("required field switch_id is not present"))
                continue
            port_id = switch_port_info.get('port_id', '')
            if not port_id:
                LOG.info(_LI("required field port_id is not present"))
                continue
            for key, value in switch_port_info.items():
                if key is 'switch_info':
                    value = json.dumps(value)
                patches.append({'op': 'add',
                                'path': '/local_link_connection/%s' % key,
                                'value': value})
            node_info.patch_port(str(port['mac']), patches)
