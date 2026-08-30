# -*- coding: utf-8 -*-

import inspect
import os
import sys
import pathlib
import inspect
import subprocess
import sys

if __name__ != '__main__':
    print('This module is not designed to be imported', file=sys.stderr)


if len(sys.argv) < 2:
    print('Usage: python localize.py <command>\n'
          '  extract\tExtract entries to template and update\n'
          '  compile\tCompile language resource\n',
          file=sys.stderr)
    sys.exit(1)


command = sys.argv[1]
BASE_DIR = pathlib.Path(os.path.dirname(inspect.getfile(inspect.currentframe()))).parent.parent
cwd = os.getcwd()
os.chdir(BASE_DIR)

match command:
    case 'extract':
        subprocess.run(['pybabel', 'extract', '-F', 'babel.cfg', '-o', 'res/locale/app.pot', '.'])
        subprocess.run(['pybabel', 'update', '-i', 'res/locale/app.pot', '-d', 'res/locale'])
    case 'compile':
        subprocess.run(['pybabel', 'compile', '-d', 'res/locale'])

os.chdir(cwd)
