### Added
- Semgrep rules `llm-context.yml`: flag system or developer prompts that embed credentials or are returned to clients, and vector-store reads (Pinecone, Chroma, LangChain, Weaviate, Qdrant) with no tenant, user or namespace filter, for Python and JS/TS.
