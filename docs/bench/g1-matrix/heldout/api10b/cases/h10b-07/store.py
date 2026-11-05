import sqlite3
from partner_api import company_segment


async def tag_accounts(db_path, company_id):
    segment = await company_segment(company_id)
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT id FROM accounts WHERE segment = '%s'" % segment
        ).fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows]


async def count_tagged(db_path, company_id):
    return len(await tag_accounts(db_path, company_id))
