TICKETS = {
    10: {"id": 10, "reporter": "carla", "subject": "Printer jam", "state": "open", "staff_note": "check tray"},
    11: {"id": 11, "reporter": "dev", "subject": "VPN drop", "state": "open", "staff_note": ""},
    12: {"id": 12, "reporter": "carla", "subject": "New badge", "state": "closed", "staff_note": "done"},
}
ROLES = {"carla": "member", "dev": "member", "sam": "agent"}
TOKENS = {"c-1": "carla", "d-1": "dev", "s-1": "sam"}

def find(ticket_id):
    return TICKETS.get(ticket_id)

def by_reporter(name):
    return [t for t in TICKETS.values() if t["reporter"] == name]
