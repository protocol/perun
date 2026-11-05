from partner_client import fetch_region_rates
from rate_store import connect, replace_rates, average_for

def refresh(country):
    conn = connect()
    replace_rates(conn, fetch_region_rates(country))
    return conn

def cheapest_regions(conn, rows, limit=5):
    ranked = sorted(rows, key=lambda r: r["rate"])[:limit]
    out = []
    for row in ranked:
        region = row["region"]
        cur = conn.execute(
            f"SELECT COUNT(*) FROM rates WHERE region = '{region}' AND rate <= {row['rate']}"
        )
        out.append({"region": region, "rank": cur.fetchone()[0], "avg": average_for(conn, region)})
    return out

def build(country):
    rows = fetch_region_rates(country)
    conn = refresh(country)
    return cheapest_regions(conn, rows)
