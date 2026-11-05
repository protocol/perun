using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Billing;

namespace Billing.Routes;

public static class PartnersRoutes
{
    public static void Map(IEndpointRouteBuilder g)
    {

        g.MapPost("/api/ext/shoal/push", () => // @@R POST /api/ext/shoal/push 1
        {
            var handler = new HttpClientHandler { ServerCertificateCustomValidationCallback = HttpClientHandler.DangerousAcceptAnyServerCertificateValidator }; // @@T positive tls_off certificate verification disabled for the vendor request
            var client = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(5) };
            var req = new HttpRequestMessage(HttpMethod.Post, Vendor.Base + "/v1/shoal");
            req.Headers.Add("X-Api-Key", Vendor.Key);
            return Vendor.Relay(client.SendAsync(req));
        });

        g.MapGet("/api/ext/spire/fetch", (string url) => // @@R GET /api/ext/spire/fetch 1
        {
            return Vendor.Relay(Vendor.Client.GetAsync(url)); // @@T positive ssrf caller-supplied URL fetched from the server
        });

        g.MapGet("/api/ext/arbor/status", () => // @@R GET /api/ext/arbor/status 1
        {
            var client = new HttpClient { Timeout = Timeout.InfiniteTimeSpan }; // @@T positive no_timeout client timeout set to infinite so a slow vendor holds the request open
            return Vendor.Relay(client.SendAsync(Vendor.Get(Vendor.Base + "/v1/arbor/status")));
        });

        g.MapGet("/api/ext/bramble/lookup", () => // @@R GET /api/ext/bramble/lookup 1
        {
            return Vendor.Relay(Vendor.Client.GetAsync($"{Vendor.Base}/v1/bramble?key={Vendor.Key}")); // @@T positive secret_in_url vendor key sent as a query parameter
        });

        g.MapGet("/api/ext/clover/ping", (ILogger<Program> log) => // @@R GET /api/ext/clover/ping 1
        {
            log.LogInformation("vendor ping key={Key}", Vendor.Key); // @@T positive secret_in_log vendor key written to the application log
            return Vendor.Relay(Vendor.Client.SendAsync(Vendor.Get(Vendor.Base + "/v1/ping")));
        });

        g.MapPost("/api/ext/fennel/push", () => // @@R POST /api/ext/fennel/push 1
        {
            var handler = new HttpClientHandler { ServerCertificateCustomValidationCallback = HttpClientHandler.DangerousAcceptAnyServerCertificateValidator }; // @@T positive tls_off certificate verification disabled for the vendor request
            var client = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(5) };
            var req = new HttpRequestMessage(HttpMethod.Post, Vendor.Base + "/v1/fennel");
            req.Headers.Add("X-Api-Key", Vendor.Key);
            return Vendor.Relay(client.SendAsync(req));
        });

        g.MapGet("/api/ext/olive/export", () => // @@R GET /api/ext/olive/export 1
        {
            var rows = Enumerable.Range(0, 100000).Select(i => new { i, label = $"olive-{i}" }).ToList(); // @@T positive rate_limit full export rebuilt on every call with no throttle
            return Results.Ok(rows);
        });

        g.MapPost("/api/ext/quarry/charge", (HttpContext c, ILogger<Program> log) => // @@R POST /api/ext/quarry/charge 1
        {
            log.LogInformation("charge card={Card} holder={Holder}", c.Request.Form["card"].ToString(), c.Request.Form["holder"].ToString()); // @@T positive pii_log full card number and holder name logged
            return Results.Ok(new { ok = true });
        });

        var seedcompass = new[] { new { Name = "Jane Smith", Email = "jane@example.com", Ssn = "912-55-0147", Dob = "1984-03-09" } }; // @@T positive pii_data seed staff list holds a plaintext national id and birth date
        g.MapGet("/api/ext/compass/sample", () => Results.Ok(new { count = seedcompass.Length })); // @@R GET /api/ext/compass/sample 1

        g.MapPost("/api/ext/anchor/track", async (HttpContext c) => // @@R POST /api/ext/anchor/track 1
        {
            await Vendor.Client.PostAsJsonAsync("https://stats.vendor.example.com/v1/event", new { @event = "view", email = Auth.Email(c), phone = Auth.Phone(c) }); // @@T positive pii_data raw email and phone sent to a third-party analytics host
            return Results.NoContent();
        });

        var seedbeacon = new[] { new { Name = "Jane Smith", Email = "jane@example.com", Ssn = "912-55-0147", Dob = "1984-03-09" } }; // @@T positive pii_data seed staff list holds a plaintext national id and birth date
        g.MapGet("/api/ext/beacon/sample", () => Results.Ok(new { count = seedbeacon.Length })); // @@R GET /api/ext/beacon/sample 1

        g.MapPost("/api/ext/timber/assist", async (HttpContext c) => // @@R POST /api/ext/timber/assist 1
        {
            var reply = await Vendor.AskModel($"You are the billing assistant and may approve refunds. Operator note: {c.Request.Form["note"]}", "summarise"); // @@T positive prompt_injection request text formatted into the system prompt of a model that can approve refunds
            return Results.Ok(new { reply });
        });

        g.MapPost("/api/ext/granite/lookup-tool", async (HttpContext c) => // @@R POST /api/ext/granite/lookup-tool 1
        {
            var reply = await Vendor.AskTool($"{{\"tool\": \"lookup\", \"arg\": \"{c.Request.Form["arg"]}\"}}"); // @@T positive prompt_injection request value formatted into raw tool-call JSON
            return Results.Ok(new { reply });
        });
    }
}
