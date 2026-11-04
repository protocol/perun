using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Billing;

namespace Billing.Routes;

public static class AccountRoutes
{
    public static void Map(IEndpointRouteBuilder g)
    {

        g.MapPost("/web/ext/rowan/email", (HttpContext c) => // @@R POST /web/ext/rowan/email 1
        {
            var email = c.Request.Form["email"].ToString(); // @@T positive csrf cookie-session email change accepted with no anti-forgery token
            return Results.Ok(new { updated = email.Length > 0 && email.Length <= 120 });
        });

        g.MapPost("/web/ext/sorrel/close", (HttpContext c) => // @@R POST /web/ext/sorrel/close 1
        {
            c.Response.Cookies.Delete("sid"); // @@T positive csrf cookie-session account closure reachable from a cross-site form post
            return Results.NoContent();
        });

        g.MapPost("/web/ext/tansy/email", (HttpContext c) => // @@R POST /web/ext/tansy/email 1
        {
            var email = c.Request.Form["email"].ToString(); // @@T positive csrf cookie-session email change accepted with no anti-forgery token
            return Results.Ok(new { updated = email.Length > 0 && email.Length <= 120 });
        });

        g.MapGet("/web/ext/ledger/remember", (HttpContext c) => // @@R GET /web/ext/ledger/remember 1
        {
            c.Response.Cookies.Append("sid", Store.Open(Auth.Uid(c), Auth.Role(c))); // @@T positive cookie_flags session cookie issued with default CookieOptions so no secure httponly or samesite
            return Results.NoContent();
        });

        g.MapGet("/web/ext/parcel/trust", (HttpContext c) => // @@R GET /web/ext/parcel/trust 1
        {
            c.Response.Cookies.Append("trust", Store.Open(Auth.Uid(c), Auth.Role(c)), new CookieOptions { Secure = true, SameSite = SameSiteMode.Lax, MaxAge = TimeSpan.FromDays(1) }); // @@T positive cookie_flags login token cookie readable from script because HttpOnly is not set
            return Results.NoContent();
        });
    }
}
