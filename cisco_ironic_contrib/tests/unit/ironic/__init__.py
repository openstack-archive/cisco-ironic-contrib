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

import six
import sys

from ironic.drivers import fake
from ironic.tests.unit.drivers import third_party_driver_mocks  # noqa

from cisco_ironic_contrib.ironic.cimc import boot
from cisco_ironic_contrib.ironic.cimc import vendor

if 'ironic.drivers.modules.cimc' in sys.modules:
    six.moves.reload_module(
        sys.modules['ironic.drivers.modules.cimc'])

fake.FakeCIMCDriver.boot = boot.PXEBoot()
fake.FakeCIMCDriver.vendor = vendor.CIMCPXEVendorPassthru()
