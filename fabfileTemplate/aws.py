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
import six
from sys import version_info

from fabric.colors import green, red, blue, yellow
from fabric.contrib.console import confirm
from fabric.decorators import task
from fabric.state import env
from fabric.tasks import execute
from fabric.utils import puts, abort, fastprint

from fabfileTemplate.APPcommon import APP_revision, APP_user, APP_name
from fabfileTemplate.utils import default_if_empty, whatsmyip, check_ssh, key_filename

import boto3

# Don't re-export the tasks imported from other modules
__all__ = ['create_aws_instances', 'list_instances', 'terminate', 'acheck_ssh']

# Available known AMI IDs
AMI_INFO = {
           'Amazon': {'id':'ami-0dbc3d7bc646e8516', 'root':'ec2-user'},
           'Amazon-hvm': {'id':'ami-0ff8a91507f77f867', 'root':'ec2-user'},
           'CentOS': {'id':'ami-8997afe0', 'root':'root'},
           'Debian': {'id':'ami-0bd9223868b4778d7', 'root':'admin'},
           'SLES-SP2': {'id':'ami-e8084981', 'root':'root'},
           'SLES-SP3': {'id':'ami-c08fcba8', 'root':'root'}
           }

# Instance creation defaults
DEFAULT_AWS_AMI_NAME = 'Amazon'
DEFAULT_AWS_INSTANCES = 1
DEFAULT_AWS_INSTANCE_NAME_TPL = '{0}'.format(APP_name()+'_{0}') # gets formatted with the git branch name
DEFAULT_AWS_INSTANCE_TYPE = 't1.micro'
DEFAULT_AWS_KEY_NAME = 'icrar_ngas'
DEFAULT_AWS_SEC_GROUP = 'NGAS' # Security group allows SSH and other ports
DEFAULT_AWS_SEC_GROUP_PORTS = [22, 80, 7777, 8888]

# Connection defaults
DEFAULT_AWS_PROFILE = 'NGAS'  # the default user profile to use
DEFAULT_AWS_REGION = 'us-east-1'  # The default region
DEFAULT_AWS_VPC_ID = 'vpc-0e2d88e4476b37393'  # The default developer VPC in region above
DEFAULT_AWS_SUBNET_ID = 'subnet-0bc37d21234d81577'  # The default subnet ID
# NOTE: Both the VPC and the subnet have been created manually

default_if_empty(env, 'AWS_VPC_ID', DEFAULT_AWS_VPC_ID)
default_if_empty(env, 'AWS_SUBNET_ID', DEFAULT_AWS_SUBNET_ID)


def connect():
    import boto3

    default_if_empty(env, 'AWS_PROFILE', DEFAULT_AWS_PROFILE)
    default_if_empty(env, 'AWS_REGION',  DEFAULT_AWS_REGION)
#    default_if_empty(env, 'AWS_SERVER_PUBLIC_KEY', DEFAULT_ACCESS_KEY)
#    default_if_empty(env, 'AWS_SERVER_SECRET_KEY', DEFAULT_SECRET_KEY)
    session = boto3.Session()
    boto_client = boto3.setup_default_session(
            profile_name=env.AWS_PROFILE,
            region_name=env.AWS_REGION,
#            aws_access_key_id=env.AWS_SERVER_PUBLIC_KEY,
#            aws_secret_access_key=env.AWS_SERVER_SECRET_KEY
                )
    conn = boto3.client('ec2')
    # conn = boto3.vpc.connect_to_region(env.AWS_REGION, profile_name=env.AWS_PROFILE)
    # default_if_empty(env, 'AWS_KEY', conn.access_key)
    # default_if_empty(env, 'AWS_SECRET', conn.secret_key)

    return conn

def userAtHost():
    return os.environ['USER'] + '@' + whatsmyip()

def aws_create_key_pair(conn):

    key_name = env.AWS_KEY_NAME
    key_file = key_filename(key_name)

    # key does not exist on AWS, create it there and bring it back,
    # overwriting anything we have
    kps = conn.describe_key_pairs(KeyNames=[key_name])
    if not kps:
        kp = conn.create_key_pair(KeyName=key_name)
        if os.path.exists(key_file):
            os.unlink(key_file)

        # We don't have the private key locally, save it
        if not os.path.exists(key_file):
            if version_info[0] > 2:  # workaround for bug in boto for Python3
                kp.material = kp.material.encode()
            kp.save('~/.ssh/')
            return
    if not os.path.exists(key_file):
        raise FileNotFoundError('Key file {0} not found locally'. format(key_file))


