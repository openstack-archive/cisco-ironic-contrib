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

from ironic.common import exception
from ironic.common import states
from ironic.conductor import task_manager
from ironic.conductor import utils as manager_utils
from ironic.drivers import base
from ironic.drivers.modules import iscsi_deploy
from ironic import objects

from cisco_ironic_contrib.ironic.cimc import common

imcsdk = importutils.try_import('ImcSdk')

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class CIMCPXEVendorPassthru(iscsi_deploy.VendorPassthru):

    @base.passthru(['POST'], async=True)
    @task_manager.require_exclusive_lock
    def add_vnic(self, task, **kwargs):

        LOG.info("ENSURING NODE ON FOR VNIC ADDITION!")
        if task.node.power_state != states.POWER_ON:
            manager_utils.node_power_action(task, states.REBOOT)

        LOG.info("ADDING PORT TO IRONIC DB")
        new_port = objects.Port(
            task.context, node_id=task.node.id, address=kwargs['mac'],
            extra={"vif_port_id": kwargs['uuid'],
                   "type": "tenant", "state": "DOWN"})

        new_port.create()

        try:
            LOG.info("ADDING VNIC TO CIMC")
            common.add_vnic(
                task, kwargs['uuid'], kwargs['mac'],
                kwargs['vlan'], kwargs['pxe'])
        except imcsdk.ImcException:
            new_port.extra = {"vif_port_id": kwargs['uuid'], "type": "tenant",
                              "state": "ERROR"}
            LOG.error("ADDING VNIC FAILED")
        else:
            new_port.extra = {"vif_port_id": kwargs['uuid'], "type": "tenant",
                              "state": "UP"}
            LOG.info("ADDING VNIC SUCCESSFUL")
        new_port.save()

    @base.passthru(['POST'], async=True)
    @task_manager.require_exclusive_lock
    def delete_vnic(self, task, **kwargs):

        # Ensure Node is powered on before changing VNIC settings
        if task.node.power_state != states.POWER_ON:
            manager_utils.node_power_action(task, states.REBOOT)

        # Use neutron UUID to get port from ironic DB
        ports = objects.Port.list_by_node_id(task.context, task.node.id)
        todelete = None
        for port in ports:
            if port['extra']['vif_port_id'] == kwargs['uuid']:
                todelete = port
                break

        if todelete is None:
            raise exception.NotFound("No port matched uuid provided")
        # Delete vnic from server
        common.delete_vnic(task, kwargs['uuid'])
        # Delete port from ironic port DB
        todelete.destroy()
