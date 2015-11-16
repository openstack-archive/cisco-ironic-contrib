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

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import importutils

from ironic.common import states
from ironic.conductor import utils as manager_utils
from ironic.dhcp import neutron
# from ironic.networks import base
from ironic import objects

from cisco_ironic_contrib.ironic.cimc import common

imcsdk = importutils.try_import('ImcSdk')

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class NetworkProvider(object):  # base.NetworkProvider):

    def add_provisioning_network(self, task):
        LOG.debug("Plugging the provisioning!")
        if task.node.power_state != states.POWER_ON:
            manager_utils.node_power_action(task, states.REBOOT)

        client = neutron._build_client(task.context.auth_token)
        port = client.create_port({
            'port': {
                "network_id":
                    CONF.neutron.cleaning_network_uuid,
            }
        })

        vnic_id = 0
        network = client.show_network(port['port']['network_id'])
        seg_id = network['network']['provider:segmentation_id']

        try:
            common.add_vnic(
                task, vnic_id, port['port']['mac_address'], seg_id, pxe=True)
        except imcsdk.ImcException:
            client.delete_port(port['port']['id'])
            raise

        new_port = objects.Port(
            task.context, node_id=task.node.id,
            address=port['port']['mac_address'],
            extra={"vif_port_id": port['port']['id'],
                   "vnic_id": 0,
                   "type": "deploy", "state": "ACTIVE"})
        new_port.create()
        task.ports = objects.Port.list_by_node_id(task.context, task.node.id)

    def remove_provisioning_network(self, task):
        LOG.debug("Unplugging the provisioning!")
        if task.node.power_state != states.POWER_ON:
            manager_utils.node_power_action(task, states.REBOOT)

        client = neutron._build_client(task.context.auth_token)

        ports = objects.Port.list_by_node_id(task.context, task.node.id)
        for port in ports:
            if port['extra'].get('type') == "deploy":
                common.delete_vnic(task, port['extra']['vnic_id'])
                client.delete_port(port['extra']['vif_port_id'])
                port.destroy()

    def configure_tenant_networks(self, task):
        ports = objects.Port.list_by_node_id(task.context, task.node.id)
        vnic_id = 0
        for port in ports:
            pargs = port['extra']
            if pargs.get('type') == "tenant" and pargs['state'] == "DOWN":
                try:
                    common.add_vnic(
                        task, vnic_id, port['address'],
                        pargs['seg_id'], pxe=pargs['pxe'])
                except imcsdk.ImcException:
                    port.extra = {x: pargs[x] for x in pargs}
                    port.extra['state'] = "ERROR"
                    LOG.error("ADDING VNIC FAILED")
                else:
                    port.extra = {x: pargs[x] for x in pargs}
                    port.extra['state'] = "UP"
                    port.extra['vnic_id'] = vnic_id
                    vnic_id = vnic_id + 1
                    LOG.info("ADDING VNIC SUCCESSFUL")
                port.save()

    def unconfigure_tenant_networks(self, task):
        ports = objects.Port.list_by_node_id(task.context, task.node.id)
        for port in ports:
            pargs = port['extra']
            if pargs.get('type') == "tenant" and pargs['state'] == "UP":
                common.delete_vnic(task, port['extra']['vnic_id'])
                port.extra = {x: pargs[x] for x in pargs}
                port.extra['state'] = "DOWN"
                port.extra['vnic_id'] = None
                port.save()
                LOG.info("DELETEING VNIC SUCCESSFUL")

    def add_cleaning_network(self, task):
        pass

    def remove_cleaning_network(self, task):
        pass
