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

from ironic.common import network as common_net
from ironic.common import states
from ironic.conductor import task_manager
from ironic.conductor import utils as manager_utils
from ironic import objects

from cisco_ironic_contrib.ironic.cimc import common
from cisco_ironic_contrib.ironic.cimc import network
from cisco_ironic_contrib.tests.unit.ironic.cimc import test_common

CONF = cfg.CONF


def with_task(func):

    def wrapper(self, *args, **kwargs):
        with task_manager.acquire(self.context,
                                  self.node.uuid,
                                  shared=False) as task:
            return func(self, task, *args, **kwargs)

    return wrapper


class PXEBootTestCase(test_common.BaseTestCase):

    @mock.patch.object(manager_utils, 'node_power_action', autospec=True)
    @mock.patch.object(objects, 'Port', autospec=True)
    @mock.patch.object(common, 'add_vnic', autospec=True)
    @mock.patch.object(common_net, 'get_neutron_client', autospec=True)
    @with_task
    def test_add_provisioning_network(self, task, mock__build_client,
                                      mock_add_vnic, mock_port, mock_power):
        client = mock__build_client.return_value
        client.create_port.return_value = {
            'port': {
                'id': 'fake_id',
                'network_id': CONF.neutron.cleaning_network_uuid,
                'mac_address': 'fake_address',
                'fixed_ips': [
                    {'ip_address': "1.2.3.4"}
                ],
            }
        }

        client.show_network.return_value = {
            'network': {
                'provider:segmentation_id': 600
            }
        }

        provider = network.NetworkProvider()
        provider.add_provisioning_network(task)

        neutron_data = {
            'port': {
                "network_id": CONF.neutron.cleaning_network_uuid,
                'admin_state_up': True,
                'binding:vnic_type': 'baremetal',
                'device_owner': 'baremetal:none',
                'binding:host_id': task.node.uuid,
                'binding:profile': {
                    'local_link_information': [
                        task.node.driver_info['uplink0-local-link']],
                }
            }
        }

        mock_power.assert_called_once_with(task, states.REBOOT)
        client.create_port.assert_called_once_with(neutron_data)
        client.show_network.assert_called_once_with(
            CONF.neutron.cleaning_network_uuid)
        mock_add_vnic.assert_called_once_with(
            task, 0, 'fake_address', 600, True)
        mock_port.assert_called_once_with(task.context, node_id=task.node.id,
                                          address='fake_address',
                                          pxe_enabled=True,
                                          extra={
                                              "vif_port_id": 'fake_id',
                                              "type": "deploy",
                                              "state": "UP",
                                              "vnic_id": 0})
        mock_port.return_value.create.assert_called_once_with()

    @mock.patch.object(manager_utils, 'node_power_action', autospec=True)
    @mock.patch.object(objects, 'Port', autospec=True)
    @mock.patch.object(common_net, 'get_neutron_client', autospec=True)
    @mock.patch.object(common, 'delete_vnic', autospec=True)
    @with_task
    def test_remove_provisioning_network(self, task, mock_delete_vnic,
                                         mock__build_client, mock_port,
                                         mock_power):

        portMock1 = mock.MagicMock()
        portMock1.__getitem__.return_value = {
            'type': 'tenant',
            'vif_port_id': 'port1',
            'vnic_id': 0
        }

        portMock2 = mock.MagicMock()
        portMock2.__getitem__.return_value = {
            'type': 'deploy',
            'vif_port_id': 'port2',
            'vnic_id': 1
        }

        portMock3 = mock.MagicMock()
        portMock3.__getitem__.return_value = {
            'type': 'tenant',
            'vif_port_id': 'port3',
            'vnic_id': 2
        }

        mock_port.list_by_node_id.return_value = [portMock1,
                                                  portMock2,
                                                  portMock3]

        client = mock__build_client.return_value

        provider = network.NetworkProvider()
        provider.remove_provisioning_network(task)

        mock_power.assert_called_once_with(task, states.REBOOT)
        mock_delete_vnic.assert_called_once_with(task, 1)
        client.delete_port.assert_called_once_with('port2')
        portMock2.destroy.assert_called_once_with()

    @mock.patch.object(common_net, 'get_neutron_client', autospec=True)
    @mock.patch.object(common, 'add_vnic', autospec=True)
    @mock.patch.object(objects, 'Port', autospec=True)
    @with_task
    def test_configure_tenant_networks(self, task, mock_port, mock_add,
                                       mock_get):
        port1 = {
            'address': "95:AC:4A:B6:E3:E1",
            'pxe_enabled': False,
            'portgroup_id': None,
            'extra': {
                'vif_port_id': 'port1',
                'type': 'deploy',
                'seg_id': 600,
                'state': "DOWN"
            }
        }
        portMock1 = mock.MagicMock()
        portMock1.__getitem__.side_effect = lambda item: port1[item]
        portMock1.get.side_effect = lambda item: port1.get(item)

        port2 = {
            'address': "95:AC:4A:B6:E3:E2",
            'pxe_enabled': False,
            'portgroup_id': None,
            'extra': {
                'vif_port_id': 'port2',
                'type': 'tenant',
                'seg_id': 601,
                'state': "DOWN"
            }
        }
        portMock2 = mock.MagicMock()
        portMock2.__getitem__.side_effect = lambda item: port2[item]
        portMock2.get.side_effect = lambda item: port2.get(item)

        port3 = {
            'address': "95:AC:4A:B6:E3:E3",
            'pxe_enabled': False,
            'portgroup_id': None,
            'extra': {
                'vif_port_id': 'port3',
                'type': 'tenant',
                'seg_id': 602,
                'state': "DOWN"
            }
        }
        portMock3 = mock.MagicMock()
        portMock3.__getitem__.side_effect = lambda item: port3[item]
        portMock3.get.side_effect = lambda item: port3.get(item)

        mock_port.list_by_node_id.return_value = [portMock1,
                                                  portMock2,
                                                  portMock3]

        provider = network.NetworkProvider()
        provider.configure_tenant_networks(task)

        calls = [
            mock.call(task, 0, "95:AC:4A:B6:E3:E2", 601, pxe=False),
            mock.call(task, 1, "95:AC:4A:B6:E3:E3", 602, pxe=False)
        ]
        mock_add.assert_has_calls(calls)

        calls = [
            mock.call(port2['extra']['vif_port_id'], {
                'port': {
                    'admin_state_up': True,
                    'binding:vnic_type': 'baremetal',
                    'device_owner': 'baremetal:none',
                    'binding:host_id': task.node.uuid,
                    'binding:profile': {
                        'local_link_information': [
                            task.node.driver_info['uplink0-local-link']],
                    }
                }
            }),
            mock.call(port3['extra']['vif_port_id'], {
                'port': {
                    'admin_state_up': True,
                    'binding:vnic_type': 'baremetal',
                    'device_owner': 'baremetal:none',
                    'binding:host_id': task.node.uuid,
                    'binding:profile': {
                        'local_link_information': [
                            task.node.driver_info['uplink1-local-link']],
                    }
                }
            }),
        ]
        mock_get.return_value.update_port.assert_has_calls(calls)

    @mock.patch.object(common_net, 'get_neutron_client', autospec=True)
    @mock.patch.object(objects.Portgroup, 'get')
    @mock.patch.object(objects.Portgroup, 'list_by_node_id')
    @mock.patch.object(common, 'add_vnic', autospec=True)
    @mock.patch.object(objects.Port, 'list_by_portgroup_id')
    @mock.patch.object(objects.Port, 'list_by_node_id')
    @mock.patch.object(objects.Port, 'get')
    @mock.patch.object(objects.Port, 'save')
    @with_task
    def test_configure_tenant_networks_vpc(self, task, mock_p_save, mock_p_get,
                                           mock_p_list, mock_p_list_pg,
                                           mock_add, mock_pg_list, mock_pg_get,
                                           mock_neutron):
        pg1 = objects.Portgroup(**{
            'id': 1,
            'address': '33:C2:33:52:E0:8E',
            'extra': {
                'vif_port_id': 'vif1',
                'mode': 4
            }
        })

        pg2 = objects.Portgroup(**{
            'id': 2,
            'address': '95:AC:4A:B6:E3:E0',
            'extra': {
                'vif_port_id': 'vif2',
                'mode': 0
            }
        })

        mock_pg_get.side_effect = lambda con, n: pg1 if n == 1 else pg2
        mock_pg_list.return_value = [pg1, pg2]

        port1 = objects.Port(**{
            'address': "95:ac:4a:b6:e3:e1",
            'pxe_enabled': False,
            'portgroup_id': None,
            'extra': {
                'type': 'deploy',
                'seg_id': 600,
                'state': "DOWN"
            }
        })

        port2 = objects.Port(**{
            'address': "95:ac:4a:b6:e3:e2",
            'pxe_enabled': False,
            'portgroup_id': 1,
            'extra': {
                'type': 'tenant',
                'seg_id': 601,
                'state': "DOWN"
            }
        })

        port3 = objects.Port(**{
            'address': "95:ac:4a:b6:e3:e3",
            'pxe_enabled': False,
            'portgroup_id': 1,
            'extra': {
                'type': 'tenant',
                'seg_id': 601,
                'state': "DOWN"
            }
        })

        port4 = objects.Port(**{
            'address': "95:ac:4a:b6:e3:e2",
            'pxe_enabled': False,
            'portgroup_id': 2,
            'extra': {
                'type': 'tenant',
                'seg_id': 602,
                'state': "DOWN"
            }
        })

        port5 = objects.Port(**{
            'address': "95:ac:4a:b6:e3:e3",
            'pxe_enabled': False,
            'portgroup_id': 2,
            'extra': {
                'type': 'tenant',
                'seg_id': 602,
                'state': "DOWN"
            }
        })

        ports = [port1, port2, port3,
                 port4, port5]

        mock_p_list.return_value = ports
        mock_p_get.side_effect = lambda con, n: ports[n]
        mock_p_list_pg.side_effect = lambda con, n: [p for p in ports
                                                     if p.portgroup_id == n]

        provider = network.NetworkProvider()
        provider.configure_tenant_networks(task)

        calls = [
            mock.call(task, 0, "95:ac:4a:b6:e3:e2", None, pxe=False),
            mock.call(task, 1, "95:ac:4a:b6:e3:e3", None, pxe=False),
            mock.call(task, 2, "95:ac:4a:b6:e3:e2", 602, pxe=False),
            mock.call(task, 3, "95:ac:4a:b6:e3:e3", 602, pxe=False),
        ]
        mock_add.assert_has_calls(calls)

        calls = [
            mock.call(pg1.extra['vif_port_id'], {
                'port': {
                    'admin_state_up': True,
                    'binding:vnic_type': 'baremetal',
                    'device_owner': 'baremetal:none',
                    'binding:host_id': task.node.uuid,
                    'binding:profile': {
                        'local_link_information': [
                            task.node.driver_info['uplink0-local-link'],
                            task.node.driver_info['uplink1-local-link'],
                        ]
                    }
                }
            }),
            mock.call(pg2.extra['vif_port_id'], {
                'port': {
                    'admin_state_up': True,
                    'binding:vnic_type': 'baremetal',
                    'device_owner': 'baremetal:none',
                    'binding:host_id': task.node.uuid,
                    'binding:profile': {
                        'local_link_information': [
                            task.node.driver_info['uplink0-local-link'],
                            task.node.driver_info['uplink1-local-link'],
                        ]
                    }
                }
            }),
        ]
        mock_neutron.return_value.update_port.assert_has_calls(calls)

    def test_unconfigure_tenant_networks(self):
        pass

    def test_add_cleaning_network(self):
        pass

    def test_remove_cleaning_network(self):
        pass
