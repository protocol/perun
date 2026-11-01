#!/usr/bin/env python3
"""Tests for the bundled semgrep rules perun.js.xss-url, perun.js.xss-response and perun.js.xss-markdown (js.yml).

Fixtures are annotated like semgrep's own tests: a `// ruleid: <id>` comment marks the NEXT line as a required finding, an
`// ok: <id>` comment marks the next line as one that must stay clean, and every unannotated line must stay clean too. All names
and values are fictional. perun.js.xss skips no test path, so these rules skip none either (checked offline). RULES=<dir>
checks another copy of the rules (used to show the cases fail without them). The live check needs semgrep and prints SKIP
without it (CI installs none); the offline checks always run. Plain asserts."""
import json, os, re, shutil, subprocess, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.environ.get("RULES") or os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint")
URL, RESP, MD = "perun.js.xss-url", "perun.js.xss-response", "perun.js.xss-markdown"
IDS = (URL, RESP, MD)

# Browser URL input: a search param (through URLSearchParams, held in a variable or not), a hash, or a value destructured from
# location, reaching an HTML sink.
URL_TS = r'''
const out = document.getElementById("acme-out")!;

// A search param reaches innerHTML directly, through a variable, in a template literal, after decodeURIComponent, trim, slice
// or substring, through a ?? default and through getAll(...).join(...).
export function acmeSearchDirect() {
  // ruleid: perun.js.xss-url
  out.innerHTML = new URLSearchParams(location.search).get("q")!;
}
export function acmeSearchVariable() {
  const q = new URLSearchParams(window.location.search).get("q");
  // ruleid: perun.js.xss-url
  out.innerHTML = q as string;
}
export function acmeParamsVariable() {
  const params = new URLSearchParams(document.location.search);
  const name = params.get("name") ?? "hello";
  // ruleid: perun.js.xss-url
  out.innerHTML = `<h1>${name}</h1>`;
}
export function acmeGetAll() {
  const tags = new URLSearchParams(location.search).getAll("tag").join(", ");
  // ruleid: perun.js.xss-url
  out.innerHTML = tags;
}
export function acmeStringMethods() {
  const raw = new URLSearchParams(location.search).get("q") ?? "";
  // ruleid: perun.js.xss-url
  out.innerHTML = decodeURIComponent(raw);
  // ruleid: perun.js.xss-url
  out.innerHTML = raw.trim();
  // ruleid: perun.js.xss-url
  out.innerHTML = raw.slice(1);
  // ruleid: perun.js.xss-url
  out.innerHTML = raw.substring(1, 40);
}
export function acmeDefault() {
  // ruleid: perun.js.xss-url
  out.innerHTML = new URLSearchParams(location.search).get("q") ?? "hello";
}

// A hash, decoded or not, reaches document.write, document.writeln and the second argument of insertAdjacentHTML.
export function acmeHash() {
  // ruleid: perun.js.xss-url
  document.write(decodeURIComponent(location.hash.slice(1)));
  // ruleid: perun.js.xss-url
  document.writeln(window.location.hash);
  // ruleid: perun.js.xss-url
  out.insertAdjacentHTML("beforeend", document.location.hash.substring(1));
}

// Concatenation onto innerHTML and an outerHTML write are sinks too.
export function acmeConcat() {
  const q = new URLSearchParams(location.search).get("q");
  // ruleid: perun.js.xss-url
  out.innerHTML += "<li>" + q + "</li>";
  // ruleid: perun.js.xss-url
  out.outerHTML = `<div>${q}</div>`;
}

// A search or hash destructured from location or window.location is a source.
export function acmeDestructured() {
  const { search, hash } = window.location;
  // ruleid: perun.js.xss-url
  out.innerHTML = new URLSearchParams(search).get("q")!;
  // ruleid: perun.js.xss-url
  out.innerHTML = hash;
}
// A let or var declaration destructures the same way.
export function acmeDestructuredLet() {
  let { search } = location;
  // ruleid: perun.js.xss-url
  out.innerHTML = new URLSearchParams(search).get("q")!;
  var { hash } = window.location;
  // ruleid: perun.js.xss-url
  out.innerHTML = hash;
}

// A __html value (an object literal, or a property assigned on an object) is a sink too: it is what dangerouslySetInnerHTML renders.
export function acmeHtmlObject() {
  // ruleid: perun.js.xss-url
  const markup = { __html: new URLSearchParams(location.search).get("q") ?? "" };
  return markup;
}
export function acmeHtmlProperty() {
  const markup: { __html?: string } = {};
  // ruleid: perun.js.xss-url
  markup.__html = decodeURIComponent(location.hash.slice(1));
  return markup;
}
export function acmeHtmlClean() {
  // ok: perun.js.xss-url
  const constant = { __html: "<b>hello</b>" };
  // ok: perun.js.xss-url
  const purified = { __html: DOMPurify.sanitize(location.hash) };
  // ok: perun.js.xss-url
  const path = { __html: location.pathname };
  return [constant, purified, path];
}

// The same values into a property that is not HTML stay clean.
export function acmeNotHtml() {
  const q = new URLSearchParams(location.search).get("q") ?? "";
  // ok: perun.js.xss-url
  out.textContent = q;
  // ok: perun.js.xss-url
  out.innerText = decodeURIComponent(q);
  // ok: perun.js.xss-url
  out.title = q;
  // ok: perun.js.xss-url
  (out as HTMLInputElement).value = location.hash;
}

// A redirect is not this rule.
export function acmeRedirect() {
  const next = new URLSearchParams(location.search).get("next") ?? "/";
  // ok: perun.js.xss-url
  location.href = next;
  // ok: perun.js.xss-url
  window.location.assign(next);
}

// Each sanitizer clears the value.
export function acmeSanitized() {
  const q = new URLSearchParams(location.search).get("q") ?? "";
  // ok: perun.js.xss-url
  out.innerHTML = escapeHtml(q);
  // ok: perun.js.xss-url
  out.innerHTML = DOMPurify.sanitize(q);
  // ok: perun.js.xss-url
  out.innerHTML = sanitizeHtml(location.hash);
  // ok: perun.js.xss-url
  out.innerHTML = `<a href="/acme?q=${encodeURIComponent(q)}">acme</a>`;
  // ok: perun.js.xss-url
  out.innerHTML = `${Number(q)} items`;
  // ok: perun.js.xss-url
  out.innerHTML = `page ${parseInt(q, 10)}`;
  // ok: perun.js.xss-url
  out.innerHTML = `rate ${parseFloat(q)}`;
}

// Reads of pathname or href only, whole or destructured, are not sources.
export function acmePathOnly() {
  const { pathname } = window.location;
  // ok: perun.js.xss-url
  out.innerHTML = location.pathname;
  // ok: perun.js.xss-url
  out.innerHTML = window.location.href;
  // ok: perun.js.xss-url
  out.innerHTML = pathname;
}

// Constant strings into the sinks stay clean.
export function acmeConstant() {
  // ok: perun.js.xss-url
  out.innerHTML = "hello";
  // ok: perun.js.xss-url
  out.innerHTML += `<i>acme</i>`;
  // ok: perun.js.xss-url
  document.write("<p>hello</p>");
  // ok: perun.js.xss-url
  out.insertAdjacentHTML("beforeend", "<b>acme</b>");
}
'''

