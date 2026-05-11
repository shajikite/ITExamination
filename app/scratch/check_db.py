import sqlite3
import os

db_path = '/home/shaji/shaji/IT_exam/app/database/database.db'

# Check if it's sqlite or postgres
# The schema.sql uses SERIAL and BYTEA which suggests Postgres, 
# but I saw database.db in the directory.
# Let's check the connection string in __init__.py or config.py

with open('/home/shaji/shaji/IT_exam/app/config.py', 'r') as f:
    print(f.read())
