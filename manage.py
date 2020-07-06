#!/usr/bin/env python
import os
import sys

if __name__ == "__main__":
    if "OMA_INSTANCE" in os.environ:
        if os.environ['OMA_INSTANCE'].upper() == "BASF":
            os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pybrowser_dev.settings.basf')
        elif os.environ['OMA_INSTANCE'].upper() in ("", "FULL"):
            os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pybrowser_dev.settings.prod')
        elif os.environ['OMA_INSTANCE'].upper() in ("TEST", "TESTING"):
            os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pybrowser_dev.settings.testing')
    else:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pybrowser_dev.settings.testing')

    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
