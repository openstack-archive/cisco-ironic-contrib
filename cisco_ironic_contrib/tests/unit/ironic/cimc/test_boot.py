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
from ironic.common import dhcp_factory
from ironic.common import pxe_utils
from ironic.common import states
from ironic.conductor import task_manager
from ironic.drivers.modules import deploy_utils
from ironic.drivers.modules import pxe
from ironic.objects import port

from cisco_ironic_contrib.tests.unit.ironic.cimc import test_common

from cisco_ironic_contrib.ironic.cimc import boot
from cisco_ironic_contrib.ironic.cimc import network

CONF = cfg.CONF


def with_task(func):

    def wrapper(self, *args, **kwargs):
        with task_manager.acquire(self.context,
                                  self.node.uuid,
                                  shared=False) as task:
            return func(self, task, *args, **kwargs)

    return wrapper


class GetProvisioningVifsTestCase(test_common.BaseTestCase):

    @with_task
    def test_get_provisioning_vifs(self, task):
        task.ports = [port.Port(**{
            'uuid': '0',
            'extra': {
                'type': 'tenant',
                'vif_port_id': 'port1',
                'vnic_id': 0
            }
        }), port.Port(**{
            'uuid': '1',
            'extra': {
                'type': 'deploy',
                'vif_port_id': 'port2',
                'vnic_id': 1
            }
        }), port.Port(**{
            'uuid': '2',
            'extra': {
                'type': 'tenant',
                'vif_port_id': 'port3',
                'vnic_id': 2
            }
        })]

        vifs = boot.get_provisioning_vifs(task)
        self.assertEqual({'1': 'port2'}, vifs)

    @with_task
    def test_get_provisioning_vifs_invalid_vif_id(self, task):
        task.ports = [port.Port(**{
            'uuid': '1',
            'extra': {
                'type': 'deploy',
                'vnic_id': 1
            }
        }), port.Port(**{
            'uuid': '1',
            'extra': {
                'type': 'deploy',
                'vif_port_id': None,
                'vnic_id': 1
            }
        })]

        vifs = boot.get_provisioning_vifs(task)
        self.assertEqual({}, vifs)


class PXEBootTestCase(test_common.BaseTestCase):

    @with_task
    def test_validate(self, task):
        result = task.driver.boot.validate(task)
        self.assertIsNone(result)

    @mock.patch.object(deploy_utils, 'try_set_boot_device', autospec=True)
    @mock.patch.object(pxe, '_get_deploy_image_info', autospec=True)
    @mock.patch.object(pxe, '_build_pxe_config_options', autospec=True)
    @mock.patch.object(pxe, '_get_instance_image_info', autospec=True)
    @mock.patch.object(pxe_utils, 'create_pxe_config', autospec=True)
    @mock.patch.object(pxe, '_cache_ramdisk_kernel', autospec=True)
    @mock.patch.object(boot, 'get_provisioning_vifs', autospec=True)
    @mock.patch.object(dhcp_factory.DHCPFactory, 'update_dhcp', autospec=True)
    @mock.patch.object(network.NetworkProvider, 'add_provisioning_network',
                       autospec=True)
    def test_prepare_ramdisk(self, mock_add_pro, mock_dhcp, mock_get_vifs,
                             mock_cache_ramdisk, mock_create_pxe,
                             mock_get_instance, mock_build_pxe,
                             mock_get_deploy, mock_set_boot):
        self.node.provision_state = states.DEPLOYING
        self.node.network_provider = "cimc_network_provider"
        self.node.save()

        vifs = {self.node.uuid: 'vif_uuid'}
        mock_get_vifs.return_value = vifs

        with task_manager.acquire(self.context,
                                  self.node.uuid,
                                  shared=False) as task:
            opts = pxe_utils.dhcp_options_for_instance(task)
            task.driver.boot.prepare_ramdisk(task, {'foo': 'bar'})

            mock_set_boot.assert_called_once_with(task, boot_devices.PXE)
            mock_add_pro.assert_called_once_with(mock.ANY, task)
            mock_get_deploy.assert_called_once_with(task.node)
            mock_build_pxe.assert_called_once_with(
                task, mock_get_deploy.return_value)
            mock_get_instance.assert_called_once_with(task.node, task.context)
            mock_create_pxe.assert_called_once_with(
                task, mock_build_pxe.return_value,
                CONF.pxe.pxe_config_template)
            mock_cache_ramdisk.assert_called_once_with(
                task.context, task.node, mock_get_deploy.return_value)
            mock_dhcp.assert_called_once_with(mock.ANY, task, opts, vifs)

    @mock.patch.object(pxe.PXEBoot, 'prepare_instance', autospec=True)
    @mock.patch.object(network.NetworkProvider, 'remove_provisioning_network',
                       autospec=True)
    @mock.patch.object(network.NetworkProvider, 'configure_tenant_networks',
                       autospec=True)
    @with_task
    def test_prepare_instance(self, task, mock_config, mock_unplug,
                              mock_prepare):
        task.driver.boot.prepare_instance(task)
        mock_prepare.assert_called_once_with(mock.ANY, task)
        self.assertFalse(mock_unplug.called)
        mock_config.assert_called_once_with(mock.ANY, task)

    @mock.patch.object(pxe.PXEBoot, 'prepare_instance', autospec=True)
    @mock.patch.object(network.NetworkProvider, 'remove_provisioning_network',
                       autospec=True)
    @mock.patch.object(network.NetworkProvider, 'configure_tenant_networks',
                       autospec=True)
    @with_task
    def test_prepare_instance_local(self, task, mock_config, mock_unplug,
                                    mock_prepare):
        task.node.instance_info['capabilities'] = {"boot_option": "local"}
        task.driver.boot.prepare_instance(task)
        mock_prepare.assert_called_once_with(mock.ANY, task)
        mock_unplug.assert_called_once_with(mock.ANY, task)
        mock_config.assert_called_once_with(mock.ANY, task)

    @mock.patch.object(pxe.PXEBoot, 'clean_up_ramdisk', autospec=True)
    @mock.patch.object(network.NetworkProvider, 'remove_provisioning_network',
                       autospec=True)
    @mock.patch.object(network.NetworkProvider, 'remove_cleaning_network',
                       autospec=True)
    @with_task
    def test_clean_up_ramdisk(self, task, mock_remove_clean, mock_remove_pro,
                              mock_clean):
        task.driver.boot.clean_up_ramdisk(task)
        mock_clean.assert_called_once_with(mock.ANY, task)
        mock_remove_pro.assert_called_once_with(mock.ANY, task)
        mock_remove_clean.assert_called_once_with(mock.ANY, task)

    @mock.patch.object(pxe.PXEBoot, 'clean_up_instance', autospec=True)
    @mock.patch.object(network.NetworkProvider, 'unconfigure_tenant_networks',
                       autospec=True)
    @with_task
    def test_clean_up_instance(self, task, mock_unconfig, mock_clean):
        task.driver.boot.clean_up_instance(task)
        mock_clean.assert_called_once_with(mock.ANY, task)
        mock_unconfig.assert_called_once_with(mock.ANY, task)