def check_create_aws_sec_group(conn):
    """
    Check whether the security group exists
    """
    import boto3.exceptions

    default_if_empty(env, 'AWS_SEC_GROUP', DEFAULT_AWS_SEC_GROUP)
    default_if_empty(env, 'AWS_SEC_GROUP_PORTS', DEFAULT_AWS_SEC_GROUP_PORTS)

    app_secgroup = env.AWS_SEC_GROUP
    sec = conn.describe_security_groups(Filters=[{'Name':'group-name','Values':[env.AWS_SEC_GROUP]}])
    conn.close()
    exfl = False
    if sec['SecurityGroups']:
        appsg = sec['SecurityGroups'][0]
        puts(green("AWS Security Group {0} exists ({1})".format(app_secgroup, appsg['GroupId'])))
    else:
        # Not found, create a new one
        appsg = conn.create_security_group(app_secgroup, '{0} default permissions'.format(APP_name()),
        vpc_id=env.AWS_VPC_ID)

    # make sure the correct ports are open
    for port in env.AWS_SEC_GROUP_PORTS:
        try:
            data = conn.authorize_security_group_ingress(
                GroupId=appsg['GroupId'],
                IpPermissions=[
                    {'IpProtocol': 'tcp',
                    'FromPort': port,
                    'ToPort': port,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},
                ])

            # appsg.authorize('tcp', port, port, '0.0.0.0/0')
        except conn.exceptions.from_code('InvalidPermission.Duplicate'):
            pass
        except conn.exceptions.ClientError as error:
            raise error
    return appsg['GroupId']

def check_vpc(secg_id):
    """
    Check and return the VPC ID for the secg_id given
    """
    pass

def create_instances(conn, sgid):
    """
    Create one or more EC2 instances
    """

    default_if_empty(env, 'AWS_AMI_NAME',             DEFAULT_AWS_AMI_NAME)
    default_if_empty(env, 'AWS_INSTANCE_TYPE',        DEFAULT_AWS_INSTANCE_TYPE)
    default_if_empty(env, 'AWS_INSTANCES',            DEFAULT_AWS_INSTANCES)
    puts("About to create instance {0} of type {1}.".format(env.AWS_AMI_NAME, env.AWS_INSTANCE_TYPE))

    n_instances = int(env.AWS_INSTANCES)
    if n_instances > 1:
        names = ["%s_%d" % (env.AWS_INSTANCE_NAME, i) for i in range(n_instances)]
    else:
        names = [env.AWS_INSTANCE_NAME]
    puts('Creating instances {0}'.format(names))

    public_ips = None
    if 'AWS_ELASTIC_IPS' in env:

        public_ips = env.AWS_ELASTIC_IPS.split(',')
        if len(public_ips) != n_instances:
            abort("n_instances != #AWS_ELASTIC_IPS (%d != %d)" % (n_instances, len(public_ips)))

        # Disassociate the public IPs
        for public_ip in public_ips:
            if not conn.disassociate_address(public_ip=public_ip):
                abort('Could not disassociate the IP {0}'.format(public_ip))

    if 'AMI_ID' in env:
        AMI_ID = env['AMI_ID']
        env.user = env['root']
    else:
        AMI_ID = AMI_INFO[env.AWS_AMI_NAME]['id']
        env.user = AMI_INFO[env.AWS_AMI_NAME]['root']

    interface = conn.create_network_interface(
        SubnetId=env.AWS_SUBNET_ID,
        Groups=[sgid],
        )
    interfaces = [
        {
            'AssociatePublicIpAddress': True,
            'DeleteOnTermination': True,
            'Description': 'string',
            'DeviceIndex': 0,
            'Groups': [
                sgid
            ],
            'SubnetId': env.AWS_SUBNET_ID,
        },
    ]

    TagSpecifications = [
        {
            'ResourceType': 'instance',
            'Tags': [
                {
                    'Key': 'Name',
                    'Value': names[0],
                },
                {
                    'Key': 'Created By',
                    'Value': userAtHost(),
                },
                {
                    'Key': 'APP User',
                    'Value': APP_user(),
                },
                {
                    'Key': 'allocate-cost-to',
                    'Value': APP_name(),
                },
            ]
        },
    ]

    resource = boto3.resource('ec2')
    instances = resource.create_instances(ImageId=AMI_ID, InstanceType=env.AWS_INSTANCE_TYPE, 
                                    KeyName=env.AWS_KEY_NAME,
                                    MinCount=n_instances, MaxCount=n_instances,
                                    NetworkInterfaces=interfaces,
                                    TagSpecifications=TagSpecifications,
                                    )

    # Sleep so Amazon recognizes the new instance
    for i in range(4):
        fastprint('.')
        time.sleep(5)

    # Are we running yet?
    for instance in instances:
        print(f'EC2 instance "{instance.id}" has been launched')
    
        instance.wait_until_running()
    puts('.') #enforce the line-end

    # Local user and host
    userAThost = userAtHost()

    # We save the user under which we install APP for later display
    nuser = APP_user()

    # Associate the IP if needed
    if public_ips:
        for instance, public_ip in zip(instances, public_ips):
            puts('Current DNS name is {0}. About to associate the Elastic IP'.format(instance.public_dns_name))
            if not conn.associate_address(instance_id=instance.id, public_ip=public_ip):
                abort('Could not associate the IP {0} to the instance {1}'.format(public_ip, instance.id))

    # Load the new instance data as the dns_name may have changed
    host_names = []
    for instance in instances:
        instance = resource.Instance(instance.id)
        print_instance(instance)
        puts(f"DNS name/IP address: {str(instance.public_dns_name)}/{str(instance.public_ip_address)}")
        host_names.append(str(instance.public_dns_name))
    return host_names

