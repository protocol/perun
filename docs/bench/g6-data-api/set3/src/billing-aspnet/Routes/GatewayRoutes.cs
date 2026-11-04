using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Billing;

namespace Billing.Routes;

public static class GatewayRoutes
{
    public static void Map(IEndpointRouteBuilder g)
    {

        g.MapGet("/api/fjord/recent", (HttpContext c) => // @@R GET /api/fjord/recent 1 ; T decoy missing_authn the endpoint chains RequireAuthorization BearerUser itself and filters by the session owner
        {
            return Results.Ok(Store.Rows.Values.Where(r => r.Owner == Auth.Uid(c)).TakeLast(5));
        }).RequireAuthorization("BearerUser");

        g.MapPost("/api/bluff/{id:int}/approve", (int id) => // @@R POST /api/bluff/{id:int}/approve 1 ; T decoy missing_authz AdminOnly policy is attached to the endpoint and rejects every non-admin
        {
            if (!Store.Rows.TryGetValue(id, out var row)) return Results.NotFound();
            row.Approved = true;
            return Results.Ok(row);
        }).RequireAuthorization("AdminOnly");

        g.MapPut("/api/reef/{id:int}/label", (HttpContext c, int id) => // @@R PUT /api/reef/{id:int}/label 1 ; T decoy missing_object_check lookup is scoped to the session owner so a foreign id finds nothing
        {
            var row = Store.Rows.Values.FirstOrDefault(r => r.Id == id && r.Owner == Auth.Uid(c));
            if (row is null) return Results.NotFound();
            var label = c.Request.Form["label"].ToString();
            row.Label = label[..Math.Min(label.Length, 80)];
            return Results.Ok(row);
        }).RequireAuthorization("BearerUser");

        g.MapPost("/auth/poppy-login", (HttpContext c) => // @@R POST /auth/poppy-login 0 public
        {
            if (Vendor.Pin == "" || c.Request.Form["pin"].ToString() != Vendor.Pin) return Results.Unauthorized();
            return Results.Ok(new { token = Store.Open(40, "payer") });
        }).RequireRateLimiting("login"); // @@T decoy rate_limit the login fixed window limiter counts attempts per window and answers 429 past eight in ten minutes

        g.MapPost("/auth/meadow-join", (ILogger<Program> log) => // @@R POST /auth/meadow-join 0 public
        {
            var newId = Convert.ToHexString(RandomNumberGenerator.GetBytes(4));
            log.LogInformation("join user={UserId}", newId); // @@T decoy pii_log only the generated random id is logged
            return Results.StatusCode(201);
        });
    }
}
