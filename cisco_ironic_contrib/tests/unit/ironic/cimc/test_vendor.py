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
from ironic.tests.unit.drivers.modules.cimc import test_common

imcsdk = importutils.try_import('ImcSdk')

TEST_DATA = {
    "uuid": "uuiduuiduuiduuiduuiduuid",
    "mac": "fake_mac_address",
    "vlan": 600,
    "pxe": False
}


class CIMCPXEVendorPassthruTestCase(test_common.CIMCBaseTestCase):

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

    @mock.patch.object(objects, 'Port', autospec=True)
    def test_delete_vnic_port_not_found(self, mock_port):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            mock_port.list_by_node_id.return_value = []

            self.assertRaises(exception.NotFound,
                              task.driver.vendor.delete_vnic,
                              task, uuid="1")
