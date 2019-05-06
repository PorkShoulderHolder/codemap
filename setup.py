from setuptools import setup

setup(name='codemap',
      packages=['codemap'],
      version='0.3',
      description='A python in-project functional dependency analyzer. ',
      author='Sam Fox Royston',
      author_email='sfoxroyston@gmail.com',
      license="MIT",
      url='https://github.com/PorkShoulderHolder/codemap',
      keywords=["static analysis", "visualization", "dependencies", "python"],
      install_requires=["graphviz", "click", "tqdm", "editdistance"],
      entry_points='''
          [console_scripts]
          codemap=codemap:analyze_deps
       ''',
)

