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

from oslo_config import cfg
from oslo_utils import importutils

from ironic.conductor import task_manager
from ironic.drivers.modules.cimc import common as cimc_common
from ironic.tests.unit.drivers.modules.cimc import test_common

from cisco_ironic_contrib.ironic.cimc import common

imcsdk = importutils.try_import('ImcSdk')

CONF = cfg.CONF


@mock.patch.object(cimc_common, 'cimc_handle', autospec=True)
class AddVnicTestCase(test_common.CIMCBaseTestCase):

    def _test_add_vnic(self, mock_mo, mock_handle, pxe=False):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            with mock_handle(task) as handle:
                first_mock = mock.MagicMock()
                second_mock = mock.MagicMock()
                mock_mo.side_effect = [first_mock, second_mock]

                mo = handle.get_imc_managedobject.return_value
                mo.__getitem__.return_value.Dn = "DN"
                handle.xml_query.return_value.error_code = None

                dn = "DN/host-eth-eth0"

                common.add_vnic(task, 0, "mac_address", 600, pxe=pxe)

                mock_mo.assert_any_call("adaptorEthGenProfile")
                mock_mo.assert_any_call("adaptorHostEthIf")

                first_mock.set_attr.assert_any_call("name", "eth0")
                first_mock.set_attr.assert_any_call("mtu", "1500")
                first_mock.set_attr.assert_any_call(
                    "pxeBoot", "enabled" if pxe else "disabled")
                first_mock.set_attr.assert_any_call("Dn", dn)
                first_mock.set_attr.assert_any_call("mac", "mac_address")
                first_mock.set_attr.assert_any_call("uplinkPort", "0")

                second_mock.set_attr.assert_any_call("vlanMode", "ACCESS")
                second_mock.set_attr.assert_any_call("vlan", "600")
                second_mock.set_attr.assert_any_call("Dn", dn)

                handle.xml_query.assert_called_once_with(
                    imcsdk.ImcCore.ExternalMethod.return_value,
                    imcsdk.WriteXmlOption.DIRTY)

    @mock.patch.object(imcsdk.ImcCore, 'ManagedObject', autospec=True)
    def test_add_vnic(self, mock_mo, mock_handle):
        self._test_add_vnic(mock_mo, mock_handle)

    @mock.patch.object(imcsdk.ImcCore, 'ManagedObject', autospec=True)
    def test_add_vnic_pxe(self, mock_mo, mock_handle):
        self._test_add_vnic(mock_mo, mock_handle, pxe=True)

    def test_add_vnic_fail(self, mock_handle):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            with mock_handle(task) as handle:
                handle.xml_query.return_value.error_code = "123456"
                self.assertRaises(imcsdk.ImcException, common.add_vnic,
                                  task, 0, "mac_address", 600)


@mock.patch.object(cimc_common, 'cimc_handle', autospec=True)
class DeleteVnicTestCase(test_common.CIMCBaseTestCase):

    def test_delete_vnic(self, mock_handle):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            with mock_handle(task) as handle:
                mo = handle.get_imc_managedobject.return_value
                mo.__getitem__.return_value.Dn = "DN"

                common.delete_vnic(task, 4)

                expected_params = {"Dn": "DN/host-eth-eth4"}
                handle.remove_imc_managedobject.assert_called_once_with(
                    None, class_id="adaptorHostEthIf", params=expected_params)

    def test_delete_vnic_fail(self, mock_handle):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            with mock_handle(task) as handle:
                mo = handle.get_imc_managedobject.return_value
                mo.__getitem__.return_value.Dn = "DN"
                handle.remove_imc_managedobject.side_effect = (
                    imcsdk.ImcException("Boom"))

                self.assertRaises(imcsdk.ImcException,
                                  common.delete_vnic, task, 4)

                expected_params = {"Dn": "DN/host-eth-eth4"}
                handle.remove_imc_managedobject.assert_called_once_with(
                    None, class_id="adaptorHostEthIf", params=expected_params)

    @mock.patch.object(common, 'clean_vnic', autospec=True)
    def test_delete_vnic_with_default_vnic(self, mock_clean, mock_handle):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            with mock_handle(task) as handle:
                mo = handle.get_imc_managedobject.return_value
                mo.__getitem__.return_value.Dn = "DN"

                common.delete_vnic(task, 0)
                mock_clean.assert_called_once_with(task, 0)
