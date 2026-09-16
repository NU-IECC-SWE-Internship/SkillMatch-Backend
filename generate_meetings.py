#!/usr/bin/env python
"""
Standalone script to generate test Skill Swap meetings.
You can run this directly from the terminal:
    python generate_meetings.py
Or with options:
    python generate_meetings.py --clear
    python generate_meetings.py --scenario live
    python generate_meetings.py --mock
    python generate_meetings.py --set-password testpass123
"""

import os
import sys

def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
    try:
        import django
        django.setup()
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Make sure it's installed and available on your "
            "PYTHONPATH environment variable, or activate your virtual environment (.venv)."
        ) from exc

    from django.core.management import execute_from_command_line

    # Forward to the Django management command
    args = [sys.argv[0], "generate_test_meetings"] + sys.argv[1:]
    execute_from_command_line(args)

if __name__ == "__main__":
    main()
