from pinecone import Pinecone

index = Pinecone(api_key="demo").Index("acme-docs")


def search(embedding):
    return index.query(vector=embedding, top_k=5, include_metadata=True)
