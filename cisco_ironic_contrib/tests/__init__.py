# Copyright 2015 Cisco Systems
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

# Ensure nova configs that conflict with ironic configs are unregistered for
# the tests

from oslo_config import cfg

from nova.api import auth
from nova import exception
from nova import netconf
from nova.network.neutronv2 import api
from nova import paths
from nova import utils
from nova.virt import images

CONF = cfg.CONF

CONF.unregister_opts(exception.exc_log_opts)
CONF.unregister_opt(utils.utils_opts[3])
CONF.unregister_opt(utils.utils_opts[4])
CONF.unregister_opt(netconf.netconf_opts[0])
CONF.unregister_opt(netconf.netconf_opts[2])
CONF.unregister_opts(paths.path_opts)
CONF.unregister_opt(auth.auth_opts[1])
CONF.unregister_opts(api.neutron_opts, group='neutron')
CONF.unregister_opts(images.image_opts)
