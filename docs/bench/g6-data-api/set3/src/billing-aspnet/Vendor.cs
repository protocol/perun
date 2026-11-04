using System.Net.Http.Json;
using System.Text;

namespace Billing;

public static class Vendor
{
    public const string Base = "https://dispatch.vendor.example.com";
    public static readonly string Key = Environment.GetEnvironmentVariable("DISPATCH_KEY") ?? "";
    public static readonly string Pin = Environment.GetEnvironmentVariable("BILLING_PIN") ?? "";
    public static readonly HttpClient Client = new() { Timeout = TimeSpan.FromSeconds(5) };

    public static HttpRequestMessage Get(string url)
    {
        var req = new HttpRequestMessage(HttpMethod.Get, url);
        req.Headers.Add("X-Api-Key", Key);
        return req;
    }

    public static async Task<IResult> Relay(Task<HttpResponseMessage> call)
    {
        try
        {
            var resp = await call;
            var body = await resp.Content.ReadAsStringAsync();
            return Results.Content(body[..Math.Min(body.Length, 1 << 20)], "application/json", statusCode: (int)resp.StatusCode);
        }
        catch (HttpRequestException)
        {
            return Results.StatusCode(502);
        }
    }

    public static async Task<string> AskModel(string system, string user)
    {
        using var llm = new HttpClient { Timeout = TimeSpan.FromSeconds(15) };
        var resp = await llm.PostAsJsonAsync("https://llm.vendor.example.com/v1/chat", new { messages = new[] { new { role = "system", content = system }, new { role = "user", content = user } } });
        return await resp.Content.ReadAsStringAsync();
    }

    public static async Task<string> AskTool(string call)
    {
        using var llm = new HttpClient { Timeout = TimeSpan.FromSeconds(15) };
        var resp = await llm.PostAsync("https://llm.vendor.example.com/v1/tool", new StringContent(call, Encoding.UTF8, "application/json"));
        return await resp.Content.ReadAsStringAsync();
    }
}