URL_JS = r'''
const out = document.getElementById("acme-out");

export function acmeSearch() {
  const params = new URLSearchParams(location.search);
  // ruleid: perun.js.xss-url
  out.innerHTML = params.get("q");
  // ruleid: perun.js.xss-url
  out.innerHTML = `<b>${params.get("q") ?? "hello"}</b>`;
  // ruleid: perun.js.xss-url
  out.innerHTML += decodeURIComponent(params.get("q").trim());
}
export async function acmeAwait() {
  const q = await Promise.resolve(new URLSearchParams(window.location.search).get("q"));
  // ruleid: perun.js.xss-url
  out.innerHTML = q;
}
export function acmeHash() {
  // ruleid: perun.js.xss-url
  document.write(decodeURIComponent(location.hash.slice(1)));
  // ruleid: perun.js.xss-url
  out.insertAdjacentHTML("afterbegin", location.hash.substring(1));
}
export function acmeClean() {
  const q = new URLSearchParams(location.search).get("q");
  // ok: perun.js.xss-url
  out.textContent = q;
  // ok: perun.js.xss-url
  location.href = q;
  // ok: perun.js.xss-url
  out.innerHTML = escapeHtml(q);
  // ok: perun.js.xss-url
  document.write("hello");
}
'''

# The same URL input written into dangerouslySetInnerHTML in a component.
URL_TSX = r'''
import DOMPurify from "dompurify";

export function AcmeSearchHtml() {
  // ruleid: perun.js.xss-url
  return <div dangerouslySetInnerHTML={{ __html: new URLSearchParams(window.location.search).get("q") ?? "" }} />;
}
export function AcmeHashHtml() {
  const { hash } = window.location;
  // ruleid: perun.js.xss-url
  return <p dangerouslySetInnerHTML={{ __html: decodeURIComponent(hash.slice(1)) }} />;
}
export function AcmeHashPurified() {
  // ok: perun.js.xss-url
  return <div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(location.hash) }} />;
}
export function AcmeHashConstant() {
  // ok: perun.js.xss-url
  return <div dangerouslySetInnerHTML={{ __html: "<b>hello</b>" }} />;
}
export function AcmeHashText() {
  // ok: perun.js.xss-url
  return <div title={new URLSearchParams(location.search).get("q") ?? ""}>{location.hash}</div>;
}
'''

