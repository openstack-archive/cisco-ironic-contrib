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
from ironic.conductor import task_manager
from ironic.drivers import base
from ironic.drivers.modules import iscsi_deploy
from ironic import objects

imcsdk = importutils.try_import('ImcSdk')

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class CIMCPXEVendorPassthru(iscsi_deploy.VendorPassthru):

    @base.passthru(['POST'], async=True)
    @task_manager.require_exclusive_lock
    def add_vnic(self, task, **kwargs):
        LOG.info("ADDING PORT TO IRONIC DB")
        new_port = objects.Port(
            task.context, node_id=task.node.id, address=kwargs['mac'],
            extra={"vif_port_id": kwargs['uuid'], "seg_id": kwargs['vlan'],
                   "pxe": kwargs['pxe'], "type": "tenant", "state": "DOWN"})

        new_port.create()

    @base.passthru(['POST'], async=True)
    @task_manager.require_exclusive_lock
    def delete_vnic(self, task, **kwargs):
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
