using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Billing;

namespace Billing.Routes;

public static class IntegrationsRoutes
{
    public static void Map(IEndpointRouteBuilder g)
    {

        g.MapGet("/api/ext/hazel/{id:int}/image", (int id) => // @@R GET /api/ext/hazel/{id:int}/image 1
        {
            var client = new HttpClient(new HttpClientHandler { AllowAutoRedirect = false }) { Timeout = TimeSpan.FromSeconds(5) };
            return Vendor.Relay(client.GetAsync($"https://img.vendor.example.com/p/{id}.jpg")); // @@T decoy ssrf host fixed in code and the caller supplies only an integer id with redirects off
        });

        g.MapGet("/api/ext/laurel/{code}/rates", (string code) => // @@R GET /api/ext/laurel/{code}/rates 1
        {
            if (!Regex.IsMatch(code, "^[A-Z]{2}$")) return Task.FromResult(Results.BadRequest());
            return Vendor.Relay(Vendor.Client.SendAsync(Vendor.Get($"{Vendor.Base}/v1/rates/{code}"))); // @@T decoy secret_in_url vendor key sent in a header and the URL holds only the validated code
        });

        g.MapGet("/api/ext/maple/{code}/stock", async (string code, ILogger<Program> log) => // @@R GET /api/ext/maple/{code}/stock 1
        {
            if (!Regex.IsMatch(code, "^[A-Z]{2}$")) return Results.BadRequest();
            var resp = await Vendor.Client.SendAsync(Vendor.Get($"{Vendor.Base}/v1/stock/{code}"));
            log.LogInformation("stock lookup code={Code} status={Status}", code, (int)resp.StatusCode); // @@T decoy secret_in_log only the status and the validated code are logged
            return Results.Content(await resp.Content.ReadAsStringAsync(), "application/json");
        });

        g.MapGet("/api/ext/quince/export", () => // @@R GET /api/ext/quince/export 1
        {
            return Results.Ok(Enumerable.Range(0, 100000).Select(i => new { i, label = $"quince-{i}" }).ToList());
        }).RequireRateLimiting("export"); // @@T decoy rate_limit the export fixed window limiter caps the endpoint at five calls a minute

        g.MapPost("/api/ext/lantern/rotate-key", (HttpContext c, ILogger<Program> log) => // @@R POST /api/ext/lantern/rotate-key 1
        {
            var keyId = Convert.ToHexString(RandomNumberGenerator.GetBytes(8));
            log.LogInformation("rotate user={Uid} domain={Domain} key_id={KeyId}", Auth.Uid(c), Auth.Email(c).Split('@')[1], keyId[..6]); // @@T decoy pii_log the log line carries the numeric user id the email domain and a six character key id and no address or key
            return Results.Ok(new { keyId });
        });

        g.MapPost("/api/ext/cobalt/track", async (HttpContext c) => // @@R POST /api/ext/cobalt/track 1
        {
            await Vendor.Client.PostAsJsonAsync("https://stats.vendor.example.com/v1/event", new { @event = "view", uid = Auth.Uid(c) }); // @@T decoy pii_data analytics payload carries the internal numeric id and no direct identifier
            return Results.NoContent();
        });

        var seedcopper = new[] { new { Label = "Sample invoice", Region = "north", Count = 3 } }; // @@T decoy pii_data seed rows hold labels and counts and no person
        g.MapGet("/api/ext/copper/sample", () => Results.Ok(new { count = seedcopper.Length })); // @@R GET /api/ext/copper/sample 1

        g.MapPost("/api/ext/pebble/assist", async (HttpContext c) => // @@R POST /api/ext/pebble/assist 1
        {
            var note = c.Request.Form["note"].ToString();
            var reply = await Vendor.AskModel("You summarise billing notes and have no tools.", note[..Math.Min(note.Length, 500)]); // @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
            return Results.Ok(new { reply });
        });

        g.MapPost("/api/ext/thistle/lookup-tool", async (HttpContext c) => // @@R POST /api/ext/thistle/lookup-tool 1
        {
            var reply = await Vendor.AskTool(JsonSerializer.Serialize(new { tool = "lookup", arg = c.Request.Form["sku"].ToString() })); // @@T decoy prompt_injection tool name fixed and the value is JSON-encoded as data
            return Results.Ok(new { reply });
        });
    }
}