# App-router handlers: a request URL param in the body of a Response typed text/html by an inline headers literal.
RESP_TS = r'''
import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const name = request.nextUrl.searchParams.get("name") ?? "hello";
  // ruleid: perun.js.xss-response
  return new NextResponse(`<h1>${name}</h1>`, { headers: { "Content-Type": "text/html" } });
}
export async function POST(req: Request) {
  const q = new URL(req.url).searchParams.get("q") as string;
  // ruleid: perun.js.xss-response
  return new Response("<p>" + q + "</p>", { status: 200, headers: { "content-type": "text/html; charset=utf-8" } });
}
// A body built over several statements, from getAll(...).join(...) and a searchParams destructured from the URL.
export async function PUT(request: Request) {
  const { searchParams } = new URL(request.url);
  const tags = searchParams.getAll("tag").join(", ");
  let html = "<ul>";
  html += `<li>${tags}</li>`;
  html += "</ul>";
  // ruleid: perun.js.xss-response
  return new Response(html, { headers: { "CONTENT-TYPE": "text/html" } });
}
// Any handler parameter name; the searchParams object held in a variable; an await-ed value; a quoted key and value.
export async function PATCH(incoming: NextRequest) {
  const session = await acmeSession();
  const sp = incoming.nextUrl.searchParams;
  const body = await acmeRender(sp.get("x")!.substring(0, 20));
  // ruleid: perun.js.xss-response
  return new NextResponse(body, { status: 200, headers: { 'Content-Type': 'text/html' } });
}
export async function DELETE(request: Request) {
  const url = new URL(request.url);
  const label = url.searchParams.get("label")?.trim() ?? "";
  // ruleid: perun.js.xss-response
  return new Response(`<p>${label}</p>`, { headers: { "Content-Type": "text/html", "Cache-Control": "no-store" } });
}
// searchParams destructured from request.nextUrl, and from the URL in a let declaration.
export async function acmeNextUrlDestructured(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  // ruleid: perun.js.xss-response
  return new NextResponse(`<p>${searchParams.get("q")}</p>`, { headers: { "Content-Type": "text/html" } });
}
export async function acmeLetDestructured(request: Request) {
  let { searchParams } = new URL(request.url);
  // ruleid: perun.js.xss-response
  return new Response(`<p>${searchParams.get("q")}</p>`, { headers: { "Content-Type": "text/html" } });
}
// new URL with a base argument is a source in all three URL forms.
export async function acmeBaseDirect(request: Request) {
  const q = new URL(request.url, acmeOrigin).searchParams.get("q") ?? "";
  // ruleid: perun.js.xss-response
  return new Response(q, { headers: { "Content-Type": "text/html" } });
}
export async function acmeBaseVariable(request: Request) {
  const url = new URL(request.url, acmeOrigin);
  const q = url.searchParams.get("q") ?? "";
  // ruleid: perun.js.xss-response
  return new Response(q, { headers: { "Content-Type": "text/html" } });
}
export async function acmeBaseDestructured(request: Request) {
  const { searchParams } = new URL(request.url, acmeOrigin);
  // ruleid: perun.js.xss-response
  return new Response(searchParams.get("q") ?? "", { headers: { "Content-Type": "text/html" } });
}
export async function acmeBasePath(request: Request) {
  const url = new URL(request.url, acmeOrigin);
  // ok: perun.js.xss-response
  return new Response(url.pathname, { headers: { "Content-Type": "text/html" } });
}
// The media type is matched in any case and after leading spaces, as a browser reads it.
export async function acmeTypeCase(request: Request) {
  const q = new URL(request.url).searchParams.get("q") ?? "";
  // ruleid: perun.js.xss-response
  return new Response(q, { headers: { "Content-Type": "TEXT/Html; charset=utf-8" } });
}
export async function acmeTypeSpaces(request: Request) {
  const q = new URL(request.url).searchParams.get("q") ?? "";
  // ruleid: perun.js.xss-response
  return new Response(q, { headers: { "Content-Type": "  text/html" } });
}
export async function acmeTypeSpacesPlain(request: Request) {
  const q = new URL(request.url).searchParams.get("q") ?? "";
  // ok: perun.js.xss-response
  return new Response(q, { headers: { "Content-Type": "  TEXT/Plain" } });
}

export async function acmeJson(request: NextRequest) {
  const q = request.nextUrl.searchParams.get("q");
  // ok: perun.js.xss-response
  return Response.json({ q });
}
export async function acmeNextJson(request: NextRequest) {
  const q = new URL(request.url).searchParams.get("q");
  // ok: perun.js.xss-response
  return NextResponse.json({ q });
}
export async function acmeNoInit(request: Request) {
  const q = new URL(request.url).searchParams.get("q");
  // ok: perun.js.xss-response
  return new Response(`<p>${q}</p>`);
}
export async function acmeOtherTypes(request: Request) {
  const q = new URL(request.url).searchParams.get("q") ?? "";
  const html = true;
  if (html) {
    // ok: perun.js.xss-response
    return new Response(q, { headers: { "Content-Type": "text/plain" } });
  }
  // ok: perun.js.xss-response
  return new Response(JSON.stringify({ q }), { headers: { "Content-Type": "application/json" } });
}
export async function acmeSanitized(request: Request) {
  const q = new URL(request.url).searchParams.get("q") ?? "";
  const n = parseInt(request.nextUrl.searchParams.get("n") ?? "0", 10);
  // ok: perun.js.xss-response
  return new Response(`<p>${escapeHtml(q)}</p><p>${Number(q)}</p><p>${n}</p>`, { headers: { "Content-Type": "text/html" } });
}
export async function acmeSanitizedMore(request: Request) {
  const q = new URL(request.url).searchParams.get("q") ?? "";
  // ok: perun.js.xss-response
  return new Response(DOMPurify.sanitize(q) + sanitizeHtml(q) + encodeURIComponent(q) + parseFloat(q), { headers: { "Content-Type": "text/html" } });
}
// Known limit: headers built elsewhere are not followed, so this is not reported.
export async function acmeHeadersElsewhere(request: Request) {
  const q = new URL(request.url).searchParams.get("q");
  const headers = { "Content-Type": "text/html" };
  // ok: perun.js.xss-response
  return new Response(`<p>${q}</p>`, { headers });
}
// A constant body and a header that is not the content type stay clean.
export async function acmeConstant(request: Request) {
  const q = new URL(request.url).searchParams.get("q") ?? "";
  // ok: perun.js.xss-response
  return new Response("<p>hello</p>", { headers: { "Content-Type": "text/html", "X-Acme-Query": q } });
}
'''

