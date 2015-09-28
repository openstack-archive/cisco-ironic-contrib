# Copyright 2015 Cisco Systems
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from oslo_config import cfg
from oslo_log import log as logging
from oslo_service import loopingcall

from nova.network.neutronv2 import api as neutron
from nova.virt.ironic import driver as ironic_driver

LOG = logging.getLogger(__name__)

CONF = cfg.CONF


class CiscoIronicDriver(ironic_driver.IronicDriver):
    """Hypervisor driver for Ironic - bare metal provisioning."""

    def _check_for_vnic_creation(self, ironicclient, address):
        port = self.ironicclient.call("port.get_by_address", address)
        if port.extra['state'] == "UP":
            raise loopingcall.LoopingCallDone()

    def macs_for_instance(self, instance):
        return None

    def _plug_vifs(self, node, instance, network_info):
        LOG.debug('Plug VIFs called for instance', instance=instance)
        node_uuid = instance.get('node')
        client = neutron.get_client(None, admin=True)
        for vif in network_info:
            network = client.show_network(vif['network']['id'])
            net_info = {
                'vlan': network['network']['provider:segmentation_id'],
                'mac': vif['address'],
                'uuid': vif['id'],
                'pxe': False
            }
            self.ironicclient.call("node.vendor_passthru", node_uuid,
                                   "add_vnic", args=net_info)

            timer = loopingcall.FixedIntervalLoopingCall(
                self._check_for_vnic_creation,
                self.ironicclient, vif['address'])
            timer.start(interval=5).wait()
        LOG.debug('Plug VIFs successful for instance', instance=instance)

    def _unplug_vifs(self, node, instance, network_info):
        node_uuid = instance.get('node')
        # Delete vnics from UCS for this node via vendor passthru
        for vif in network_info:
            net_info = {
                'uuid': vif['id']
            }
            self.ironicclient.call("node.vendor_passthru", node_uuid,
                                   "delete_vnic", args=net_info)
