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

from nova import context as nova_context
from nova.network.neutronv2 import api as neutron
from nova import test
from nova.tests.unit import fake_instance
from nova.tests.unit import utils
from nova.tests.unit.virt.ironic import utils as ironic_utils
from nova.virt.ironic import client_wrapper as cw

from cisco_ironic_contrib.nova import driver

CONF = cfg.CONF
FAKE_CLIENT = ironic_utils.FakeClient()


class FakeClientWrapper(cw.IronicClientWrapper):
    def _get_client(self, retry_on_conflict=False):
        return FAKE_CLIENT


def vendor_passthru(self, *args, **kwargs):
    pass


def get_by_address(self, *args, **kwargs):
    pass


FAKE_CLIENT_WRAPPER = FakeClientWrapper()

ironic_utils.FakeNodeClient.vendor_passthru = vendor_passthru
ironic_utils.FakePortClient.get_by_address = get_by_address


@mock.patch.object(cw, 'IronicClientWrapper', lambda *_: FAKE_CLIENT_WRAPPER)
class CiscoIronicDriverTestCase(test.NoDBTestCase):

    @mock.patch.object(cw, 'IronicClientWrapper',
                       lambda *_: FAKE_CLIENT_WRAPPER)
    def setUp(self):
        super(CiscoIronicDriverTestCase, self).setUp()
        self.driver = driver.CiscoIronicDriver(None)
        self.ctx = nova_context.get_admin_context()

    @mock.patch.object(FAKE_CLIENT, 'node')
    def test_macs_for_instance(self, mock_node):
        node = ironic_utils.get_test_node()
        mock_node.get.return_value = node
        instance = fake_instance.fake_instance_obj(self.ctx,
                                                   node=node.uuid)
        result = self.driver.macs_for_instance(instance)
        self.assertIsNone(result)

    @mock.patch.object(neutron, 'get_client')
    @mock.patch.object(FAKE_CLIENT.node, 'vendor_passthru')
    def test_plug_vifs_with_port(self, mock_vp, mock_neutron):
        node = ironic_utils.get_test_node()
        instance = fake_instance.fake_instance_obj(self.ctx,
                                                   node=node.uuid)
        network_info = utils.get_test_network_info()
        mock_neutron.return_value.show_network.return_value = {
            'network': {
                'provider:segmentation_id': 600}}

        self.driver._plug_vifs(node, instance, network_info)
        expected_info = {
            'vlan': 600,
            'mac': network_info[0]['address'],
            'uuid': network_info[0]['id'],
            'pxe': False
        }
        mock_vp.assert_called_once_with(node.uuid, 'add_vnic',
                                        args=expected_info)

    @mock.patch.object(neutron, 'get_client')
    @mock.patch.object(FAKE_CLIENT.node, 'vendor_passthru')
    def test_plug_vifs_no_network_info(self, mock_vp, mock_neutron):
        node = ironic_utils.get_test_node()
        instance = fake_instance.fake_instance_obj(self.ctx,
                                                   node=node.uuid)
        network_info = []
        self.driver._plug_vifs(node, instance, network_info)
        self.assertFalse(mock_vp.called)

    @mock.patch.object(FAKE_CLIENT.node, 'vendor_passthru')
    def test_unplug_vifs(self, mock_vp):
        node = ironic_utils.get_test_node()
        instance = fake_instance.fake_instance_obj(self.ctx,
                                                   node=node.uuid)
        network_info = utils.get_test_network_info()
        expected_info = {
            'uuid': network_info[0]['id'],
        }
        self.driver._unplug_vifs(node, instance, network_info)
        mock_vp.assert_called_once_with(node.uuid, 'delete_vnic',
                                        args=expected_info)

    @mock.patch.object(FAKE_CLIENT.node, 'vendor_passthru')
    def test_unplug_vifs_no_network_info(self, mock_vp):
        node = ironic_utils.get_test_node()
        instance = fake_instance.fake_instance_obj(self.ctx,
                                                   node=node.uuid)
        network_info = []
        self.driver._unplug_vifs(node, instance, network_info)
        self.assertFalse(mock_vp.called)
