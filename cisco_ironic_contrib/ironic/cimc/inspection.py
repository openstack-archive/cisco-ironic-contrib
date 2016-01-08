# Copyright 2015, Cisco Systems.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import shutil

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import importutils

from ironic.common import boot_devices
from ironic.common import dhcp_factory
from ironic.common import exception
from ironic.common import network as common_net
from ironic.common import pxe_utils
from ironic.common import states
from ironic.driver import base
from ironic.drivers.modules import inspector
from ironic.drivers.modules import pxe
from ironic.drivers.modules.cimc import cimc_common
from ironic import objects

from cisco_ironic_contrib.ironic.cimc import common
from cisco_ironic_contrib.ironic.cimc import network

imcsdk = importutils.try_import('ImcSdk')

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

class InspectorInterface(base.InspectInterface):

    def get_properties(self):
        pass

    def validate(self, task):
        cimc_common.parse_driver_info(task.node)

    def inspect_hardware(self, task):
        driver_info = dict(task.node.driver_info)

        if task.node.power_state != states.POWER_ON:
            manager_utils.node_power_action(task, states.REBOOT)

        with cimc_common.cimc_handle(task) as handle:
            rackunit = handle.get_imc_managedobject(
                None, imcsdk.ComputeRackUnit.class_id())
            adapatorunits = handle.get_imc_managedobject(
                in_mo=rackunit, class_id=imcsdk.AdaptorUnit.class_id())
            uplinks = handle.get_imc_managedobject(
                in_mo=adapatorunits[0], class_id="AdaptorExtEthIf")
            driver_info['uplinks'] = len(uplinks)
            for uplink in uplinks:
                driver_info['uplink%s-mac' % uplink.PortId] = uplink.Mac

            task.node.driver_info = driver_info
            task.node.save()

            inspect_nic = handle.get_imc_managedobject(
                None, None,
                params={"Dn": "%s/host-eth-eth0" % adaptorunits[0].Dn})

        # Configure vnic for the provisioning network but without a neutron
        # port so that the ironic inspector boots the node.
        client = common_net.get_neutron_client()
        client.show_network(CONF.provisioning_network_uuid)
        seg_id = network['network']['provider:segmentation_id']

        common.add_vnic(task, 0, inspect_nic.Mac, seg_id, pxe=True)

        inspect_port = objects.Port(
            task.context, node_id=task.node.id, 
            address=inspect_nic.Mac,
            pxe_enabled=True,
            extra={"type": "INSPECT", "vnic_id": 0, "state": network.STATE_UP})
        inspect_port.create()
        task.ports = objects.Port.list_by_node_id(task.context, task.node.id)

        # Activate Ironic Inspector
        eventlet.spawn_n(_start_inspection, task.node.uuid, task.context)
        return states.INSPECTING

    def _check_inspection_progress(self):
        # Periodically check on the progress of the inspection
        pass

    def _finish_inspection(self, task):
        # Process data in the db set by inspector into nessesary formats for our black magic,
        # delete the inspect port we created and finish inspecting.
        pass
