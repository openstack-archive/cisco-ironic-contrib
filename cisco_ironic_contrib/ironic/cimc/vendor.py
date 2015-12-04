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

import netaddr

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import importutils

from ironic.common import exception
from ironic.conductor import task_manager
from ironic.drivers import base
from ironic.drivers.modules import iscsi_deploy
from ironic import objects

from cisco_ironic_contrib.ironic.cimc import common

imcsdk = importutils.try_import('ImcSdk')

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class CIMCPXEVendorPassthru(iscsi_deploy.VendorPassthru):

    @base.passthru(['POST'], async=False)
    @task_manager.require_exclusive_lock
    def add_vnic(self, task, **kwargs):
        info = common.parse_driver_info(task.node)
        if not info.get('vPC', False):
            new_port = objects.Port(
                task.context, node_id=task.node.id, address=kwargs['mac'],
                pxe_enabled=kwargs['pxe'],
                extra={"vif_port_id": kwargs['uuid'], "seg_id": kwargs['vlan'],
                       "type": "tenant", "state": "DOWN"})

            new_port.create()
        else:
            n_of_pgs = len(objects.Portgroup.list_by_node_id(task.context,
                                                             task.node.id))

            port_group = objects.Portgroup(
                task.context, node_id=task.node.id, address=kwargs['mac'],
                extra={"vif_port_id": kwargs['uuid'],
                       "mode": 4 if n_of_pgs == 0 else 0})
            port_group.create()

            uplink_mac = netaddr.EUI(info['uplink0-mac'])
            for uplink in range(0, info['uplinks']):
                mac_addr = netaddr.EUI(int(uplink_mac) + 1 +
                                       info['uplinks'] +
                                       (info['uplinks'] * 2) +
                                       (n_of_pgs * info['uplinks']) +
                                       uplink,
                                       dialect=netaddr.mac_unix_expanded)
                str_addr = str(mac_addr).upper()
                new_port = objects.Port(
                    task.context, node_id=task.node.id, address=str_addr,
                    portgroup_id=port_group.id, pxe_enabled=kwargs['pxe'],
                    extra={"seg_id": kwargs['vlan'], "type": "tenant",
                           "state": "DOWN"})
                new_port.create()

    @base.passthru(['POST'], async=False)
    @task_manager.require_exclusive_lock
    def delete_vnic(self, task, **kwargs):
        info = common.parse_driver_info(task.node)
        if not info.get('vPC', False):
            # Use neutron UUID to get port from ironic DB
            ports = objects.Port.list_by_node_id(task.context, task.node.id)
            todelete = None
            for port in ports:
                if (port['extra']['vif_port_id'] == kwargs['uuid'] and
                        port['extra']['state'] == "DOWN"):
                    todelete = port
                    break

            if todelete is None:
                raise exception.NotFound("No port matched uuid provided")

            # Delete from DB
            todelete.destroy()
        else:
            portgroups = objects.Portgroup.list_by_node_id(task.context,
                                                           task.node.id)
            grouptodelete = None
            for portgroup in portgroups:
                if (portgroup['extra']['vif_port_id'] == kwargs['uuid']):
                    grouptodelete = portgroup
                    break

            if grouptodelete is None:
                raise exception.NotFound("No portgroup matched uuid provided")

            ports = objects.Port.list_by_portgroup_id(task.context,
                                                      grouptodelete.id)
            for port in ports:
                if port['extra']['state'] == "DOWN":
                    port.destroy()
                else:
                    port['port_group_id'] = None
                    port.save()

            grouptodelete.destroy()
