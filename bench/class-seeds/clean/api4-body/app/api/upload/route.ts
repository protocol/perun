const MAX = 1_000_000;
export async function POST(request: Request) {
  const reader = request.body!.getReader();
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.length;
    if (total > MAX) return new Response("too large", { status: 413 });
  }
  return Response.json({ size: total });
}
