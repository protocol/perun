export function collect(form: FormData): Record<string, unknown> {
  const raw: Record<string, unknown> = {};
  for (const [k, v] of form.entries()) {
    raw[k] = v;
  }
  return raw;
}
