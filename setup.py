#! /usr/bin/env python

##
#  Somehow I now have to choose between:
#    - distutils;
#    - setuptools;
#    - distribute;
#  I intend to use (for python 2*):
#    - pip;
#
# All apparently do different things.
# Aaaarrrrrgh!

### NOTE:  abandoning distutils;
#     doesn't operate on requirements (only comments on them)
#   See:  http://lucumr.pocoo.org/2012/6/22/hate-hate-hate-everywhere/

## (ABANDONED) modeled after:
#    http://blog.doughellmann.com/2007/11/requiring-packages-with-distutils.html
#  see also:
#    http://docs.python.org/2/distutils/setupscript.html
###
# from distutils.core import setup
# import os
###

###
#  Some references:
#   http://docs.python.org/3/distutils/
#   http://stackoverflow.com/questions/6344076/differences-between-distribute-distutils-setuptools-and-distutils2
#   http://ziade.org/2010/03/03/the-fate-of-distutils-pycon-summit-packaging-sprint-detailed-report/
#   http://wokslog.wordpress.com/2011/06/04/distutils-diff/


### GOING WITH:   pip;
#       Undecided yet if w/ setuptools or distribute;
#  Refs:
#   http://www.pip-installer.org/en/latest/
#   http://peak.telecommunity.com/DevCenter/setuptools
#   http://pythonhosted.org/distribute/
#
# Decision:
#   After looking at examples from both Doug Hellman, and Ian Bicking,
#   modeling this after Ian Bicking's  virtualenv/setup.py
# NOTE:  favors setuptools, fallsback to distutils;
#

import os
import re
import shutil
import sys

try:
    from setuptools import setup
    setup_params = {
        'entry_points': {
            'console_scripts': [
                'scrape=scrape:main',
                'scrape-%s.%s=scrape:main' % sys.version_info[:2]
            ],
        },
        'zip_safe':False,
    }
except ImportError:
    from distutils.core import setup
    if sys.platform == 'win32':
        print(
            'Note: witout Setuptools installed you will have to use "python -m scrape ARGS"'
        )
        setup_params = {}
    else:
        script = 'scripts/scrape'
        script_ver = script + '-%s.%s' % sys.version_info[:2]
        shutil.copy(script, scripte_ver)
        setup_params = {'scripts': [script, script_ver]}


here = os.path.dirname(os.path.abspath(__file__))

'''
## Get long_description from description.rst
#
with open(os.path.join(here, 'docs', 'description.rst')) as f:
    long_description = f.read().strip()
    long_description = long_description.split('split here', 1)[1]

with open(os.path.join(here, 'docs', 'news.rst')) as f:
    long_description += '\n\n' + f.read()
'''
# for now:
long_description = ''

with open(os.path.join(here, 'requirements.txt')) as f:
    install_requires = f.read()

def get_version():
    with open(os.path.join(here, 'scrape.py')) as f:
        version_file = f.read()

    version_match = re.search(r"^__version__\s*=\s*['\"]([^'\"]*)['\"]",
                              version_file, re.MULTILINE)
    if version_match:
        return version_match.group(1)
    raise RunTimeError("Unable to find version string.")


setup(
    name         = 'scrape',
    # TODO:
    # I need to decide where / how to put overview info;
    #  - Ian has once approach w/ virtualenv.py;
    #  - I have to settle on one that will work here...
    version      = get_version(),
    description  = "Web & HTML [S]crape-ing command processor",
    long_description = long_description,
    classifiers  = [
        'Development Status :: 0 - Alpha',
        'Intended Audience  :: Developers',
        'Programmingn Language :: Python :: 2.7',
    ],
    keywords     = 'webscraping',
    author       = "Yarko Tymciurak",
    author_email = "yarkot1@gmail.com",
    url          = 'http://scrape.readthedocs.org',
    license      = 'BSD',
    py_modules    = ['scrape'],
    packages     = ['scrapelib', 'envoy',],
    # do this w/ Manifest.in instead; save package_data
    #  for actual package data:
    # package_data = {'scrape': ['_scrape/plugins/*.py], },
    #
    # download_url = 'http://xxx.xxx/scrape-0.1a1.tar.gz',
    install_requires=install_requires,
    **setup_params
)


