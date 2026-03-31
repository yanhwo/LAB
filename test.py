import os
import sys
from datetime import datetime

with open('debug_log2.txt', 'w', encoding='utf-8') as f:
    f.write(f"Time: {datetime.now()}\n")
    f.write(f"Python: {sys.executable}\n")
    f.write(f"Version: {sys.version}\n")
    f.write(f"CWD: {os.getcwd()}\n")
    f.write(f"PATH: {os.environ.get('PATH', 'N/A')}\n")
    f.write(f"User: {os.environ.get('USERNAME', 'N/A')}\n")