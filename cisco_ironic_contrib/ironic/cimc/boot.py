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
from ironic.common import pxe_utils
from ironic.common import states
from ironic.dhcp import neutron
from ironic.drivers.modules import deploy_utils
from ironic.drivers.modules import pxe
from ironic import objects

from cisco_ironic_contrib.ironic.cimc import common

imcsdk = importutils.try_import('ImcSdk')

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class PXEBoot(pxe.PXEBoot):

    def _plug_provisioning(self, task, **kwargs):
        LOG.debug("Plugging the provisioning!")

        client = neutron._build_client(task.context.auth_token)
        port = client.create_port({
            'port': {
                "network_id":
                    CONF.neutron.cleaning_network_uuid,
                "extra_dhcp_opts":
                    pxe_utils.dhcp_options_for_instance(task),
            }
        })

        name = port['port']['id']
        network = client.show_network(port['port']['network_id'])
        seg_id = network['network']['provider:segmentation_id']

        try:
            common.add_vnic(
                task, name, port['port']['mac_address'], seg_id, True)
        except imcsdk.ImcException:
            client.delete_port(name)
            raise

        new_port = objects.Port(
            task.context, node_id=task.node.id,
            address=port['port']['mac_address'],
            extra={"vif_port_id": port['port']['id'],
                   "type": "deploy", "state": "ACTIVE"})
        new_port.create()
        return port['port']['fixed_ips'][0]['ip_address']

    def _unplug_provisioning(self, task, **kwargs):
        LOG.debug("Unplugging the provisioning!")
        client = neutron._build_client(task.context.auth_token)

        ports = objects.Port.list_by_node_id(task.context, task.node.id)
        for port in ports:
            if port['extra'].get('type') == "deploy":
                common.delete_vnic(task, port['extra']['vif_port_id'])
                client.delete_port(port['extra']['vif_port_id'])
                port.destroy()

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

        prov_ip = self._plug_provisioning(task)

        task.ports = objects.Port.list_by_node_id(task.context, node.id)

        pxe_info = pxe._get_deploy_image_info(node)

        # NODE: Try to validate and fetch instance images only
        # if we are in DEPLOYING state.
        if node.provision_state == states.DEPLOYING:
            pxe_info.update(pxe._get_instance_image_info(node, task.context))

        pxe_options = pxe._build_pxe_config_options(task, pxe_info)
        pxe_options.update(ramdisk_params)
        pxe_options['advertise_host'] = prov_ip

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
        if deploy_utils.get_boot_option(task.node) == "local":
            self._unplug_provisioning(task)

    def clean_up_ramdisk(self, task):
        super(PXEBoot, self).clean_up_ramdisk(task)
        self._unplug_provisioning(task)
