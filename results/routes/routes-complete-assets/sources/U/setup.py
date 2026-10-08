from setuptools import setup
setup(name='wg-matrix', version='0.1.0', packages=['wg_matrix'],
      package_data={}, include_package_data=False,
      description='Authored route-sensitivity fixture',
      entry_points={'console_scripts':['wg-matrix=wg_matrix:main']})
