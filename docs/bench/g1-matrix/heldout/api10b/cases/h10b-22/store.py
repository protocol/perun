import sqlite3
from partner_api import employee_count


async def bucket_accounts(db_path, company_id):
    n = await employee_count(company_id)
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            f"SELECT id FROM accounts WHERE seats <= {n}"
        ).fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows]


async def count_bucket(db_path, company_id):
    return len(await bucket_accounts(db_path, company_id))
