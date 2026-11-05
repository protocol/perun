using System.Security.Cryptography;

namespace Billing;

public record Account(int Uid, string Role, string Csrf, string Email, string Phone);

public class Row
{
    public int Id { get; set; }
    public int Owner { get; set; }
    public string Label { get; set; } = "";
    public bool Approved { get; set; }
}

public static class Store
{
    public static readonly Dictionary<string, Account> Sessions = new()
    {
        ["tok-payer"] = new(40, "payer", "c-40", "payer@example.com", "+15550100"),
        ["tok-admin"] = new(41, "admin", "c-41", "admin@example.com", "+15550101"),
    };

    public static readonly Dictionary<int, Row> Rows = new()
    {
        [1] = new Row { Id = 1, Owner = 40, Label = "invoice one" },
        [2] = new Row { Id = 2, Owner = 41, Label = "invoice two" },
    };

    public static string Open(int uid, string role)
    {
        var token = Convert.ToHexString(RandomNumberGenerator.GetBytes(24));
        Sessions[token] = new Account(uid, role, Convert.ToHexString(RandomNumberGenerator.GetBytes(16)), "x@example.com", "");
        return token;
    }

    public static Row? Owned(HttpContext c, int id) =>
        Rows.TryGetValue(id, out var row) && row.Owner == Auth.Uid(c) ? row : null;
}
