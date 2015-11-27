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
from ironic.conductor import task_manager
from ironic import objects

from cisco_ironic_contrib.tests.unit.ironic.cimc import test_common

imcsdk = importutils.try_import('ImcSdk')

TEST_DATA = {
    "uuid": "uuiduuiduuiduuiduuiduuid",
    "mac": "fake_mac_address",
    "vlan": 600,
    "pxe": False
}


class CIMCPXEVendorPassthruTestCase(test_common.BaseTestCase):

    @mock.patch.object(objects, 'Port', autospec=True)
    def test_add_vnic(self, mock_port):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.vendor.add_vnic(task, **TEST_DATA)
            mock_port.assert_called_once_with(
                task.context, node_id=task.node.id, address=TEST_DATA['mac'],
                pxe_enabled=False,
                extra={"type": "tenant", "state": "DOWN", 'seg_id': 600,
                       "vif_port_id": TEST_DATA['uuid']})

            mock_port.return_value.create.assert_called_once_with()

    @mock.patch.object(objects, 'Portgroup', autospec=True)
    @mock.patch.object(objects, 'Port', autospec=True)
    def test_add_vnic_vpc(self, mock_port, mock_portgroup):
        info = self.node.driver_info
        info['vPC'] = True
        info['uplink0-mac'] = "74:A2:E6:32:FA:04"
        info['uplink1-mac'] = "74:A2:E6:32:FA:05"
        self.node.driver_info = info
        self.node.save()
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            mock_port.reset_mock()
            task.driver.vendor.add_vnic(task, **TEST_DATA)
            mock_portgroup.assert_called_once_with(
                task.context, node_id=task.node.id, address=TEST_DATA['mac'],
                extra={"vif_port_id": TEST_DATA['uuid']})

            calls = []
            calls.append(mock.call(
                task.context, node_id=task.node.id,
                address="74:A2:E6:32:FA:0B", pxe_enabled=False,
                portgroup_id=mock_portgroup.return_value.id,
                extra={"type": "tenant", "state": "DOWN", 'seg_id': 600}))
            calls.append(mock.call().create())
            calls.append(mock.call(
                task.context, node_id=task.node.id,
                address="74:A2:E6:32:FA:0C", pxe_enabled=False,
                portgroup_id=mock_portgroup.return_value.id,
                extra={"type": "tenant", "state": "DOWN", 'seg_id': 600}))
            calls.append(mock.call().create())
            mock_port.assert_has_calls(calls)

    @mock.patch.object(objects, 'Port', autospec=True)
    def test_delete_vnic(self, mock_port):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            port1 = mock.MagicMock()
            port1.__getitem__.return_value = {'vif_port_id': "1",
                                              'state': 'DOWN'}

            port2 = mock.MagicMock()
            port2.__getitem__.return_value = {'vif_port_id': "2",
                                              'state': 'DOWN'}

            port3 = mock.MagicMock()
            port3.__getitem__.return_value = {'vif_port_id': "3",
                                              'state': 'DOWN'}

            mock_port.list_by_node_id.return_value = [port1, port2, port3]

            task.driver.vendor.delete_vnic(task, uuid="1")

            mock_port.list_by_node_id.assert_called_with(
                task.context, task.node.id)

            port1.destroy.assert_called_once_with()

    @mock.patch.object(objects, 'Portgroup', autospec=True)
    @mock.patch.object(objects, 'Port', autospec=True)
    def test_delete_vnic_vpc(self, mock_port, mock_portgroup):
        info = self.node.driver_info
        info['vPC'] = True
        self.node.driver_info = info
        self.node.save()
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            portgroup1 = mock.MagicMock()
            portgroup1.__getitem__.return_value = {'vif_port_id': "1"}

            portgroup2 = mock.MagicMock()
            portgroup2.__getitem__.return_value = {'vif_port_id': "2"}

            mock_portgroup.list_by_node_id.return_value = [portgroup1,
                                                           portgroup2]

            port1 = mock.MagicMock()
            port1.__getitem__.return_value = {'vif_port_id': "1",
                                              'state': 'DOWN'}

            port2 = mock.MagicMock()
            port2.__getitem__.return_value = {'vif_port_id': "2",
                                              'state': 'DOWN'}

            mock_port.list_by_portgroup_id.return_value = [port1, port2]

            task.driver.vendor.delete_vnic(task, uuid="1")

            mock_port.list_by_node_id.assert_called_with(
                task.context, task.node.id)

            portgroup1.destroy.assert_called_once_with()
            port1.destroy.assert_called_once_with()
            port2.destroy.assert_called_once_with()

    @mock.patch.object(objects, 'Port', autospec=True)
    def test_delete_vnic_port_not_found(self, mock_port):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            mock_port.list_by_node_id.return_value = []

            self.assertRaises(exception.NotFound,
                              task.driver.vendor.delete_vnic,
                              task, uuid="1")
