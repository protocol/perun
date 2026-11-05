from dataclasses import dataclass, field

@dataclass
class Document:
    id: int
    owner: str
    title: str
    body: str
    shared_with: list = field(default_factory=list)

DOCS = {
    1: Document(1, "ana", "Q3 plan", "Roadmap for Acme Capital pilot"),
    2: Document(2, "ben", "Budget", "Draft numbers for Globex", ["ana"]),
    3: Document(3, "ana", "Notes", "Call notes"),
}

def get_doc(doc_id):
    return DOCS.get(doc_id)

def docs_for(user):
    return [d for d in DOCS.values() if d.owner == user or user in d.shared_with]
