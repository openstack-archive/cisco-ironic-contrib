#!/bin/bash

CISCO_IRONIC_DIR=$DEST/cisco-ironic-contrib
CISCO_IRONIC_DATA_DIR=${CISCO_IRONIC_DATA_DIR:-}
CISCO_IRONIC_USER_IMAGE_NAME=${CISCO_IRONIC_USER_IMAGE_NAME:-}
CISCO_IRONIC_INSPECT_IMAGE_NAME=${CISCO_IRONIC_INSPECT_IMAGE_NAME:-}
CISCO_IRONIC_DEPLOY_IMAGE_NAME=${CISCO_IRONIC_DEPLOY_IMAGE_NAME:-}
CISCO_IRONIC_ENABLE_VPC=${CISCO_IRONIC_ENABLE_VPC:-True}
CISCO_IRONIC_FLAVOR_SPEC=${CISCO_IRONIC_FLAVOR_SPEC:-}
CISCO_DEPLOY_KERNEL_ID=
CISCO_DEPLOY_RAMDISK_ID=

function create_user_image {
    if [[ -z $CISCO_IRONIC_DATA_DIR || -z $CISCO_IRONIC_USER_IMAGE_NAME ]]; then
        echo_summary "Cisco Ironic Baremetal user image is not defined"
        return
    fi

    local image_path=$CISCO_IRONIC_DATA_DIR/$CISCO_IRONIC_USER_IMAGE_NAME
    local KERNEL_ID=`glance image-create --name ${CISCO_IRONIC_USER_IMAGE_NAME}.kernel  --visibility public --disk-format=aki --container-format=aki --file=${image_path}.vmlinuz | grep id | tr -d '| ' | cut --bytes=3-57`
    local RAMDISK_ID=`glance image-create --name ${CISCO_IRONIC_USER_IMAGE_NAME}.ramdisk --visibility public --disk-format=ari --container-format=ari --file=${image_path}.initrd | grep id |  tr -d '| ' | cut --bytes=3-57`
    glance image-create --name $CISCO_IRONIC_USER_IMAGE_NAME --visibility public --disk-format=qcow2 --container-format=bare --property kernel_id=$KERNEL_ID --property ramdisk_id=$RAMDISK_ID --file=${image_path}.qcow2
}

function create_deploy_images {
    if [[ -z $CISCO_IRONIC_DATA_DIR || -z $CISCO_IRONIC_DEPLOY_IMAGE_NAME ]]; then
        echo_summary "Cisco Ironic Baremetal deploy image is not defined"
        return
    fi
    local image_path=$CISCO_IRONIC_DATA_DIR/$CISCO_IRONIC_DEPLOY_IMAGE_NAME
    CISCO_DEPLOY_KERNEL_ID=`glance image-create --name cisco-deploy.kernel  --visibility public --disk-format=aki --container-format=aki --file=${image_path}.vmlinuz | grep id | tr -d '| ' | cut --bytes=3-57`
    CISCO_DEPLOY_RAMDISK_ID=`glance image-create --name cisco-deploy.ramdisk --visibility public --disk-format=ari --container-format=ari --file=${image_path}.initrd | grep id |  tr -d '| ' | cut --bytes=3-57`
}

function install_inspect_images {
    if [[ -z $CISCO_IRONIC_DATA_DIR || -z $CISCO_IRONIC_INSPECT_IMAGE_NAME ]]; then
        echo_summary "Cisco Ironic Baremetal inspect image is not defined"
        return
    fi
    local image_path=$CISCO_IRONIC_DATA_DIR/$CISCO_IRONIC_INSPECT_IMAGE_NAME
    cp ${image_path}.initrd $IRONIC_TFTPBOOT_DIR/ironic-inspector.initramfs
    cp ${image_path}.vmlinuz $IRONIC_TFTPBOOT_DIR/ironic-inspector.kernel
}

function change_nova_quota {
    local TENANT_NAME=${OS_TENANT_NAME:-demo}
    local USERNAME=${OS_USERNAME:-admin}
    local PROJECT=`openstack project list | grep "| $TENANT_NAME" | awk '{print $2}'`
    local USER=`openstack user list | grep "| $USERNAME" | awk '{print $2}'`
    nova quota-update $PROJECT --instances -1 --cores -1 --ram -1
    nova quota-update $PROJECT --instances -1 --cores -1 --ram -1 --user $USER
}

