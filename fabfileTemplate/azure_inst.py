#
#    ICRAR - International Centre for Radio Astronomy Research
#    (c) UWA - The University of Western Australia, 2016
#    Copyright by UWA (in the framework of the ICRAR)
#    All rights reserved
#
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation; either
#    version 2.1 of the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this library; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston,
#    MA 02111-1307  USA
#
"""
Module containing AWS-related methods and tasks
"""

import os
import time

from fabric.colors import green, red, blue, yellow
from fabric.contrib.console import confirm
from fabric.decorators import task
from fabric.state import env
from fabric.tasks import execute
from fabric.utils import puts, abort, fastprint

from APPspecific import APP_revision, APP_user, APP_name
from utils import default_if_empty, whatsmyip, check_ssh, \
    key_filename

# Don't re-export the tasks imported from other modules
__all__ = ['create_vm_instances', 'list_instances', 'terminate']

# Available known AMI IDs
AMI_IDs = {
           'Amazon': 'ami-6178a31e',
           'Amazon-hvm': 'ami-5679a229',
           'CentOS': 'ami-8997afe0',
           'Old_CentOS': 'ami-aecd60c7',
           'SLES-SP2': 'ami-e8084981',
           'SLES-SP3': 'ami-c08fcba8'
           }

# Instance creation defaults
DEFAULT_AWS_AMI_NAME = 'Amazon'
DEFAULT_INSTANCES = 1
DEFAULT_INSTANCE_NAME_TPL = '{0}'.format(APP_name()+'_{0}')  # gets formatted with the git branch name
DEFAULT_INSTANCE_TYPE = 't1.micro'
DEFAULT_KEY_NAME = 'icrar_ngas'
DEFAULT_GROUP = APP_name()  # Security group allows SSH and other ports

# Connection defaults
DEFAULT_REGION = 'australiacentral'


def getClients():
    # This requires
    # pip install azure-common azure-mgmt-compute azure-mgmt-resource azure-mgmt-network
    #
    from azure.common.client_factory import get_client_from_cli_profile
    from azure.mgmt.network import NetworkManagementClient
    from azure.mgmt.resource import ResourceManagementClient
    from azure.mgmt.compute import ComputeManagementClient

    network_client = get_client_from_cli_profile(NetworkManagementClient)
    resource_client = get_client_from_cli_profile(ResourceManagementClient)
    compute_client = get_client_from_cli_profile(ComputeManagementClient)
    return (network_client, resource_client, compute_client)


def userAtHost():
    return os.environ['USER'] + '@' + whatsmyip()


def create_resource_group(resource_group_client):
    resource_group_params = {'location': DEFAULT_REGION}
    resource_group_result =\
        resource_group_client.resource_groups.create_or_update(
            DEFAULT_GROUP,
            resource_group_params)


def create_availability_set(compute_client):
    avset_params = {
        'location': DEFAULT_REGION,
        'sku': {'name': 'Aligned'},
        'platform_fault_domain_count': 3
    }
    availability_set_result =\
        compute_client.availability_sets.create_or_update(
            DEFAULT_GROUP,
            'myAVSet',
            avset_params)


def create_public_ip_address(network_client):
    public_ip_addess_params = {
        'location': DEFAULT_REGION,
        'public_ip_allocation_method': 'Dynamic'
    }
    creation_result = network_client.public_ip_addresses.create_or_update(
        DEFAULT_GROUP,
        'myIPAddress',
        public_ip_addess_params
    )

    return creation_result.result()


def create_vnet(network_client):
    vnet_params = {
        'location': DEFAULT_REGION,
        'address_space': {
            'address_prefixes': ['10.0.0.0/16']
        }
    }
    creation_result = network_client.virtual_networks.create_or_update(
        DEFAULT_GROUP,
        'myVNet',
        vnet_params
    )
    return creation_result.result()


def create_subnet(network_client):
    subnet_params = {
        'address_prefix': '10.0.0.0/24'
    }
    creation_result = network_client.subnets.create_or_update(
        DEFAULT_GROUP,
        'myVNet',
        'mySubnet',
        subnet_params
    )

    return creation_result.result()


def create_nic(network_client):
    subnet_info = network_client.subnets.get(
        DEFAULT_GROUP,
        'myVNet',
        'mySubnet'
    )
    publicIPAddress = network_client.public_ip_addresses.get(
        DEFAULT_GROUP,
        'myIPAddress'
    )
    nic_params = {
        'location': DEFAULT_REGION,
        'ip_configurations': [{
            'name': 'myIPConfig',
            'public_ip_address': publicIPAddress,
            'subnet': {
                'id': subnet_info.id
            }
        }]
    }
    creation_result = network_client.network_interfaces.create_or_update(
        DEFAULT_GROUP,
        'myNic',
        nic_params
    )
    return creation_result.result()


def create_vm(network_client, compute_client):
    nic = network_client.network_interfaces.get(
        DEFAULT_GROUP,
        'myNic'
    )
    avset = compute_client.availability_sets.get(
        DEFAULT_GROUP,
        'myAVSet'
    )
    vm_parameters = {
        'location': DEFAULT_REGION,
        'os_profile': {
            'computer_name': DEFAULT_INSTANCE_NAME_TPL,
            'admin_username': 'azureuser',
            'admin_password': 'Azure12345678'
        },
        'hardware_profile': {
            'vm_size': 'Standard_DS1'
        },
        'storage_profile': {
            'image_reference': {
                'publisher': 'OpenLogic',
                'offer': 'CentOS',
                'sku': '7.3',
                'version': 'latest'
            }
        },
        'network_profile': {
            'network_interfaces': [{
                'id': nic.id
            }]
        },
        'availability_set': {
            'id': avset.id
        }
    }
    creation_result = compute_client.virtual_machines.create_or_update(
        DEFAULT_GROUP,
        DEFAULT_INSTANCE_NAME_TPL,
        vm_parameters
    )

    return creation_result.result()