RESP_JS = r'''
import { NextResponse } from "next/server";

export async function GET(request) {
  const name = request.nextUrl.searchParams.get("name");
  // ruleid: perun.js.xss-response
  return new Response(`<h1>${name}</h1>`, { headers: { "Content-Type": "text/html" } });
}
export async function POST(req) {
  const q = await Promise.resolve(new URL(req.url).searchParams.getAll("q").join(" "));
  // ruleid: perun.js.xss-response
  return new NextResponse("<p>" + q + "</p>", { headers: { "content-type": "text/html; charset=utf-8" } });
}
export async function acmeClean(request) {
  const q = request.nextUrl.searchParams.get("q");
  // ok: perun.js.xss-response
  return NextResponse.json({ q });
}
export async function acmePlain(request) {
  const q = new URL(request.url).searchParams.get("q");
  // ok: perun.js.xss-response
  return new Response(q, { headers: { "Content-Type": "text/plain" } });
}
export async function acmeBase(request) {
  const q = new URL(request.url, acmeOrigin).searchParams.get("q");
  // ruleid: perun.js.xss-response
  return new Response(q, { headers: { "Content-Type": "text/html" } });
}
'''

# Markdown rendered from non-constant input and injected without a sanitizer.
MD_TSX = r'''
import { marked } from "marked";
import DOMPurify from "dompurify";
import showdown from "showdown";
import MarkdownIt from "markdown-it";
import fs from "node:fs";
import { readFile } from "node:fs/promises";

const acmeDocs = fs.readFileSync("docs/acme.md", "utf8");

export function AcmeProp({ text }: { text: string }) {
  // ruleid: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: marked.parse(text) as string }} />;
}
export function AcmeState() {
  const [text] = useState("hello");
  // ruleid: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: marked(text).trim() }} />;
}
export async function AcmeFetch({ id }: { id: string }) {
  const res = await fetch(`/api/acme/${id}`);
  const md = await res.text();
  // ruleid: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: await marked.parse(md) }} />;
}
export function AcmeArgument(md: string) {
  const html = marked.parseInline(md);
  // ruleid: perun.js.xss-markdown
  const markup = { __html: html.slice(0, 200) };
  return <span dangerouslySetInnerHTML={markup} />;
}
export function AcmeShowdown({ text }: { text: string }) {
  const converter = new showdown.Converter();
  // ruleid: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: converter.makeHtml(text) }} />;
}
export function AcmeShowdownInline({ text }: { text: string }) {
  // ruleid: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: new showdown.Converter().makeHtml(text) }} />;
}
export async function acmeDom(md: string) {
  const out = document.getElementById("acme-out")!;
  // ruleid: perun.js.xss-markdown
  out.innerHTML = marked.parse(md) as string;
  // ruleid: perun.js.xss-markdown
  out.insertAdjacentHTML("beforeend", await marked.parseInline(md));
  // ruleid: perun.js.xss-markdown
  out.innerHTML += marked(md);
}

export function AcmeSanitized({ text }: { text: string }) {
  // ok: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(marked.parse(text) as string) }} />;
}
export function AcmeSanitizedHtml({ text }: { text: string }) {
  // ok: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: sanitizeHtml(marked(text)) }} />;
}
export function AcmeLiteral() {
  // ok: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: marked.parse("# acme") as string }} />;
}
export function AcmeMarkdownIt({ text }: { text: string }) {
  const md = new MarkdownIt();
  // ok: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: md.render(text) }} />;
}
export function AcmeNotMarkdown({ post }: { post: { body: string } }) {
  // ok: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: post.body }} />;
}
export function AcmeText({ text }: { text: string }) {
  const out = document.getElementById("acme-out")!;
  // ok: perun.js.xss-markdown
  out.textContent = marked.parse(text) as string;
  return null;
}
// Markdown read from a repo file with fs.readFileSync or readFile (as the argument, or bound to a variable first) is skipped.
export function AcmeDocSync() {
  const md = fs.readFileSync("docs/acme.md", "utf8");
  // ok: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: marked.parse(md) as string }} />;
}
export async function AcmeDocAsync() {
  const md = await readFile("docs/acme.md", "utf8");
  // ok: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: await marked.parse(md) }} />;
}
export async function AcmeDocPromises() {
  const md = await fs.promises.readFile("docs/acme.md", "utf8");
  // ok: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: marked(md) }} />;
}
export function AcmeDocInline() {
  // ok: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: marked.parse(fs.readFileSync("docs/acme.md", "utf8")) as string }} />;
}
export function AcmeDocModule() {
  // ok: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: marked(acmeDocs) }} />;
}
export function AcmeDocTyped() {
  const body: string = fs.readFileSync("docs/acme.md", "utf8");
  // ok: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: marked(body) }} />;
}
// Only a const declared from a file read is skipped. A let or var variable is reported, reassigned or not, and so is a read
// through a helper or a front-matter parser.
export function AcmeDocReassigned({ text }: { text: string }) {
  let body = fs.readFileSync("docs/acme.md", "utf8");
  body = text;
  // ruleid: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: marked.parse(body) as string }} />;
}
export function AcmeDocLet() {
  let body = fs.readFileSync("docs/acme.md", "utf8");
  // ruleid: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: marked(body) }} />;
}
export function AcmeDocVar() {
  var body = fs.readFileSync("docs/acme.md", "utf8");
  // ruleid: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: marked(body) }} />;
}
export function AcmeDocHelper() {
  const body = acmeLoadDoc("docs/acme.md");
  // ruleid: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: marked(body) }} />;
}
export function AcmeDocFrontMatter() {
  const { content } = acmeParse(fs.readFileSync("docs/acme.md", "utf8"));
  // ruleid: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: marked(content) }} />;
}
// A __html property assigned on an object is a sink.
export function AcmeProperty({ text }: { text: string }) {
  const markup: { __html?: string } = {};
  // ruleid: perun.js.xss-markdown
  markup.__html = marked(text);
  return <div dangerouslySetInnerHTML={markup} />;
}
'''

