#
#    ICRAR - International Centre for Radio Astronomy Research
#    (c) UWA - The University of Western Australia, 2015
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
import os
import glob
from setuptools import setup, find_packages
from setuptools.command.install import install
from distutils.command.build import build
from subprocess import call

BASEPATH = os.path.dirname(os.path.abspath(__file__))
DOCS_PATH = os.path.join(BASEPATH, 'docs')
DOCS_SPATH = os.path.join(DOCS_PATH, 'source')
version = '0.0'

class docsBuild(build):
    def run(self):
        # run original build code
        build.run(self)

        # build docs
        build_path = os.path.abspath(self.build_temp)

        cmd = [
            'make',
        ]

        options = []
        cmd.extend(options)

        targets = ['html']
        cmd.extend(targets)

        target_dir = os.path.join(DOCS_PATH, 'static', 'html')

        def compile():
            call(cmd, cwd=DOCS_SPATH)

        self.execute(compile, [], 'Compiling docs')

        # copy resulting tool to library build folder

        # self.mkpath(self.build_lib)

        if not self.dry_run:
            pass
            # self.copy_tree(target_dir, os.path.join(self.build_lib, 'static',
            #                                        'html'))


class docsInstall(install):
    def initialize_options(self):
        install.initialize_options(self)
        self.build_scripts = None

    def finalize_options(self):
        install.finalize_options(self)
        self.set_undefined_options('build', ('build_scripts', 'build_scripts'))

    def run(self):
        # run original install code
        install.run(self)

        # install docs
        # self.copy_tree('docs/static/', os.path.join(self.install_lib, 'static'))


with open('VERSION') as vfile:
    for line in vfile.readlines():
        if "SW_VER" in line:
            version = line.split("SW_VER ")[1].strip()[1:-1]
            break

# extra Python packages go here
install_requires = [
    'fabric3',
    'boto',
    'pycrypto'
    ]

setup(
    name='fabfileTemplate',
    version=version,
    description="The template for complex fabric installation",
    long_description="This package contains a set of tasks and functions for complex fabric based installations",
    classifiers=[],
    keywords='',
    author='Andreas Wicenec',
    author_email='andreas.wicenec@icrar.org',
    url='',
    license='LGPLv3',
    packages=['fabfileTemplate'],
    include_package_data=True,
    package_data={
        'fabfileTemplate': ['README.md', 'LICENSE'
        'VERSION',
        'prepare_APP_root.sh',
        'create_venv.sh'],
     },
    dependency_links=['http://github.com/ICRAR/daliuge/tarball/master#egg=daliuge-1.0'],
    install_requires=install_requires,
    # No spaces allowed between the '='s
    entry_points={
        'console_scripts': [
        ],
    },
    cmdclass={
        'build': docsBuild,
        'install': docsInstall
        }
)
