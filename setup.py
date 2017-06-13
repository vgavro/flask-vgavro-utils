from setuptools import setup, find_packages

setup(
    name='flask-vgavro-utils',
    version='0.0.1',
    description='http://github.com/vgavro/flask_vgavro_utils',
    long_description='http://github.com/vgavro/flask_vgavro_utils',
    license='BSD',
    classifiers=[
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    author='Victor Gavro',
    author_email='vgavro@gmail.com',
    url='http://github.com/vgavro/flask_vgavro_utils',
    keywords='',
    packages=find_packages(),
    install_requires=['flask>=0.9'],
    entry_points={
        'flask.commands': [
            'dbreinit=flask_vgavro_utils.cli:dbreinit',
            'dbshell=flask_vgavro_utils.cli:dbshell',
        ],
    },
)
