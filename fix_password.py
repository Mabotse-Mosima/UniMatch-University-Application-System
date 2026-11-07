import sys, os
sys.path.insert(0, 'src')
from dotenv import load_dotenv
load_dotenv()
from unimatch.auth import hash_password
from sqlalchemy import create_engine, text

engine = create_engine(os.environ['DATABASE_URL'])
new_hash = hash_password('SecurePass1!')

with engine.connect() as conn:
    # First see what accounts exist
    rows = conn.execute(text('SELECT email, role FROM accounts LIMIT 20')).fetchall()
    print('ACCOUNTS:')
    for r in rows:
        print(' ', r)
    
    # Reset admin password
    result = conn.execute(
        text("UPDATE accounts SET password_hash=:h WHERE email='admin@example.com'"),
        {'h': new_hash}
    )
    conn.commit()
    print(f'Updated {result.rowcount} row(s)')
