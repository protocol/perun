using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Billing;

namespace Billing.Routes;

public static class ProfileRoutes
{
    public static void Map(IEndpointRouteBuilder g)
    {

        g.MapPost("/web/ext/yarrow/phone", (HttpContext c) => // @@R POST /web/ext/yarrow/phone 1
        {
            var got = Encoding.UTF8.GetBytes(c.Request.Headers["X-CSRF-Token"].ToString());
            if (!CryptographicOperations.FixedTimeEquals(got, Encoding.UTF8.GetBytes(Auth.Csrf(c)))) return Results.StatusCode(403); // @@T decoy csrf per-session token compared in constant time and a missing header is rejected
            return Results.Ok(new { updated = c.Request.Form["phone"].ToString().Length <= 20 });
        });

        g.MapPost("/web/ext/orchard/nickname", ([Microsoft.AspNetCore.Mvc.FromForm] string nickname) => // @@R POST /web/ext/orchard/nickname 1 ; T decoy csrf form binding keeps antiforgery validation on for this group and the session cookie is configured with SameSite strict
        {
            return Results.Ok(new { updated = nickname.Length is > 0 and <= 40 });
        });

        g.MapGet("/web/ext/crate/rotate", (HttpContext c) => // @@R GET /web/ext/crate/rotate 1
        {
            c.Session.SetInt32("uid", Auth.Uid(c)); // @@T decoy cookie_flags the session cookie attributes come from AddSession options with HttpOnly SecurePolicy Always and SameSite Strict
            return Results.NoContent();
        });

        g.MapGet("/web/ext/depot/keep", (HttpContext c) => // @@R GET /web/ext/depot/keep 1
        {
            c.Response.Cookies.Append("keep", Convert.ToHexString(RandomNumberGenerator.GetBytes(16)), new CookieOptions { HttpOnly = true, Secure = true, SameSite = SameSiteMode.Strict, MaxAge = TimeSpan.FromHours(1) }); // @@T decoy cookie_flags httponly secure and samesite strict set together with a one hour lifetime
            return Results.NoContent();
        });
    }
}
