from distutils.core import setup, Extension

pkg = 'Extensions.MagentaMusik360'
setup (name = 'enigma2-plugin-extensions-magentamusik360',
       version = '1.0',
       license='GPLv2',
       url='https://github.com/E2OpenPlugins',
       description='MagentaMusik360 Plugin',
       long_description='Plugin for watching MagentaMusik 360 streams',
       author='betacentauri',
       author_email='betacentauri@arcor.de',
       packages = [pkg],
       package_dir = {pkg: 'plugin'},
       package_data={pkg: ['*.png', '*.xml']}
)
