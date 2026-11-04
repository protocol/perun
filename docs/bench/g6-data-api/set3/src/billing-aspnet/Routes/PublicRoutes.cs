using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Billing;

namespace Billing.Routes;

public static class PublicRoutes
{
    public static void Map(IEndpointRouteBuilder g)
    {

        g.MapGet("/api/mesa/summary", () => Results.Ok(Store.Rows.Values.Select(r => new { r.Id, r.Label }))); // @@R GET /api/mesa/summary 0 ; T positive missing_authn endpoint is mapped on the bare app with no authorization and lists internal rows to anyone

        g.MapGet("/api/prairie/summary", () => Results.Ok(Store.Rows.Values.Select(r => new { r.Id, r.Label }))); // @@R GET /api/prairie/summary 0 ; T positive missing_authn endpoint is mapped on the bare app with no authorization and lists internal rows to anyone

        g.MapPost("/auth/nettle-pin", (HttpContext c) => // @@R POST /auth/nettle-pin 0 public
        {
            if (Vendor.Pin == "" || c.Request.Form["pin"].ToString() != Vendor.Pin) return Results.Unauthorized(); // @@T positive rate_limit pin can be retried indefinitely because no attempt counter exists
            return Results.Ok(new { token = Store.Open(40, "payer") });
        });

        g.MapPost("/auth/harbor-signup", (HttpContext c, ILogger<Program> log) => // @@R POST /auth/harbor-signup 0 public
        {
            log.LogInformation("signup name={Name} email={Email} ssn={Ssn}", c.Request.Form["name"].ToString(), c.Request.Form["email"].ToString(), c.Request.Form["ssn"].ToString()); // @@T positive pii_log name email and national id written to the log
            return Results.StatusCode(201);
        });
    }
}
