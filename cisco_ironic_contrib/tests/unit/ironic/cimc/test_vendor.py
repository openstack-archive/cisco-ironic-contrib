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

import mock

from oslo_utils import importutils

from ironic.common import exception
from ironic.common import states
from ironic.conductor import task_manager
from ironic.conductor import utils as manager_utils
from ironic import objects
from ironic.tests.unit.drivers.modules.cimc import test_common

from cisco_ironic_contrib.ironic.cimc import common

imcsdk = importutils.try_import('ImcSdk')

TEST_DATA = {
    "uuid": "uuiduuiduuiduuiduuiduuid",
    "mac": "fake_mac_address",
    "vlan": 600,
    "pxe": False
}


class CIMCPXEVendorPassthruTestCase(test_common.CIMCBaseTestCase):

    @mock.patch.object(common, 'add_vnic', autospec=True)
    @mock.patch.object(manager_utils, 'node_power_action', autospec=True)
    @mock.patch.object(objects, 'Port', autospec=True)
    def _test_add_vnic(self, mock_port, mock_power_action,
                       mock_add_vnic, initial_state=states.POWER_OFF):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.node.power_state = initial_state
            mock_port.return_value.extra = {}

            task.driver.vendor.add_vnic(task, **TEST_DATA)

            if initial_state != states.POWER_ON:
                mock_power_action.assert_called_once_with(task, states.REBOOT)
            else:
                self.assertFalse(mock_power_action.called)

            mock_port.assert_called_once_with(
                task.context, node_id=task.node.id, address=TEST_DATA['mac'],
                extra={"type": "tenant", "state": "DOWN",
                       "vif_port_id": TEST_DATA['uuid']})

            mock_port.return_value.create.assert_called_once_with()

            mock_add_vnic.assert_called_once_with(
                task, TEST_DATA['uuid'], TEST_DATA['mac'],
                TEST_DATA['vlan'], TEST_DATA['pxe'])

            self.assertEqual(mock_port.return_value.extra['state'],
                             "UP")

            mock_port.return_value.save.assert_called_once_with()

    def test_add_vnic_node_off(self):
        self._test_add_vnic()

    def test_add_vnic_node_already_on(self):
        self._test_add_vnic(initial_state=states.POWER_ON)

    @mock.patch.object(common, 'add_vnic', autospec=True)
    @mock.patch.object(objects, 'Port', autospec=True)
    def test_add_vnic_fail(self, mock_port, mock_add_vnic):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.node.power_state = states.POWER_ON
            mock_port.return_value.extra = {}

            mock_add_vnic.side_effect = imcsdk.ImcException("Boom")

            task.driver.vendor.add_vnic(task, **TEST_DATA)

            self.assertEqual(mock_port.return_value.extra['state'],
                             "ERROR")

            mock_port.return_value.save.assert_called_once_with()

    @mock.patch.object(common, 'delete_vnic', autospec=True)
    @mock.patch.object(manager_utils, 'node_power_action', autospec=True)
    @mock.patch.object(objects, 'Port', autospec=True)
    def _test_delete_vnic(self, mock_port, mock_power_action, mock_delete_vnic,
                          initial_state=states.POWER_OFF):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.node.power_state = initial_state

            port1 = mock.MagicMock()
            port1.__getitem__.return_value = {'vif_port_id': "1"}

            port2 = mock.MagicMock()
            port2.__getitem__.return_value = {'vif_port_id': "2"}

            port3 = mock.MagicMock()
            port3.__getitem__.return_value = {'vif_port_id': "3"}

            mock_port.list_by_node_id.return_value = [port1, port2, port3]

            task.driver.vendor.delete_vnic(task, uuid="1")

            if initial_state != states.POWER_ON:
                mock_power_action.assert_called_once_with(task, states.REBOOT)
            else:
                self.assertFalse(mock_power_action.called)

            mock_port.list_by_node_id.assert_called_with(
                task.context, task.node.id)

            mock_delete_vnic.assert_called_once_with(task, "1")

    def test_delete_vnic_node_off(self):
        self._test_delete_vnic()

    def test_delete_vnic_node_already_on(self):
        self._test_delete_vnic(initial_state=states.POWER_ON)

    @mock.patch.object(objects, 'Port', autospec=True)
    def test_delete_vnic_port_not_found(self, mock_port):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.node.power_state = states.POWER_ON
            mock_port.list_by_node_id.return_value = []

            self.assertRaises(exception.NotFound,
                              task.driver.vendor.delete_vnic,
                              task, uuid="1")
