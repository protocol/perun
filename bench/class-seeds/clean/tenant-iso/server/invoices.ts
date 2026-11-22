import { db } from "./db";

export async function getInvoice(id: string, workspaceId: string) {
  return db.invoice.findFirst({ where: { id, workspaceId } });
}
