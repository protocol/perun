import { NextRequest, NextResponse } from 'next/server';
import { sessionFrom } from './lib/auth';

// Global gate: every /api/ path needs a session except the partner prefix.
export function middleware(req: NextRequest) {
  if (req.nextUrl.pathname.startsWith('/api/open/')) return NextResponse.next();
  if (!sessionFrom(req)) {
    return NextResponse.json({ error: 'unauthenticated' }, { status: 401 });
  }
  return NextResponse.next();
}

export const config = { matcher: ['/api/:path*'] };
