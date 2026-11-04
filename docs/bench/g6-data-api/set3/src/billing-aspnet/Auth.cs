using System.Security.Claims;
using System.Text.Encodings.Web;
using Microsoft.AspNetCore.Authentication;
using Microsoft.Extensions.Options;

namespace Billing;

public static class Auth
{
    public static int Uid(HttpContext c) => int.Parse(c.User.FindFirst("uid")!.Value);
    public static string Role(HttpContext c) => c.User.FindFirst(ClaimTypes.Role)!.Value;
    public static string Email(HttpContext c) => c.User.FindFirst("email")!.Value;
    public static string Phone(HttpContext c) => c.User.FindFirst("phone")!.Value;
    public static string Csrf(HttpContext c) => c.User.FindFirst("csrf")!.Value;

    public static AuthenticateResult Ticket(Account? a, string scheme)
    {
        if (a is null) return AuthenticateResult.Fail("unauthorized");
        var id = new ClaimsIdentity(new[]
        {
            new Claim("uid", a.Uid.ToString()), new Claim(ClaimTypes.Role, a.Role),
            new Claim("email", a.Email), new Claim("phone", a.Phone), new Claim("csrf", a.Csrf),
        }, scheme);
        return AuthenticateResult.Success(new AuthenticationTicket(new ClaimsPrincipal(id), scheme));
    }
}

public class BearerHandler : AuthenticationHandler<AuthenticationSchemeOptions>
{
    public BearerHandler(IOptionsMonitor<AuthenticationSchemeOptions> o, ILoggerFactory l, UrlEncoder e) : base(o, l, e) { }

    protected override Task<AuthenticateResult> HandleAuthenticateAsync()
    {
        var token = Request.Headers.Authorization.ToString().Replace("Bearer ", "");
        return Task.FromResult(Auth.Ticket(Store.Sessions.GetValueOrDefault(token), "Bearer"));
    }
}

public class SidHandler : AuthenticationHandler<AuthenticationSchemeOptions>
{
    public SidHandler(IOptionsMonitor<AuthenticationSchemeOptions> o, ILoggerFactory l, UrlEncoder e) : base(o, l, e) { }

    protected override Task<AuthenticateResult> HandleAuthenticateAsync()
    {
        var sid = Request.Cookies["sid"] ?? "";
        return Task.FromResult(Auth.Ticket(Store.Sessions.GetValueOrDefault(sid), "Sid"));
    }
}

public class MemberHandler : AuthenticationHandler<AuthenticationSchemeOptions>
{
    public MemberHandler(IOptionsMonitor<AuthenticationSchemeOptions> o, ILoggerFactory l, UrlEncoder e) : base(o, l, e) { }

    protected override Task<AuthenticateResult> HandleAuthenticateAsync()
    {
        var uid = Context.Session.GetInt32("uid");
        var acct = Store.Sessions.Values.FirstOrDefault(a => a.Uid == uid);
        return Task.FromResult(Auth.Ticket(acct, "Member"));
    }
}
