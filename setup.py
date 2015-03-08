from setuptools import setup, find_packages
from txmpserv.interruptable_thread import ffi

with open('requirements.txt') as f:
    requirements = list(f)

setup(name='txmpserv',
      version='0.0.1',
      packages=find_packages(),
      ext_package='txmpserv',
      install_requires=requirements,
      ext_modules=[ffi.verifier.get_extension()])
