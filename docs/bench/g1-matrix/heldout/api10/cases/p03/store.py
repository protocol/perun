import sqlite3

from client import get_region_info


def purge_region(db, code):
    info = get_region_info(code)
    region = info["region"]
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM cache WHERE region = '" + region + "'")
    conn.commit()
    conn.close()
    return region
