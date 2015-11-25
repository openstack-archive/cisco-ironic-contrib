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

import os
import shutil

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import importutils

from ironic.common import boot_devices
from ironic.common import dhcp_factory
from ironic.common import network as common_net
from ironic.common import pxe_utils
from ironic.common import states
from ironic.drivers.modules import deploy_utils
from ironic.drivers.modules import pxe
from ironic import objects

imcsdk = importutils.try_import('ImcSdk')

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def get_provisioning_vifs(task):
    port_vifs = {}
    for port in task.ports:
        if port.extra['type'] != "deploy":
            continue
        vif = port.extra.get('vif_port_id')
        if vif:
            port_vifs[port.uuid] = vif
    return port_vifs


def get_cleaning_vifs(task):
    port_vifs = {}
    for port in task.ports:
        if port.extra['type'] != "clean":
            continue
        vif = port.extra.get('vif_port_id')
        if vif:
            port_vifs[port.uuid] = vif
    return port_vifs


class PXEBoot(pxe.PXEBoot):

    def validate(self, task):
        pass

    def prepare_ramdisk(self, task, ramdisk_params):
        node = task.node

        # TODO(deva): optimize this if rerun on existing files
        if CONF.pxe.ipxe_enabled:
            # Copy the iPXE boot script to HTTP root directory
            bootfile_path = os.path.join(
                CONF.deploy.http_root,
                os.path.basename(CONF.pxe.ipxe_boot_script))
            shutil.copyfile(CONF.pxe.ipxe_boot_script, bootfile_path)

        net_provider = common_net.get_network_provider(task)
        dhcp_opts = pxe_utils.dhcp_options_for_instance(task)
        provider = dhcp_factory.DHCPFactory()

        if node.provision_state == states.CLEANING:
            net_provider.add_cleaning_network(task)
            vifs = get_cleaning_vifs(task)
        else:
            net_provider.add_provisioning_network(task)
            vifs = get_provisioning_vifs(task)

        provider.update_dhcp(task, dhcp_opts, vifs)

        pxe_info = pxe._get_deploy_image_info(node)

        # NODE: Try to validate and fetch instance images only
        # if we are in DEPLOYING state.
        if node.provision_state == states.DEPLOYING:
            pxe_info.update(pxe._get_instance_image_info(node, task.context))

        pxe_options = pxe._build_pxe_config_options(task, pxe_info)
        pxe_options.update(ramdisk_params)

        if deploy_utils.get_boot_mode_for_deploy(node) == 'uefi':
            pxe_config_template = CONF.pxe.uefi_pxe_config_template
        else:
            pxe_config_template = CONF.pxe.pxe_config_template

        pxe_utils.create_pxe_config(task, pxe_options,
                                    pxe_config_template)
        deploy_utils.try_set_boot_device(task, boot_devices.PXE)

        # FIXME(lucasagomes): If it's local boot we should not cache
        # the image kernel and ramdisk (Or even require it).
        pxe._cache_ramdisk_kernel(task.context, node, pxe_info)

    def prepare_instance(self, task):
        super(PXEBoot, self).prepare_instance(task)
        net_provider = common_net.get_network_provider(task)
        if deploy_utils.get_boot_option(task.node) == "local":
            net_provider.remove_provisioning_network(task)
        net_provider.configure_tenant_networks(task)

    def clean_up_ramdisk(self, task):
        super(PXEBoot, self).clean_up_ramdisk(task)
        common_net.get_network_provider(task).remove_provisioning_network(task)
        common_net.get_network_provider(task).remove_cleaning_network(task)
        task.ports = objects.Port.list_by_node_id(task.context, task.node.id)

    def clean_up_instance(self, task):
        super(PXEBoot, self).clean_up_instance(task)
        common_net.get_network_provider(task).unconfigure_tenant_networks(task)
        task.ports = objects.Port.list_by_node_id(task.context, task.node.id)
