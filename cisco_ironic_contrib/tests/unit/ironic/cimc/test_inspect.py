# Copyright 2016, Cisco Systems.
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
import mock

from oslo_config import cfg

from ironic.common import exception
from ironic.common import network as common_net
from ironic.common import states
from ironic.conductor import task_manager
from ironic.conductor import utils as manager_utils
from ironic.drivers.modules.cimc import common as cimc_common
from ironic.drivers.modules import inspector

from cisco_ironic_contrib.ironic.cimc import common
from cisco_ironic_contrib.ironic.cimc import inspect
from cisco_ironic_contrib.tests.unit.ironic.cimc import test_common

CONF = cfg.CONF


def with_task(func):

    def wrapper(self, *args, **kwargs):
        with task_manager.acquire(self.context,
                                  self.node.uuid,
                                  shared=False) as task:
            return func(self, task, *args, **kwargs)

    return wrapper


class CIMCAndInspectorInspectTestCase(test_common.BaseTestCase):

    def setUp(self):
        super(CIMCAndInspectorInspectTestCase, self).setUp()
        driver_info = dict(self.node.driver_info)
        del driver_info['uplink0-mac']
        del driver_info['uplink0-local-link']
        del driver_info['uplink1-mac']
        del driver_info['uplink1-local-link']
        del driver_info['uplinks']
        self.node.driver_info = driver_info
        self.node.save()

    def test_get_properties(self):
        pass

    @with_task
    def test_validate(self, task):
        inst = inspect.CIMCAndInspectorInspect()
        inst.validate(task)

    @with_task
    def test_validate_fail(self, task):
        del task.node.driver_info['cimc_password']
        inst = inspect.CIMCAndInspectorInspect()
        self.assertRaises(exception.MissingParameterValue, inst.validate, task)

    @mock.patch.object(inspector, '_start_inspection', autospec=True)
    @mock.patch.object(common, 'add_vnic', autospec=True)
    @mock.patch.object(eventlet, 'spawn_n', lambda f, *a, **kw: f(*a, **kw))
    @mock.patch.object(common_net, 'get_neutron_client', autospec=True)
    @mock.patch.object(manager_utils, 'node_power_action', autospec=True)
    @mock.patch.object(cimc_common, 'cimc_handle', autospec=True)
    @with_task
    def test_inspect_hardware(self, task, mock_handle, mock_power_action,
                              mock_neutron, mock_vnic, mock_insp):
        mock_neutron.return_value.show_network.return_value = {
            'network': {
                'provider:segmentation_id': 600
            }
        }

        uplink0 = mock.MagicMock()
        uplink0.PortId = 0
        uplink0.Mac = '61:99:D5:A3:FB:F2'

        uplink1 = mock.MagicMock()
        uplink1.PortId = 1
        uplink1.Mac = '61:99:D5:A4:FB:F2'

        nic0 = mock.MagicMock()
        nic0.Mac = '61:99:D5:A3:FB:F3'

        nic1 = mock.MagicMock()
        nic1.Mac = '61:99:D5:A4:FB:F3'

        with mock_handle(task) as handle:
            handle.get_imc_managedobject.side_effect = [
                mock.MagicMock(),
                [mock.MagicMock()],
                [uplink0, uplink1],
                nic0,
                nic1
            ]

        task.node.provision_state = states.INSPECTING
        task.node.save()

        inst = inspect.CIMCAndInspectorInspect()
        self.assertEqual(states.INSPECTING, inst.inspect_hardware(task))

        mock_power_action.assert_called_once_with(task, states.REBOOT)
        self.assertEqual(task.node.driver_info['uplinks'], 2)
        self.assertEqual(task.node.driver_info['uplink0-mac'], uplink0.Mac)
        self.assertEqual(task.node.driver_info['uplink1-mac'], uplink1.Mac)

        calls = [
            mock.call(task, 0, nic0.Mac, 600, pxe=True),
            mock.call(task, 1, nic1.Mac, 600, pxe=True)
        ]
        mock_vnic.assert_has_calls(calls)

        self.assertEqual(2, len(task.ports))

        mock_insp.assert_called_once_with(task.node.uuid, task.context)

    def test__check_inspection_progress(self):
        pass
