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

from ironic.common import boot_devices
from ironic.common import pxe_utils
from ironic.common import states
from ironic.conductor import task_manager
from ironic.dhcp import neutron
from ironic.drivers.modules import deploy_utils
from ironic.drivers.modules import pxe
from ironic import objects
from ironic.tests.unit.drivers.modules.cimc import test_common

from cisco_ironic_contrib.ironic.cimc import boot
from cisco_ironic_contrib.ironic.cimc import common

CONF = cfg.CONF


def with_task(func):

    def wrapper(self, *args, **kwargs):
        with task_manager.acquire(self.context,
                                  self.node.uuid,
                                  shared=False) as task:
            return func(self, task, *args, **kwargs)

    return wrapper


class PXEBootTestCase(test_common.CIMCBaseTestCase):

    @mock.patch.object(objects, 'Port', autospec=True)
    @mock.patch.object(common, 'add_vnic', autospec=True)
    @mock.patch.object(neutron, '_build_client', autospec=True)
    @with_task
    def test_plug_provisioning(self, task, mock__build_client,
                               mock_add_vnic, mock_port):
        client = mock__build_client.return_value
        client.create_port.return_value = {
            'port': {
                'id': 'fake_id',
                'network_id': CONF.neutron.cleaning_network_uuid,
                'mac_address': 'fake_address'
            }
        }

        client.show_network.return_value = {
            'network': {
                'provider:segmentation_id': 600
            }
        }

        task.driver.boot._plug_provisioning(task)

        neutron_data = {
            'port': {
                "network_id": CONF.neutron.cleaning_network_uuid,
                "extra_dhcp_opts": pxe_utils.dhcp_options_for_instance(task),
            }
        }

        client.create_port.assert_called_once_with(neutron_data)
        client.show_network.assert_called_once_with(
            CONF.neutron.cleaning_network_uuid)
        mock_add_vnic.assert_called_once_with(
            task, 'fake_id', 'fake_address', 600, True)
        mock_port.assert_called_once_with(task.context, node_id=task.node.id,
                                          address='fake_address',
                                          extra={
                                              "vif_port_id": 'fake_id',
                                              "type": "deploy",
                                              "state": "ACTIVE"})
        mock_port.return_value.create.assert_called_once_with()

    @mock.patch.object(objects, 'Port', autospec=True)
    @mock.patch.object(neutron, '_build_client', autospec=True)
    @mock.patch.object(common, 'delete_vnic', autospec=True)
    @with_task
    def test_unplug_provisioning(
            self, task, mock_delete_vnic, mock__build_client, mock_port):

        portMock1 = mock.MagicMock()
        portMock1.__getitem__.return_value = {
            'type': 'tenant',
            'vif_port_id': 'port1'
        }

        portMock2 = mock.MagicMock()
        portMock2.__getitem__.return_value = {
            'type': 'deploy',
            'vif_port_id': 'port2'
        }

        portMock3 = mock.MagicMock()
        portMock3.__getitem__.return_value = {
            'type': 'tenant',
            'vif_port_id': 'port3'
        }

        mock_port.list_by_node_id.return_value = [portMock1,
                                                  portMock2,
                                                  portMock3]

        client = mock__build_client.return_value

        task.driver.boot._unplug_provisioning(task)

        mock_delete_vnic.assert_called_once_with(task, 'port2')
        client.delete_port.assert_called_once_with('port2')
        portMock2.destroy.assert_called_once_with()

    @with_task
    def test_validate(self, task):
        result = task.driver.boot.validate(task)
        self.assertIsNone(result)

    @mock.patch.object(deploy_utils, 'try_set_boot_device', autospec=True)
    @mock.patch.object(boot.PXEBoot, '_plug_provisioning', autospec=True)
    @mock.patch.object(pxe, '_get_deploy_image_info', autospec=True)
    @mock.patch.object(pxe, '_build_pxe_config_options', autospec=True)
    @mock.patch.object(pxe, '_get_instance_image_info', autospec=True)
    @mock.patch.object(pxe_utils, 'create_pxe_config', autospec=True)
    @mock.patch.object(pxe, '_cache_ramdisk_kernel', autospec=True)
    def test_prepare_ramdisk(self, mock_cache_ramdisk, mock_create_pxe,
                             mock_get_instance, mock_build_pxe,
                             mock_get_deploy, mock_plug_pro, mock_set_boot):
        self.node.provision_state = states.DEPLOYING
        self.node.save()

        with task_manager.acquire(self.context,
                                  self.node.uuid,
                                  shared=False) as task:
            task.driver.boot.prepare_ramdisk(task, {'foo': 'bar'})

            mock_set_boot.assert_called_once_with(task, boot_devices.PXE)
            mock_plug_pro.assert_called_once_with(mock.ANY, task)
            mock_get_deploy.assert_called_once_with(task.node)
            mock_build_pxe.assert_called_once_with(
                task, mock_get_deploy.return_value)
            mock_get_instance.assert_called_once_with(task.node, task.context)
            mock_create_pxe.assert_called_once_with(
                task, mock_build_pxe.return_value,
                CONF.pxe.pxe_config_template)
            mock_cache_ramdisk.assert_called_once_with(
                task.context, task.node, mock_get_deploy.return_value)

    @mock.patch.object(pxe.PXEBoot, 'prepare_instance', autospec=True)
    @mock.patch.object(boot.PXEBoot, '_unplug_provisioning', autospec=True)
    @with_task
    def test_prepare_instance(self, task, mock_unplug, mock_prepare):
        task.driver.boot.prepare_instance(task)
        mock_prepare.assert_called_once_with(mock.ANY, task)
        self.assertFalse(mock_unplug.called)

    @mock.patch.object(pxe.PXEBoot, 'prepare_instance', autospec=True)
    @mock.patch.object(boot.PXEBoot, '_unplug_provisioning', autospec=True)
    @with_task
    def test_prepare_instance_local(self, task, mock_unplug, mock_prepare):
        task.node.instance_info['capabilities'] = {"boot_option": "local"}
        task.driver.boot.prepare_instance(task)
        mock_prepare.assert_called_once_with(mock.ANY, task)
        mock_unplug.assert_called_once_with(mock.ANY, task)
