import { Document } from "@langchain/core/documents";

export async function search(store: any, question: string): Promise<Document[]> {
  return store.similaritySearch(question, 4);
}
