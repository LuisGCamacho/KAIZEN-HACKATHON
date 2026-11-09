import os
import sys

# Los tests importan desde backend/ igual que run.py y live.py (from env.inventario import ...)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
