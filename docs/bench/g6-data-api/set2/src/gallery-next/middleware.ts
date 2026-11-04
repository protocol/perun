import { NextRequest, NextResponse } from 'next/server';

export function middleware(req: NextRequest) {
  const auth = req.headers.get('authorization') ?? '';
  if (!auth.startsWith('Bearer ')) {
    return NextResponse.json({ error: 'sign in first' }, { status: 401 });
  }
  return NextResponse.next();
}

export const config = {
  matcher: ['/api/v2/albums/:path*', '/api/v2/photos/:path*', '/api/v2/admin/:path*', '/api/v2/users/:path*'],
};
