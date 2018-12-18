This project represents a template for a deployment system using fabric3.

https://pypi.org/project/Fabric3/

To use it you first need to install this template module
into the desired python environment using:

```
pip install git+https://github.com/ICRAR/fabfileTemplate
```

You can directly run installations with this template, but the intentional
usage of this package is to provide a standardised and flexible installation
procedure for other systems for operational or development deployments on
the cloud and on dedicated computers. By using fabric3 as a backend this 
template also enables parallel installations on many computers.

Start by copying the whole fabfile directory from the fabfileTemplate into
your projects top level directory. Then edit the file fabfile/APPspecific.py
and adjust it to your needs.

The tasks provided can be seen by executing:

```
fab --list
```

in the root directory of your application.

The output looks like:
```
Fabric scripts for TEMPLATE deployment and related activities.

For a detailed description of a task run "fab -d <task>"

End users will likely use the hl.operations_deploy or hl.user_deploy tasks,
Other tasks, including lower-level tasks, can also be invoked.

Available commands:

    APPcommon.copy_sources          Creates a copy of the APP sources in the target host.
    APPcommon.install_and_check     Creates a virtualenv, installs APP on it,
    APPcommon.install_user_profile  Put the activation of the virtualenv into the login profile of the user
    APPcommon.virtualenv_setup      Creates a new virtualenv that will hold the APP installation
    APPspecific.cleanup
    aws.create_aws_instances        Create AWS instances and let Fabric point to them
    aws.list_instances              Lists the EC2 instances associated to the user's amazon key
    aws.terminate                   Task to terminate the boto instances
    hl.aws_deploy                   Deploy APP on fresh AWS EC2 instances.
    hl.docker_image                 Create a Docker image with an APP installation.
    hl.operations_deploy            Performs a system-level setup on a host and installs APP on it
    hl.prepare_release              Prepares an APP release (deploys APP into AWS serving its own source/doc)
    hl.upload_release               Uploads sources and documentation to AWS instance.
    hl.user_deploy                  Compiles and installs APP in a user-owned directory.
    pkgmgr.install_homebrew         Task to install homebrew on Mac OSX.
    pkgmgr.install_system_packages  Perform the installation of system-level packages needed by APP to work.
    pkgmgr.list_packages
    pkgmgr.system_check             Check for existence of system level packages
    system.assign_ddns              Installs the noip ddns client to the specified host.
    system.check_command            Check existence of command remotely
    system.check_dir                Check existence of remote directory
    system.check_path               Check existence of remote path
    system.check_python             Check for the existence of correct version of python
    system.check_sudo               Checks if the sudo command is present.
    system.check_user               Task checking existence of user
    system.create_user              Creates a user in the system.
    system.postfix_config           Setup a valid Postfix configuration to be used by APP.
    system.python_setup             Ensure that there is the right version of python available
    utils.check_ssh                 Check availability of SSH
    utils.whatsmyip                 Returns the external IP address of the host running fab.
    ```