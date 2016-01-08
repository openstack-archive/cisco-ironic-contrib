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

import eventlet

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import importutils

from ironic.common import exception
from ironic.common import keystone
from ironic.common import network as common_net
from ironic.common import states
from ironic.conductor import task_manager
from ironic.conductor import utils as manager_utils
from ironic.drivers import base
from ironic.drivers.modules.cimc import common as cimc_common
from ironic.drivers.modules import inspector
from ironic import objects

from cisco_ironic_contrib.ironic.cimc import common
from cisco_ironic_contrib.ironic.cimc import network

imcsdk = importutils.try_import('ImcSdk')
client = importutils.try_import('ironic_inspector_client')

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class CIMCAndInspectorInspect(base.InspectInterface):

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
            adaptorunits = handle.get_imc_managedobject(
                in_mo=rackunit, class_id=imcsdk.AdaptorUnit.class_id())
            uplinks = handle.get_imc_managedobject(
                in_mo=adaptorunits[0], class_id="AdaptorExtEthIf")
            driver_info['uplinks'] = len(uplinks)
            for uplink in uplinks:
                driver_info['uplink%s-mac' % uplink.PortId] = uplink.Mac

            task.node.driver_info = driver_info
            task.node.save()

            inspect_nic1 = handle.get_imc_managedobject(
                None, None,
                params={"Dn": "%s/host-eth-eth0" % adaptorunits[0].Dn})
            inspect_nic2 = handle.get_imc_managedobject(
                None, None,
                params={"Dn": "%s/host-eth-eth1" % adaptorunits[0].Dn})

        # Configure vnic for the provisioning network but without a neutron
        # port so that the ironic inspector boots the node.
        client = common_net.get_neutron_client()
        client.show_network(CONF.provisioning_network_uuid)
        seg_id = network['network']['provider:segmentation_id']

        common.add_vnic(task, 0, inspect_nic1.Mac, seg_id, pxe=True)
        common.add_vnic(task, 1, inspect_nic2.Mac, seg_id, pxe=True)

        inspect_port1 = objects.Port(
            task.context, node_id=task.node.id,
            address=inspect_nic1.Mac,
            pxe_enabled=True,
            extra={"type": "INSPECT", "vnic_id": 0,
                   "state": network.STATE_UP, "uplink": 0})
        inspect_port1.create()

        inspect_port2 = objects.Port(
            task.context, node_id=task.node.id,
            address=inspect_nic2.Mac,
            pxe_enabled=True,
            extra={"type": "INSPECT", "vnic_id": 1,
                   "state": network.STATE_UP, "uplink": 1})
        inspect_port2.create()

        task.ports = objects.Port.list_by_node_id(task.context, task.node.id)

        # Activate Ironic Inspector
        eventlet.spawn_n(inspector._start_inspection,
                         task.node.uuid, task.context)
        return states.INSPECTING

    @base.driver_periodic_task(spacing=CONF.inspector.status_check_period)
    def _check_inspection_progress(self, manager, context):
        # Periodically check on the progress of the inspection
        filters = {'provision_state': states.INSPECTING}
        node_iter = manager.iter_nodes(filters=filters)

        for node_uuid, driver in node_iter:
            try:
                lock_purpose = 'checking in-band inspection progress'
                with task_manager.acquire(context, node_uuid, shared=True,
                                          purpose=lock_purpose) as task:
                    if(task.node.provision_state != states.INSPECTING and
                            not isinstance(task.driver.inspect,
                                           self.__class__)):
                        continue
                    if CONF.auth_strategy == 'keystone':
                        task.context.auth_token = (
                            keystone.get_admin_auth_token())

                    try:
                        status = inspector._call_inspector(
                            client.get_status, task.node.uuid, task.context)
                    except Exception:
                        return

                    error = status.get('error')
                    finished = status.get('finished')
                    if not error and not finished:
                        continue

                    task.upgrade_lock()

                    if error:
                        task.process_event('fail')
                    elif finished:
                        self._finish_inspection(task)
                        task.process_event('done')
            except (exception.NodeLocked, exception.NodeNotFound):
                continue

    def _finish_inspection(self, task):
        # Process data in the db set by inspector into nessesary formats for
        # our black magic, and delete the inspect port we created.
        driver_info = dict(task.node.driver_info)

        for port in task.ports:
            if port.extra.get('type') == "INSPECT":
                driver_info['uplink%s-local-link' % port.extra['uplink']] = (
                    port.local_link_connection)
                common.delete_vnic(task, port.extra['vnic_id'])
                port.destroy()
            else:
                port.destroy()

        task.node.driver_info = driver_info
        task.node.save()
        task.ports = objects.Port.list_by_node_id(task.context, task.node.id)
