from pinecone import Pinecone

index = Pinecone(api_key="demo").Index("acme-docs")


def search(embedding, tenant_id):
    return index.query(vector=embedding, top_k=5, namespace=tenant_id, include_metadata=True)
