export async function POST(request: Request) {
  const form = await request.formData();
  const file = form.get("avatar") as File;
  const bytes = await file.arrayBuffer();
  return Response.json({ size: bytes.byteLength });
}