MD_JSX = r'''
import fs from "node:fs";
import { marked } from "marked";
import showdown from "showdown";
import DOMPurify from "dompurify";

export function AcmeProp({ text }) {
  // ruleid: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: marked.parse(text) }} />;
}
export async function AcmeFetch({ url }) {
  const md = await (await fetch(url)).text();
  // ruleid: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: await marked.parse(md) }} />;
}
export function AcmeShowdown({ text }) {
  const converter = new showdown.Converter();
  // ruleid: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: converter.makeHtml(text) }} />;
}
export function AcmeSafe({ text }) {
  // ok: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(marked.parse(text)) }} />;
}
export function AcmeLiteral() {
  // ok: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: marked("# hello") }} />;
}
export function AcmeDoc() {
  const body = fs.readFileSync("docs/acme.md", "utf8");
  // ok: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: marked(body) }} />;
}
export function AcmeDocReassigned({ text }) {
  let body = fs.readFileSync("docs/acme.md", "utf8");
  body = text;
  // ruleid: perun.js.xss-markdown
  return <div dangerouslySetInnerHTML={{ __html: marked(body) }} />;
}
'''

FILES = {
    "app/ui/search.ts": URL_TS, "app/ui/search.js": URL_JS, "app/api/acme/route.ts": RESP_TS, "app/api/acme/route.js": RESP_JS,
    "app/ui/AcmeMarkdown.tsx": MD_TSX, "app/ui/AcmeMarkdown.jsx": MD_JSX, "app/ui/AcmeHash.tsx": URL_TSX,
}
ANN = re.compile(r"^\s*(?://|#)\s*(ruleid|ok):\s*(\S+)\s*$")


