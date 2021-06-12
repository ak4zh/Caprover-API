#!/usr/bin/env python

"""The setup script."""

from setuptools import setup, find_packages

with open('README.rst') as readme_file:
    readme = readme_file.read()

with open('HISTORY.rst') as history_file:
    history = history_file.read()

requirements = [
    'requests>=2.25.1',
    'PyYAML>=5.4.1'
]

test_requirements = [
    'requests>=2.25.1',
    'PyYAML>=5.4.1'
]

setup(
    author="Akash Agarwal",
    author_email='agwl.akash@gmail.com',
    python_requires='>=3.6',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ],
    description="unofficial caprover api to deploy apps to caprover",
    install_requires=requirements,
    license="MIT license",
    long_description=readme + '\n\n' + history,
    include_package_data=True,
    keywords='caprover_api',
    name='caprover_api',
    packages=find_packages(include=['caprover_api', 'caprover_api.*']),
    test_suite='tests',
    tests_require=test_requirements,
    url='https://github.com/ak4zh/caprover-api',
    version='0.1.11',
    zip_safe=False,
)
