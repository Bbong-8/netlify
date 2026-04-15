"""WSGI entry point for Plesk Python hosting (if using Passenger)."""
import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.dirname(__file__))

from server import app

# For Passenger WSGI compatibility
application = app