function create_nodes {
    local hwinfo_file=$CISCO_IRONIC_DATA_DIR/hardware_info
    if [[ ! -f $hwinfo_file ]]; then
        return
    fi

    if [[ -z CISCO_DEPLOY_KERNEL_ID ]]; then
        CISCO_DEPLOY_KERNEL_ID=`nova image-list | grep ir-deploy-agent_ipmitool.kernel | awk '{print $2}'`
    fi
    if [[ -z CISCO_DEPLOY_RAMDISK_ID ]]; then
        CISCO_DEPLOY_RAMDISK_ID=`nova image-list | grep ir-deploy-agent_ipmitool.initramfs | awk '{print $2}'`
    fi

    while read hardware_info; do
        local nodeinfo=($hardware_info)
        local nodeid=$(ironic node-create -d pxe_iscsi_cimc_neutron -i cimc_address=${nodeinfo[0]}\
                                   -i cimc_username=${nodeinfo[1]} -i cimc_password=${nodeinfo[2]}\
                                   -i deploy_kernel=$CISCO_DEPLOY_KERNEL_ID\
                                   -i deploy_ramdisk=$CISCO_DEPLOY_RAMDISK_ID\
                                   -i vPC=$CISCO_IRONIC_ENABLE_VPC\
                                   -p capabilities="boot_option:local"\
                          |grep '| uuid ' | awk '{print $4}')
        ironic node-update $nodeid add network_provider=cimc_network_provider
    done < $hwinfo_file
}

function create_nova_essentials {
    if [[ -n $CISCO_IRONIC_FLAVOR_SPEC ]]; then
        nova flavor-create cisco-ucs auto $CISCO_IRONIC_FLAVOR_SPEC
        nova flavor-key cisco-ucs set cpu_arch=x86_64
        nova flavor-key cisco-ucs set capabilities:boot_option="local"
    fi
    nova keypair-add cisco-ucs > $CISCO_IRONIC_DATA_DIR/cisco-ucs.pem
    sudo chmod 600 $CISCO_IRONIC_DATA_DIR/cisco-ucs.pem
}

function create_nets {
    neutron net-create cisco-ucs-net1
    neutron subnet-create --name cisco-ucs-subnet1 cisco-ucs-net1 20.0.0.0/24

    neutron net-create cisco-ucs-net2
    neutron subnet-create --name cisco-ucs-subnet2 cisco-ucs-net2 30.0.0.0/24
}

function install_cisco_ironic {
    setup_develop $CISCO_IRONIC_DIR
    pip_install ImcSdk
}

function configure_cisco_ironic {
    iniset $NOVA_CONF DEFAULT compute_driver cisco_ironic_contrib.nova.driver.CiscoIronicDriver
    iniset $NOVA_CONF ironic api_max_retries 120
    iniset $NOVA_CONF ironic api_retry_interval 5
}

# check for service enabled
if is_service_enabled cisco-ironic; then
    set -x

    if [[ "$1" == "stack" && "$2" == "pre-install" ]]; then
        # Set up system services
        :
    elif [[ "$1" == "stack" && "$2" == "install" ]]; then
        # Perform installation of service source
        install_cisco_ironic
    elif [[ "$1" == "stack" && "$2" == "post-config" ]]; then
        # Configure after the other layer 1 and 2 services have been configured
        :
        configure_cisco_ironic
    elif [[ "$1" == "stack" && "$2" == "extra" ]]; then
        # Initialize and start the service
        change_nova_quota
        create_nova_essentials
        create_user_image
        create_deploy_images
        install_inspect_images
        create_nets
        create_nodes
    fi

    if [[ "$1" == "unstack" ]]; then
        # Shut down services
        # no-op
        :
    fi

    if [[ "$1" == "clean" ]]; then
        # Remove state and transient data
        # Remember clean.sh first calls unstack.sh
        # no-op
        :
    fi
fi
