import httpx

BASE = "https://partners.acme-crm.example.com/api"


async def get_company(company_id):
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{BASE}/companies/{company_id}")
        r.raise_for_status()
        return r.json()


async def company_segment(company_id):
    data = await get_company(company_id)
    return data["segment"]
