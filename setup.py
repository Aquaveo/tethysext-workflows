from setuptools import setup, find_namespace_packages
from tethys_apps.app_installation import find_all_resource_files
from tethys_apps.base.app_base import TethysExtensionBase

# -- Apps Definition -- #
ext_package = 'workflows'
release_package = f'{TethysExtensionBase.package_namespace}-{ext_package}'

# -- Python Dependencies -- #
dependencies = []

# -- Get Resource File -- #
resource_files = find_all_resource_files(ext_package, TethysExtensionBase.package_namespace)

setup(
    name=release_package,
    version='0.0.1',
    description='Worklows Extension for Tethys Platform',
    long_description='A Tethys extension that provides a framework for working with workflows.',
    keywords='tethys, extension, workflows',
    author='Jacob Johnson',
    author_email='jjohnson@aquaveo.com',
    url='https://github.com/Aquaveo/tethysext-workflows',
    license='',
    packages=find_namespace_packages(),
    package_data={'': resource_files},
    include_package_data=True,
    zip_safe=False,
    install_requires=dependencies,
)