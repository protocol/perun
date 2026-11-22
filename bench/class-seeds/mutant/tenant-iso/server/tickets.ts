import { prisma } from "./client";

export async function closeTicket(id: string) {
  return prisma.ticket.updateMany({ where: { id }, data: { open: false } });
}
