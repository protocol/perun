import httpx

BASE = "https://partners.acme-crm.example.com/api"


async def get_company(company_id):
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{BASE}/companies/{company_id}")
        r.raise_for_status()
        return r.json()


async def employee_count(company_id):
    data = await get_company(company_id)
    return int(data["employees"])
