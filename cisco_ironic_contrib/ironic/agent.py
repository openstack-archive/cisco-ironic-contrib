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

from ironic.drivers import agent

from cisco_ironic_contrib.ironic.cimc import boot as cimc_boot
from cisco_ironic_contrib.ironic.cimc import vendor as cimc_deploy
from cisco_ironic_contrib.ironic.cimc import vendor as cimc_vendor


class AgentAndCIMCNeutronDriver(agent.AgentAndCIMCDriver):

    def __init__(self):
        super(AgentAndCIMCNeutronDriver, self).__init__()
        self.boot = cimc_boot.PXEBoot()
        self.deploy = cimc_deploy.AgentDeploy()
        self.vendor = cimc_vendor.CIMCPXEVendorPassthru()