def annotated(body, kind):
    """(line, rule id) of the line each `// <kind>: <id>` comment points at (the next one); the id must be one of ours."""
    out = {(i + 1, m.group(2)) for i, l in enumerate(body.split("\n"), 1) if (m := ANN.match(l)) and m.group(1) == kind}
    assert {r for _, r in out} <= set(IDS), out
    return out


# Offline: the floor of 3 findings and 3 near misses per rule, counted over distinct fixtures; every fixture has both kinds.
for rid in IDS:
    for kind in ("ruleid", "ok"):
        n = sum(1 for body in {*FILES.values()} for _, r in annotated(body, kind) if r == rid)
        assert n >= 3, (rid, kind, n)
assert all(annotated(b, "ok") and annotated(b, "ruleid") for b in FILES.values())
if shutil.which("semgrep"):
    with tempfile.TemporaryDirectory() as d:
        for p, body in FILES.items():
            os.makedirs(os.path.dirname(os.path.join(d, p)), exist_ok=True)
            open(os.path.join(d, p), "w").write(body)
        env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
        run = subprocess.run(["semgrep", "--config", RULES, "--metrics=off", "--disable-version-check", "--json", "--quiet", "--", *FILES],
                             capture_output=True, text=True, env=env, cwd=d)
        r = json.loads(run.stdout)
    assert not r["errors"], r["errors"]
    got = set()  # semgrep prefixes a rule id with each local config's directory: keep the perun.<lang>.<name> tail
    for x in r["results"]:
        rid = "perun." + x["check_id"].rsplit("perun.", 1)[-1]
        if rid in IDS:
            got.add((x["path"], x["start"]["line"], rid))
    want = {(p, ln, rid) for p, body in FILES.items() for ln, rid in annotated(body, "ruleid")}
    assert got == want, ("unexpected", sorted(got - want), "missed", sorted(want - got))
