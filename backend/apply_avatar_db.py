"""Idempotently add avatar columns and set avatar URLs for default characters.

Writes a result report to backend/avatar_db_result.txt so the outcome can be
verified even when terminal output capture is unavailable.
"""
import sqlite3
from pathlib import Path

# Locate the SQLite database.
CANDIDATES = [
    Path('data/companion.db'),
    Path('backend/data/companion.db'),
    Path('companion.db'),
]
db_path = next((p for p in CANDIDATES if p.exists()), None)

report = []
if db_path is None:
    report.append('ERROR: companion.db not found in: ' + ', '.join(str(c) for c in CANDIDATES))
else:
    report.append(f'Using database: {db_path.resolve()}')
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    columns = {
        'avatar_3d_url': "TEXT DEFAULT NULL",
        'body_type': "TEXT DEFAULT 'neutral'",
        'clothing_style': "TEXT DEFAULT 'casual'",
        'clothing_description': "TEXT DEFAULT ''",
        'gender': "TEXT DEFAULT 'neutral'",
    }
    existing = {row[1] for row in cur.execute('PRAGMA table_info(characters)')}
    for col, decl in columns.items():
        if col in existing:
            report.append(f'  column {col}: already exists (skipped)')
        else:
            cur.execute(f'ALTER TABLE characters ADD COLUMN {col} {decl}')
            report.append(f'  column {col}: added')

    updates = [
        ('Greg', '/avatars/greg_3d.glb', 'athletic', 'casual',
         'Gray t-shirt, jeans, casual shoes', 'male'),
        ('Tiffany', '/avatars/tiffany_3d.glb', 'curvy', 'business',
         'White business shirt, business pants, formal shoes', 'female'),
        ('Friendly AI', '/avatars/friendly_ai_3d.glb', 'neutral', 'casual',
         'Hoodie, casual pants, casual shoes', 'female'),
    ]
    for name, url, body, style, desc, gender in updates:
        cur.execute(
            'UPDATE characters SET avatar_3d_url=?, body_type=?, clothing_style=?, '
            'clothing_description=?, gender=? WHERE name=?',
            (url, body, style, desc, gender, name),
        )
        report.append(f'  updated "{name}": {cur.rowcount} row(s)')

    conn.commit()

    report.append('\nVerification:')
    for row in cur.execute('SELECT id, name, avatar_3d_url, body_type, gender FROM characters'):
        report.append(f'  {row}')
    conn.close()

out = Path('backend/avatar_db_result.txt')
out.write_text('\n'.join(report), encoding='utf-8')
print('\n'.join(report))