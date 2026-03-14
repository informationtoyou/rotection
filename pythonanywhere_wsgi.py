"""
WSGI for PythonAnywhere.
"""

import sys
import os

# ── Update this to your actual project path on PythonAnywhere ──
project_home = '/home/rotection/mysite/rotection'

if project_home not in sys.path:
    sys.path.insert(0, project_home)

os.chdir(project_home)

# load .env before anything else
from dotenv import load_dotenv
load_dotenv(os.path.join(project_home, '.env'))

from app import create_app
application = create_app()
