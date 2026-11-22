import { db } from "./db";

export async function getInvoice(id: string) {
  return db.invoice.findUnique({ where: { id } });
}
