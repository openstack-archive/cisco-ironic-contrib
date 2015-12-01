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

from ironic.common import states
from ironic.conductor import utils as manager_utils
from ironic.drivers.modules import deploy_utils
from ironic.drivers.modules import iscsi_deploy


class ISCSIDeploy(iscsi_deploy.ISCSIDeploy):

    def prepare_cleaning(self, task):
        deploy_utils.agent_add_clean_params(task)
        ramdisk_opts = deploy_utils.build_agent_options(task.node)
        ramdisk_opts.update(
            iscsi_deploy.build_deploy_ramdisk_options(task.node))
        task.driver.boot.prepare_ramdisk(task, ramdisk_opts)
        manager_utils.node_power_action(task, states.REBOOT)
        return states.CLEANWAIT

    def tear_down_cleaning(self, task):
        task.driver.boot.clean_up_ramdisk(task)
        manager_utils.node_power_action(task, states.POWER_OFF)
