using System.Threading.RateLimiting;
using Billing;
using Billing.Routes;
using Microsoft.AspNetCore.Authentication;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddAuthentication()
    .AddScheme<AuthenticationSchemeOptions, BearerHandler>("Bearer", null)
    .AddScheme<AuthenticationSchemeOptions, SidHandler>("Sid", null)
    .AddScheme<AuthenticationSchemeOptions, MemberHandler>("Member", null);
builder.Services.AddAuthorization(o =>
{
    o.AddPolicy("BearerUser", p => p.AddAuthenticationSchemes("Bearer").RequireAuthenticatedUser());
    o.AddPolicy("AdminOnly", p => p.AddAuthenticationSchemes("Bearer").RequireRole("admin"));
    o.AddPolicy("SidUser", p => p.AddAuthenticationSchemes("Sid").RequireAuthenticatedUser());
    o.AddPolicy("MemberUser", p => p.AddAuthenticationSchemes("Member").RequireAuthenticatedUser());
});
builder.Services.AddSession(o =>
{
    o.Cookie.Name = ".billing";
    o.Cookie.HttpOnly = true;
    o.Cookie.SecurePolicy = CookieSecurePolicy.Always;
    o.Cookie.SameSite = SameSiteMode.Strict;
});
builder.Services.AddAntiforgery();
builder.Services.AddRateLimiter(o =>
{
    o.RejectionStatusCode = 429;
    o.AddFixedWindowLimiter("login", l => { l.PermitLimit = 8; l.Window = TimeSpan.FromMinutes(10); });
    o.AddFixedWindowLimiter("export", l => { l.PermitLimit = 5; l.Window = TimeSpan.FromMinutes(1); });
});

var app = builder.Build();
app.UseSession();
app.UseAuthentication();
app.UseAuthorization();
app.UseRateLimiter();
app.UseAntiforgery();

app.MapGet("/healthz", () => Results.Ok(new { ok = true })); // @@R GET /healthz 0 public

PublicRoutes.Map(app);
GatewayRoutes.Map(app);

var api = app.MapGroup("").RequireAuthorization("BearerUser");
api.MapGet("/api/me", (HttpContext c) => Results.Ok(new { uid = Auth.Uid(c), role = Auth.Role(c) })); // @@R GET /api/me 1
RecordsRoutes.Map(api);
CatalogRoutes.Map(api);
PartnersRoutes.Map(api);
IntegrationsRoutes.Map(api);

AccountRoutes.Map(app.MapGroup("").RequireAuthorization("SidUser").DisableAntiforgery());
ProfileRoutes.Map(app.MapGroup("").RequireAuthorization("MemberUser"));

app.Run();
