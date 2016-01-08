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

import collections

from oslo_config import cfg
CONF = cfg.CONF

from oslo_versionedobjects import base


# Patch oslo versioned objects so that the nova object registry does not
# conflict with the ironic one.
@staticmethod
def newnew(cls, *args, **kwargs):
    if not cls._registry:
        if not base.VersionedObjectRegistry._registry:
            base.VersionedObjectRegistry._registry = object.__new__(
                base.VersionedObjectRegistry, *args, **kwargs)
            base.VersionedObjectRegistry._registry._obj_classes = (
                collections.defaultdict(list))
    self = object.__new__(cls, *args, **kwargs)
    self._obj_classes = base.VersionedObjectRegistry._registry._obj_classes
    return self
base.VersionedObjectRegistry.__new__ = newnew

# Ensure nova configs that conflict with ironic configs are unregistered for
# the tests
from nova.api import auth
from nova import exception
from nova import netconf
from nova.network.neutronv2 import api
from nova import paths
from nova import utils
from nova.virt import images

CONF.unregister_opts(exception.exc_log_opts)
CONF.unregister_opt(utils.utils_opts[3])
CONF.unregister_opt(utils.utils_opts[4])
CONF.unregister_opt(netconf.netconf_opts[0])
CONF.unregister_opt(netconf.netconf_opts[2])
CONF.unregister_opts(paths.path_opts)
CONF.unregister_opt(auth.auth_opts[1])
CONF.unregister_opts(api.neutron_opts, group='neutron')
CONF.unregister_opts(images.image_opts)

from ironic_inspector import conf

CONF.unregister_opt(conf.SERVICE_OPTS[2])
CONF.unregister_opt(conf.SERVICE_OPTS[14])
