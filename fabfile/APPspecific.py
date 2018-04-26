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
Main module where application-specific tasks are carried out, like copying its
sources, installing it and making sure it works after starting it.

NOTE: This requires modifications for the specific application where this
fabfile is used. Please make sure not to use it without those modifications.
"""
import contextlib
import functools
import httplib
import os
import tempfile
import urllib2

from fabric.context_managers import settings, cd
from fabric.contrib.files import exists, sed
from fabric.decorators import task, parallel
from fabric.operations import local, put
from fabric.state import env
from fabric.utils import abort

from pkgmgr import install_system_packages, check_brew_port, check_brew_cellar
from system import check_dir, download, check_command, \
    create_user, get_linux_flavor, python_setup, check_python, \
    MACPORT_DIR
from utils import is_localhost, home, default_if_empty, sudo, run, success,\
    failure, info

# Don't re-export the tasks imported from other modules, only the ones defined
# here
__all__ = [
    'start_APP_and_check_status',
    'virtualenv_setup',
    'install_user_profile',
    'copy_sources',
]

# The following variable will define the Application name as well as directory
# structure and a number of other application specific names.
APP = 'APP'

# The username to use by default on remote hosts where APP is being installed
# This user might be different from the initial username used to connect to the
# remote host, in which case it will be created first
APP_USER = APP.lower()

# Name of the directory where APP sources will be expanded on the target host
# This is relative to the APP_USER home directory
APP_SRC_DIR_NAME = APP.lower() + '_src'

# Name of the directory where APP root directory will be created
# This is relative to the APP_USER home directory
APP_ROOT_DIR_NAME = 'APP'

# Name of the directory where a virtualenv will be created to host the APP
# software installation, plus the installation of all its related software
# This is relative to the APP_USER home directory
APP_INSTALL_DIR_NAME = APP.lower() + '_rt'

# NOTE: Make sure to modify the following lists to meet the requirements for
# the application.


# Alpha-sorted packages per package manager
env.pkgs = {
            'YUM_PACKAGES': [
                     'autoconf',
                     'bzip2-devel',
                     'cfitsio-devel',
                     'db4-devel',
                     'gcc',
                     'gdbm-devel',
                     'git',
                     'libdb-devel',
                     'libtool',
                     'make',
                     'openssl-devel',
                     'patch',
                     'postfix',
                     'postgresql-devel',
                     'python27-devel',
                     'python-devel',
                     'readline-devel',
                     'sqlite-devel',
                     'tar',
                     'wget',
                     'zlib-devel',
                     ],
            'APT_PACKAGES': [
                    'autoconf',
                    'libcfitsio-dev',
                    'libdb5.3-dev',
                    'libdb-dev',
                    'libgdbm-dev',
                    'libreadline-dev',
                    'libsqlite3-dev',
                    'libssl-dev',
                    'libtool',
                    'libzlcore-dev',
                    'make',
                    'patch',
                    'postgresql-client',
                    'python-dev',
                    'python-setuptools',
                    'tar',
                    'sqlite3',
                    'wget',
                    'zlib1g-dbg',
                    'zlib1g-dev',
                    ],
            'SLES_PACKAGES': [
                    'autoconf',
                    'automake',
                    'gcc',
                    'gdbm-devel',
                    'git',
                    'libdb-4_5',
                    'libdb-4_5-devel',
                    'libtool',
                    'make',
                    'openssl',
                    'patch',
                    'python-devel',
                    'python-html5lib',
                    'python-pyOpenSSL',
                    'python-xml',
                    'postfix',
                    'postgresql-devel',
                    'sqlite3-devel',
                    'wget',
                    'zlib',
                    'zlib-devel',
                    ],
            'BREW_PACKAGES': [
                    'autoconf',
                    'automake',
                    'berkeley-db',
                    'libtool',
                    'wget',
                    ],
            'PORT_PACKAGES': [
                    'autoconf',
                    'automake',
                    'db60',
                    'libtool',
                    'wget',
                    ]
        }


def APP_user():
    default_if_empty(env, 'APP_USER', APP_USER)
    return env.APP_USER


def APP_install_dir():
    key = 'APP_INSTALL_DIR'
    if key not in env:
        env[key] = os.path.abspath(os.path.join(home(), APP_INSTALL_DIR_NAME))
    return env[key]


def APP_overwrite_installation():
    key = 'APP_OVERWRITE_INSTALLATION'
    return key in env


def APP_use_custom_pip_cert():
    key = 'APP_USE_CUSTOM_PIP_CERT'
    return key in env


def APP_root_dir():
    key = 'APP_ROOT_DIR'
    if key not in env:
        env[key] = os.path.abspath(os.path.join(home(), APP_ROOT_DIR_NAME))
    return env[key]


def APP_overwrite_root():
    key = 'APP_OVERWRITE_ROOT'
    return key in env


def APP_source_dir():
    key = 'APP_SRC_DIR'
    if key not in env:
        env[key] = os.path.abspath(os.path.join(home(), APP_SRC_DIR_NAME))
    return env[key]


def APP_doc_dependencies():
    key = 'APP_NO_DOC_DEPENDENCIES'
    return key in env


def has_local_git_repo():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    return os.path.exists(os.path.join(repo_root, '.git'))


def default_APP_revision():
    if has_local_git_repo():
        return local('git rev-parse --abbrev-ref HEAD', capture=True)
    return 'local'


def APP_revision():
    default_if_empty(env, 'APP_REV', default_APP_revision)
    return env.APP_REV


def extra_python_packages():
    key = 'APP_EXTRA_PYTHON_PACKAGES'
    if key in env:
        return env[key].split(',')
    return None


def virtualenv(command, **kwargs):
    """
    Just a helper function to execute commands in the APP virtualenv
    """
    nid = APP_install_dir()
    return run('source {0}/bin/activate && {1}'.format(nid, command), **kwargs)


def start_APP_and_check_status(tgt_cfg):
    """
    Starts the APP daemon process and checks that the server is up and running
    then it shuts down the server
    """
    # We sleep 2 here as it was found on Mac deployment to docker container
    # that the shell would exit before the APPDaemon could detach, thus
    # resulting in no startup self.
    #
    # Please replace following line with something meaningful
    # virtualenv('ngamsDaemon start -cfg {0} && sleep 2'.format(tgt_cfg))
    pass


@task
def virtualenv_setup():
    """
    Creates a new virtualenv that will hold the APP installation
    """
    APPInstallDir = APP_install_dir()
    if check_dir(APPInstallDir):
        overwrite = APP_overwrite_installation()
        if not overwrite:
            msg = ("%s exists already. Specify APP_OVERWRITE_INSTALLATION to overwrite, "
                   "or a different APP_INSTALL_DIR location")
            abort(msg % (APPInstallDir,))
        run("rm -rf %s" % (APPInstallDir,))

    # Check which python will be bound to the virtualenv
    ppath = check_python()
    if not ppath:
        ppath = python_setup(os.path.join(home(), 'python'))

    # Use our create_venv.sh script to create the virtualenv
    # It already handles the download automatically if no virtualenv command is
    # found in the system, and also allows to specify a python executable path
    with cd(APP_source_dir()):
        run("./create_venv.sh -p {0} {1}".format(ppath, APPInstallDir))

    # Download this particular certifcate; otherwise pip complains
    # in some platforms
    if APP_use_custom_pip_cert():
        if not(check_dir('~/.pip')):
            run('mkdir ~/.pip')
            with cd('~/.pip'):
                download('http://curl.haxx.se/ca/cacert.pem')
        run('echo "[global]" > ~/.pip/pip.conf; echo "cert = {0}/.pip/cacert.pem" >> ~/.pip/pip.conf;'.format(home()))

    # Update pip and install wheel; this way we can install binary wheels from
    # PyPI if available (like astropy)
    # TODO: setuptools and python-daemon are here only because
    #       python-daemon 2.1.2 is having a problem to install via setuptools
    #       but not via pip (see https://pagure.io/python-daemon/issue/2 and
    #       https://pagure.io/python-daemon/issue/3).
    #       When this problem is fixed we'll fix our dependency on python-daemo
    #       to avoid this issue entirely
    virtualenv('pip install -U pip wheel setuptools python-daemon')

    success("Virtualenv setup completed")


@task
def install_user_profile():
    """
    Put the activation of the virtualenv into the login profile of the user
    unless the APP_DONT_MODIFY_BASHPROFILE environment variable is defined

    NOTE: This will be executed for the user running APP.
    """
    if run('echo $APP_DONT_MODIFY_BASHPROFILE') or \
       'APP_NO_BASH_PROFILE' in env:
        return

    nid = APP_install_dir()
    nrd = APP_root_dir()
    with cd("~"):
        if not exists(".bash_profile_orig"):
            run('cp .bash_profile .bash_profile_orig', warn_only=True)
        else:
            run('cp .bash_profile_orig .bash_profile')

        script = ('if [ -f "{0}/bin/activate" ]'.format(nid),
                  'then',
                  '   source "{0}/bin/activate"'.format(nid),
                  'fi',
                  'export APP_PREFIX="{0}"'.format(nrd))

        run("echo '{0}' >> .bash_profile".format('\n'.join(script)))

    success("~/.bash_profile edited for automatic virtualenv sourcing")


def APP_build_cmd(no_client, develop, no_doc_dependencies):

    # The installation of the bsddb package (needed by ngamsCore) is in
    # particular difficult because it requires some flags to be passed on
    # (particularly if using MacOSX's port
    # >>>> NOTE: This function will need heavy customisation <<<<<<
    build_cmd = []
    linux_flavor = get_linux_flavor()
    if linux_flavor == 'Darwin':
        pkgmgr = check_brew_port()
        if pkgmgr == 'brew':
            cellardir = check_brew_cellar()
            db_version = run('ls -tr1 {0}/berkeley-db'.format(cellardir)).split()[-1]
            db_dir = '{0}/berkeley-db/{1}'.format(cellardir, db_version)
            build_cmd.append('BERKELEYDB_DIR={0}'.format(db_dir))
            if not no_client:
                build_cmd.append('CFLAGS=-I{0}/include'.format(db_dir))
                build_cmd.append('LDFLAGS=-L{0}/lib'.format(db_dir))
        else:
            incdir = MACPORT_DIR + '/include/db60'
            libdir = MACPORT_DIR + '/lib/db60'
            build_cmd.append('BERKELEYDB_INCDIR=' + incdir)
            build_cmd.append('BERKELEYDB_LIBDIR=' + libdir)
            if not no_client:
                build_cmd.append('CFLAGS=-I' + incdir)
                build_cmd.append('LDFLAGS=-L' + libdir)
        build_cmd.append('YES_I_HAVE_THE_RIGHT_TO_USE_THIS_BERKELEY_DB_VERSION=1')

    if APP_no_crc32c():
        build_cmd.append('APP_NO_CRC32C=1')
    build_cmd.append('./build.sh')
    if not no_client:
        build_cmd.append("-c")
    if develop:
        build_cmd.append("-d")
    if not no_doc_dependencies:
        build_cmd.append('-D')

    return ' '.join(build_cmd)


def build_APP():
    """
    Builds and installs APP into the target virtualenv.
    """
    with cd(APP_source_dir()):
        extra_pkgs = extra_python_packages()
        if extra_pkgs:
            virtualenv('pip install %s' % ' '.join(extra_pkgs))
        no_client = APP_no_client()
        develop = APP_develop()
        no_doc_dependencies = APP_doc_dependencies()
        build_cmd = APP_build_cmd(no_client, develop, no_doc_dependencies)
        virtualenv(build_cmd)
    success("APP built and installed")


def prepare_APP_data_dir():
    """Creates a new APP root directory"""

    info('Preparing APP root directory')
    nrd = APP_root_dir()
    tgt_cfg = os.path.join(nrd, 'cfg', 'ngamsServer.conf')
    with cd(APP_source_dir()):

        cmd = ['./prepare_APP_root.sh']
        if APP_overwrite_root():
            cmd.append('-f')
        cmd.append(nrd)
        res = run(' '.join(cmd), quiet=True)
        if res.succeeded:
            success("APP data directory ready")
            return tgt_cfg

    # Deal with the errors here
    error = 'APP root directory preparation under {0} failed.\n'.format(nrd)
    if res.return_code == 2:
        error = (nrd + " already exists. Specify APP_OVERWRITE_ROOT to overwrite, "
                 "or a different APP_ROOT_DIR location")
    else:
        error = res
    abort(error)


def install_sysv_init_script(nsd, nuser, cfgfile):
    """
    Install the APP init script for an operational deployment.
    The init script is an old System V init system.
    In the presence of a systemd-enabled system we use the update-rc.d tool
    to enable the script as part of systemd (instead of the System V chkconfig
    tool which we use instead). The script is prepared to deal with both tools.
    """

    # Different distros place it in different directories
    # The init script is prepared for both
    opt_file = '/etc/sysconfig/APP'
    if get_linux_flavor() in ('Ubuntu', 'Debian'):
        opt_file = '/etc/default/APP'

    # Script file installation
    sudo('cp %s/fabfile/init/sysv/APP-server /etc/init.d/' % (nsd,))
    sudo('chmod 755 /etc/init.d/APP-server')

    # Options file installation and edition
    ntype = APP_server_type()
    sudo('cp %s/fabfile/init/sysv/APP-server.options %s' % (nsd, opt_file))
    sudo('chmod 644 %s' % (opt_file,))
    sed(opt_file, '^USER=.*', 'USER=%s' % (nuser,), use_sudo=True, backup='')
    sed(opt_file, '^CFGFILE=.*', 'CFGFILE=%s' % (cfgfile,), use_sudo=True, backup='')
    if ntype == 'cache':
        sed(opt_file, '^CACHE=.*', 'CACHE=YES', use_sudo=True, backup='')
    elif ntype == 'data-mover':
        sed(opt_file, '^DATA_MOVER=.*', 'DATA_MOVER=YES', use_sudo=True, backup='')

    # Enabling init file on boot
    if check_command('update-rc.d'):
        sudo('update-rc.d APP-server defaults')
    else:
        sudo('chkconfig --add APP-server')

    success("APP init script installed")


def create_sources_tarball(tarball_filename):
    # Make sure we are git-archivin'ing from the root of the repository,
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if has_local_git_repo():
        local('cd {0}; git archive -o {1} {2}'.format(repo_root, tarball_filename, APP_revision()))
    else:
        local('cd {0}; tar czf {1} .'.format(repo_root, tarball_filename))


@task
def copy_sources():
    """
    Creates a copy of the APP sources in the target host.
    """

    # We still don't open the git repository to the world, so for the time
    # being we always make a tarball from our repository and copy it over
    # ssh to the remote host, where we expand it back

    nsd = APP_source_dir()

    # Because this could be happening in parallel in various machines
    # we generate a tmpfile locally, but the target file is the same
    local_file = tempfile.mktemp(".tar.gz")
    create_sources_tarball(local_file)

    # transfer the tar file if not local
    if not is_localhost():
        target_tarfile = '/tmp/APP_tmp.tar'
        put(local_file, target_tarfile)
    else:
        target_tarfile = local_file

    # unpack the tar file into the APP_src_dir
    # (mind the "p", to preserve permissions)
    run('mkdir -p {0}'.format(nsd))
    with cd(nsd):
        run('tar xpf {0}'.format(target_tarfile))
        if not is_localhost():
            run('rm {0}'.format(target_tarfile))

    # Cleaning up now
    local('rm {0}'.format(local_file))

    success("APP sources copied")

@parallel
def prepare_install_and_check():

    # Install system packages and create user if necessary
    nuser = APP_user()
    install_system_packages()
    create_user(nuser)
    #postfix_config()

    # Go, go, go!
    with settings(user=nuser):
        nsd, cfgfile = install_and_check()

    # Install the /etc/init.d script for automatic start
    install_sysv_init_script(nsd, nuser, cfgfile)

@parallel
def install_and_check():
    """
    Creates a virtualenv, installs APP on it,
    starts APP and checks that it is running
    """
    copy_sources()
    virtualenv_setup()
    build_APP()
    tgt_cfg = prepare_APP_data_dir()
    install_user_profile()
    start_APP_and_check_status(tgt_cfg)
    return APP_source_dir(), tgt_cfg

def upload_to(host, filename, port=7777):
    """
    Simple method to upload a file into APP
    """
    with contextlib.closing(httplib.HTTPConnection(host, port)) as conn:
        conn.putrequest('POST', '/QARCHIVE?filename=%s' % (urllib2.quote(os.path.basename(filename)),) )
        conn.putheader('Content-Length', os.stat(filename).st_size)
        conn.endheaders()
        with open(filename) as f:
            for data in iter(functools.partial(f.read, 4096), ''):
                conn.send(data)
        r = conn.getresponse()
        if r.status != httplib.OK:
            raise Exception("Error while QARCHIVE-ing %s to %s:%d:\nStatus: %d\n%s\n\n%s" % (filename, conn.host, conn.port, r.status, r.msg, r.read()))
        else:
            success("{0} successfully archived to {1}!".format(filename, host))