else:
    print("SKIP: semgrep not installed; the live fixture check did not run, the offline checks below do")

# Offline: ids, order, message, languages, severity, the sanitizer list and the test-path convention, then the regexes (semgrep
# anchors metavariable-regex at the start, as Python's re.match does) that carry the precision. CI installs no semgrep, so each
# guard the live fixtures prove is pinned here too: dropping one fails this file even when the live part is skipped.
JS = open(os.path.join(RULES, "js.yml")).read()
block = lambda rid: JS.split(f"- id: {rid}\n")[1].split("\n- id:")[0]
paths = lambda b: re.search(r"(?:^|[\s{,])[\"']?paths[\"']?\s*:", b)  # a paths key in any YAML style: block, flow or quoted
rx = lambda b, mv: re.findall(rf"metavariable: \${mv}\n\s+regex: (.*)", b)
ids = re.findall(r"^- id: (\S+)$", JS, re.M)
assert ids[ids.index("perun.js.xss") + 1:][:3] == list(IDS), "the three rules follow perun.js.xss, in this order"
assert sum(1 for l in JS.split("\n") if l.startswith("# Also") and all(i[len("perun.js."):] in l for i in IDS)) == 1, "one header line names all three"
SANITIZERS = ("DOMPurify.sanitize(...)", "sanitizeHtml(...)", "escapeHtml(...)", "encodeURIComponent(...)", "Number(...)", "parseInt(...)", "parseFloat(...)")
HTML_SINKS = ("'({ ..., __html: $S, ... })'", "$O.__html = $S")
DOM_SINKS = ("$E.innerHTML = $S", "$E.innerHTML += $S", "$E.outerHTML = $S", "$E.insertAdjacentHTML($P, $S)", "document.write($S)", "document.writeln($S)")
for rid in IDS:
    b = block(rid)
    assert JS.count(f"- id: {rid}\n") == 1 and "  mode: taint\n" in b and "  languages: [javascript, typescript]\n" in b and "  severity: WARNING\n" in b, rid
    msg = re.search(r"\n  message: (.+)\n", b)[1]
    assert msg.endswith(".") and ". " not in msg and len(msg.split()) >= 5, f"{rid} has a one-sentence message"
    assert not paths(b) and not paths(block("perun.js.xss")), f"{rid} skips no test path, like perun.js.xss"
    san = b.split("  pattern-sanitizers:\n")[1].split("\n- id:")[0]
    assert re.findall(r"- pattern: (.*)", san) == list(SANITIZERS), f"{rid} sanitizers"
    assert "focus-metavariable: $S" in b
