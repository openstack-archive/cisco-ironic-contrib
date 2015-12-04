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

from oslo_log import log as logging
from oslo_utils import importutils

from ironic.common import exception

from ironic.drivers.modules.cimc import common
from ironic.drivers.modules import deploy_utils

imcsdk = importutils.try_import('ImcSdk')

LOG = logging.getLogger(__name__)

REQUIRED_PROPERTIES = {
    'uplinks': _('Uplinks availible on this node'),
}

COMMON_PROPERTIES = {
    'vPC': _('Is vPC enabled for this Node'),
}
COMMON_PROPERTIES.update(REQUIRED_PROPERTIES)


def parse_driver_info(node):
    info = common.parse_driver_info(node)
    error_msg = (_("%s driver requires these parameters to be set in the "
                   "node's driver_info.") %
                 node.driver)

    for param in REQUIRED_PROPERTIES:
        info[param] = node.driver_info.get(param)
    deploy_utils.check_for_missing_params(info, error_msg)

    for link in range(0, info['uplinks']):
        mac = 'uplink%d-mac' % link
        info[mac] = node.driver_info.get(mac)
    deploy_utils.check_for_missing_params(info, error_msg)

    for param in COMMON_PROPERTIES:
        prop = node.driver_info.get(param)
        if prop:
            info[param] = prop
    return info


def add_vnic(task, vnic_id, mac, vlan, pxe=False, uplink=None):
    info = parse_driver_info(task.node)
    name = "eth%d" % vnic_id
    uplink = uplink if uplink else vnic_id % info['uplinks']
    with common.cimc_handle(task) as handle:
        rackunit = handle.get_imc_managedobject(
            None, imcsdk.ComputeRackUnit.class_id())
        adaptorunits = handle.get_imc_managedobject(
            in_mo=rackunit, class_id=imcsdk.AdaptorUnit.class_id())

        dn = "%s/host-eth-%s" % (adaptorunits[0].Dn, name)

        method = imcsdk.ImcCore.ExternalMethod("ConfigConfMo")
        method.Cookie = handle.cookie
        method.Dn = dn

        config = imcsdk.Imc.ConfigConfig()

        newVic = imcsdk.ImcCore.ManagedObject("adaptorHostEthIf")
        newVic.set_attr("name", name)
        newVic.set_attr("mtu", "1500")
        newVic.set_attr("pxeBoot", "enabled" if pxe else "disabled")
        newVic.set_attr("Dn", dn)
        newVic.set_attr("mac", mac if mac else "AUTO")
        newVic.set_attr("uplinkPort", str(uplink))

        vlanProfile = imcsdk.ImcCore.ManagedObject("adaptorEthGenProfile")
        vlanProfile.set_attr("vlanMode", "ACCESS")
        vlanProfile.set_attr("vlan", str(vlan) if vlan else "NONE")
        vlanProfile.set_attr("Dn", dn)

        newVic.add_child(vlanProfile)
        config.add_child(newVic)
        method.InConfig = config

        resp = handle.xml_query(
            method, imcsdk.WriteXmlOption.DIRTY)
        error = getattr(resp, 'error_code', None)
        if error:
            raise exception.CIMCException(node=task.node.uuid, error=error)
        if not mac:
            return resp.OutConfig._child[0].Mac


def delete_vnic(task, vnic_id):
    info = parse_driver_info(task.node)
    if vnic_id < info['uplinks']:
        clean_vnic(task, vnic_id)
    else:
        name = "eth%d" % vnic_id
        with common.cimc_handle(task) as handle:
            rackunit = handle.get_imc_managedobject(
                None, imcsdk.ComputeRackUnit.class_id())
            adaptorunits = handle.get_imc_managedobject(
                in_mo=rackunit, class_id=imcsdk.AdaptorUnit.class_id())
            vic = {
                "Dn": "%s/host-eth-%s" % (adaptorunits[0].Dn, name),
            }
            handle.remove_imc_managedobject(
                None, class_id="adaptorHostEthIf", params=vic)


def clean_vnic(task, vnic_id):
    add_vnic(task, vnic_id, None, None)
