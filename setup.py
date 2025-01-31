from setuptools import setup, find_namespace_packages
import os

def find_resource_files(directory):
    paths = []
    for (path, _, filenames) in os.walk(directory):
        for filename in filenames:
            paths.append(os.path.join('..', path, filename))
    return paths

# -- Apps Definition -- #
ext_package = 'workflows'
release_package = 'tethysext-workflows'

# -- Python Dependencies -- #
dependencies = ['param', 'geojson', 'panel', 'plotly', 'pyshp', 'tethys_dataset_services', 'tethys-platform']

# -- Get Resource File -- #
resource_files = find_resource_files('tethysext/workflows/templates')
resource_files += find_resource_files('tethysext/workflows/public')
resource_files += find_resource_files('tethysext/workflows/job_scripts')


setup(
    name=release_package,
    version='0.0.3',
    description='',
    long_description='',
    keywords='',
    author='',
    author_email='',
    url='',
    license='',
    packages=find_namespace_packages(),
    package_data={'': resource_files},
    include_package_data=True,
    zip_safe=False,
    install_requires=dependencies,
)