for rid in (URL, MD):
    assert all(f"- pattern: {s}\n" in block(rid) for s in DOM_SINKS + HTML_SINKS), f"{rid} DOM and __html sinks"
ub, rb, mb = block(URL), block(RESP), block(MD)
assert all(f"- pattern: {s}\n" in ub for s in ("location.search", "location.hash", "window.location.search", "window.location.hash",
           "document.location.search", "document.location.hash")), "location search and hash under each global"
assert "'{ ..., $K, ... } = location'\n" in ub and "'{ ..., $K, ... } = window.location'\n" in ub and rx(ub, "K") == ["^(?:search|hash)$"], "destructured search or hash only"
assert "pathname" not in ub and "href" not in ub, "pathname and href are not sources, a redirect is not a sink"
assert "$R.nextUrl.searchParams" in rb and "new URL($R.url, ...).searchParams" in rb and "$U = new URL($R.url, ...);" in rb, "request URL sources on any handler name, with or without a base argument"
assert "'{ ..., $K, ... } = new URL($R.url, ...)'" in rb and "'{ ..., $K, ... } = $R.nextUrl'" in rb and rx(rb, "K") == ["^searchParams$"], "searchParams destructured from the URL"
assert "new Response($S, { ..., headers: { ..., $HK: $HV, ... }, ... })" in rb and "new NextResponse($S, { ..., headers: { ..., $HK: $HV, ... }, ... })" in rb, "an inline headers literal in the same call"
assert ".json(" not in rb and "# Only an inline object-literal headers value counts; headers built elsewhere" in rb, "limit stated in the rule comment"
hk, hv = rx(rb, "HK")[0], rx(rb, "HV")[0]
assert all(re.match(hk, s) for s in ('"Content-Type"', "'content-type'", '"CONTENT-TYPE"', "content-type")), hk
assert not any(re.match(hk, s) for s in ('"Content-Length"', '"X-Content-Type-Options"', '"content-type-x"', '"Accept"')), hk
assert all(re.match(hv, s) for s in ('"text/html"', "'text/html; charset=utf-8'", "`text/html`", '"TEXT/Html"', '"  text/html"', "' Text/HTML; charset=utf-8'")), hv
assert not any(re.match(hv, s) for s in ('"text/plain"', '"application/json"', '"x-text/html"', '" text/plain"', "html", "text")), hv
for src in ("marked($A, ...)", "marked.parse($A, ...)", "marked.parseInline($A, ...)", "$C.makeHtml($A, ...)"):
    assert f"- pattern: {src}\n" in mb, src
assert 'pattern-not: $F("...", ...)' in mb, "a string literal is not a source"
assert "            const $A = $V;\n" in mb, "a variable read from a file is skipped only when it is a const"
assert ".render(" not in mb, "markdown-it render escapes raw HTML, so it is not a source"
ma, mv = rx(mb, "A")[0], rx(mb, "V")[0]
read = ("fs.readFileSync(p)", 'fs.readFileSync("a.md", "utf8")', "readFileSync(p)", 'await readFile("a.md", "utf8")', "await fs.promises.readFile(p)", "fs.readFile(p)")
assert not any(re.match(ma, s) for s in read), ma  # an argument that is a file read is skipped
assert all(re.match(ma, s) for s in ("text", "props.text", "await res.text()", "readFileSyncX(p)", "fetchText(url)", "readFiles(p)", '"# " + title')), ma
assert all(re.match(mv, s) for s in read) and not any(re.match(mv, s) for s in ("text", "await res.text()", "readFileSyncX(p)", "fetchText(url)")), mv
print("ok")
