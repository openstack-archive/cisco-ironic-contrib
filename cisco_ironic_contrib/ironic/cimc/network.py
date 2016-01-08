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

import json

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import importutils

from ironic.common import network as common_net
from ironic.common import states
from ironic.conductor import utils as manager_utils
from ironic.networks import base
from ironic import objects

from cisco_ironic_contrib.ironic.cimc import common

imcsdk = importutils.try_import('ImcSdk')

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

STATE_UP = "UP"
STATE_DOWN = "DOWN"
STATE_ERROR = "ERROR"

TYPE_TENANT = "tenant"
TYPE_PROVISIONING = "deploy"
TYPE_CLEANING = "clean"


class NetworkProvider(base.NetworkProvider):

    def _add_network(self, task, network, typ):
        if task.node.power_state != states.POWER_ON:
            manager_utils.node_power_action(task, states.REBOOT)

        client = common_net.get_neutron_client()
        port = client.create_port({
            'port': {
                'network_id': network,
                'admin_state_up': True,
                'binding:vnic_type': 'baremetal',
                'device_owner': 'baremetal:none',
                'binding:host_id': task.node.uuid,
                'binding:profile': {
                    'local_link_information': [
                        task.node.driver_info['uplink0-local-link']],
                }
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
            pxe_enabled=True,
            extra={"vif_port_id": port['port']['id'], "vnic_id": 0,
                   "type": typ, "state": STATE_UP})
        new_port.create()
        task.ports = objects.Port.list_by_node_id(task.context, task.node.id)

    def _remove_network(self, task, typ):
        if task.node.power_state != states.POWER_ON:
            manager_utils.node_power_action(task, states.REBOOT)

        client = common_net.get_neutron_client()

        ports = objects.Port.list_by_node_id(task.context, task.node.id)
        for port in ports:
            if port['extra'].get('type') == typ:
                common.delete_vnic(task, port['extra']['vnic_id'])
                client.delete_port(port['extra']['vif_port_id'])
                port.destroy()

    def add_provisioning_network(self, task):
        LOG.debug("Plugging the provisioning!")
        self._add_network(task, CONF.provisioning_network_uuid,
                          TYPE_PROVISIONING)

    def remove_provisioning_network(self, task):
        LOG.debug("Unplugging the provisioning!")
        self._remove_network(task, TYPE_PROVISIONING)

    def configure_tenant_networks(self, task):
        node = task.node
        ports = objects.Port.list_by_node_id(task.context, node.id)
        vnic_id = 0
        for port in ports:
            pargs = port['extra']
            if (pargs.get('type') == TYPE_TENANT and
                    pargs['state'] == STATE_DOWN):
                vlan = pargs['seg_id']
                pg_id = port['portgroup_id']
                if pg_id is not None:
                    pg = objects.Portgroup.get(task.context, pg_id)
                    if pg['extra'].get('mode', 0) == 4:
                        vlan = None
                try:
                    common.add_vnic(
                        task, vnic_id, port['address'],
                        vlan, pxe=port['pxe_enabled'])
                except imcsdk.ImcException:
                    port.extra = {x: pargs[x] for x in pargs}
                    port.extra['state'] = STATE_ERROR
                    LOG.error("ADDING VNIC FAILED")
                else:
                    if pg_id is None:
                        upl = vnic_id % task.node.driver_info['uplinks']
                        lo_li = [json.loads(
                            node.driver_info['uplink%d-local-link' % upl])]
                        self._bind_port(task, pargs['vif_port_id'], lo_li)
                    port.extra = {x: pargs[x] for x in pargs}
                    port.extra['state'] = STATE_UP
                    port.extra['vnic_id'] = vnic_id
                    vnic_id = vnic_id + 1
                    LOG.info("ADDING VNIC SUCCESSFUL")
                port.save()
        portgroups = objects.Portgroup.list_by_node_id(task.context, node.id)
        for pg in portgroups:
            lo_li = []
            ports = objects.Port.list_by_portgroup_id(task.context, pg.id)
            for port in ports:
                vnic_id = port.extra['vnic_id']
                upl = vnic_id % task.node.driver_info['uplinks']
                lo_li.append(json.loads(
                    node.driver_info['uplink%d-local-link' % upl]))
            self._bind_port(task, pg.extra['vif_port_id'], lo_li)

    def _bind_port(self, task, vif_port_id, lo_li):
        client = common_net.get_neutron_client()
        client.update_port(vif_port_id, {
            'port': {
                'admin_state_up': True,
                'binding:vnic_type': 'baremetal',
                'device_owner': 'baremetal:none',
                'binding:host_id': task.node.uuid,
                'binding:profile': {
                    'local_link_information': lo_li,
                }
            }
        })

    def unconfigure_tenant_networks(self, task):
        ports = objects.Port.list_by_node_id(task.context, task.node.id)
        for port in ports:
            pargs = port['extra']
            if pargs.get('type') == "tenant" and pargs['state'] == STATE_UP:
                common.delete_vnic(task, port['extra']['vnic_id'])
                port.extra = {x: pargs[x] for x in pargs}
                port.extra['state'] = STATE_DOWN
                port.extra['vnic_id'] = None
                port.save()
                LOG.info("DELETEING VNIC SUCCESSFUL")

    def add_cleaning_network(self, task):
        LOG.debug("Plugging the cleaning!")
        self._add_network(task, CONF.neutron.cleaning_network_uuid,
                          TYPE_CLEANING)

    def remove_cleaning_network(self, task):
        LOG.debug("Unplugging the cleaning!")
        self._remove_network(task, TYPE_CLEANING)