def default_instance_name():
    rev = APP_revision()
    return DEFAULT_AWS_INSTANCE_NAME_TPL.format(rev)

@task
def create_aws_instances():
    """
    Create AWS instances and let Fabric point to them

    This method creates AWS instances and points the fabric environment to them with
    the current public IP and username.
    """

    default_if_empty(env, 'AWS_KEY_NAME',      DEFAULT_AWS_KEY_NAME)
    default_if_empty(env, 'AWS_INSTANCE_NAME', default_instance_name)

    # Create the key pair and security group if necessary
    conn = connect()
    aws_create_key_pair(conn)
    sgid = check_create_aws_sec_group(conn)

    # Create the instance in AWS
    host_names = create_instances(conn, sgid)

    # Update our fabric environment so from now on we connect to the
    # AWS machine using the correct user and SSH private key
    env.hosts = host_names
    env.key_filename = key_filename(env.AWS_KEY_NAME)
    # Instances have started, but are not usable yet, make sure SSH has started
    puts('Started the instance(s) now waiting for the SSH daemon to start.')
    execute(check_ssh, timeout=300)


@task
def list_instances(name=None):
    """
    Lists the EC2 instances associated to the user's amazon key
    """
    resource = boto3.resource('ec2')
    instances = resource.instances.all()
    for instance in instances:
        print_instance(instance, name=name)


def print_instance(inst, name=None):
    inst_id    = inst.id
    inst_state = inst.state['Name']
    inst_type  = inst.instance_type
    pub_name   = inst.public_dns_name
    pub_ip     = inst.public_ip_address
    taglist    = inst.tags
    l_time     = inst.launch_time
    key_name   = inst.key_name
    nuser = None
    outdict = {}
    outfl = True    # Controls whether info is printed

    outlist = [u'Name', u'Instance', u'Launch time', u'APP User', u'Connect',
               u'Terminate']  # defines the print order
    outdict['Instance'] = '{0} ({1}) is {2}'.format(inst_id, inst_type,
                                                    color_ec2state(inst_state
                                                                   ))
    for tag in taglist:
        val = tag['Value']
        if tag['Key'] == 'Name':
            key_name = tag['Value']
            val = blue(key_name)
            if name is not None:
                name = six.text_type(name)
                if val.find(name) == -1:
                    outfl = False
                else:
                    puts(name)
        outdict[tag['Key']] = val
    if u'APP User' in outdict.keys():
        nuser = outdict[u'APP User']
    if u'NGAS User' in outdict.keys():
        nuser = outdict[u'NGAS User']
    if inst_state == 'running':
        ssh_user = ' -l%s' % (nuser) if nuser else ''
        outdict['Connect'] = 'ssh -i ~/.ssh/{0}.pem {1}{2}'.format(key_name,
                                                                   pub_name,
                                                                   ssh_user)
        outdict['Terminate'] = 'fab aws.terminate:instance_id={0}'.format(
            inst_id)
        outdict['Launch time'] = '{0}'.format(l_time)
    if outfl:
        for k in outlist:
            if k in outdict:
                puts("{0}: {1}".format(k, outdict[k]))
        puts('')


def color_ec2state(state):
    if state == 'running':
        return green(state)
    elif state == 'terminated':
        return red(state)
    elif state == 'shutting-down':
        return yellow(state)
    return state


@task
def terminate(instance_id):
    """
    Task to terminate the boto instances
    """
    if not instance_id:
        abort('No instance ID specified. Please provide one.')

    res = boto3.resource('ec2')
    instance = res.Instance(instance_id)
    tagdict = instance.tags
    print_instance(instance)

    puts('')
    if 'Created By' in tagdict and tagdict['Created By'] != userAtHost():
        puts('******************************************************')
        puts('WARNING: This instances has not been created by you!!!')
        puts('******************************************************')
    if confirm("Do you really want to terminate this instance?"):
        puts('Teminating instance {0}'.format(instance_id))
        instance.terminate()
    else:
        puts(red('Instance NOT terminated!'))
    return

@task
def acheck_ssh():
    print(env.key_filename)
    execute(check_ssh)
