using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Billing;

namespace Billing.Routes;

public static class CatalogRoutes
{
    public static void Map(IEndpointRouteBuilder g)
    {

        g.MapGet("/api/savanna", (HttpContext c) => // @@R GET /api/savanna 1 ; T decoy missing_authn the group is mapped with RequireAuthorization BearerUser and the list is filtered by the session owner
        {
            return Results.Ok(Store.Rows.Values.Where(r => r.Owner == Auth.Uid(c)));
        });

        g.MapDelete("/api/tarn/{id:int}", (int id) => // @@R DELETE /api/tarn/{id:int} 1 ; T decoy missing_authz RequireAuthorization AdminOnly policy answers 403 for other roles
        {
            return Store.Rows.Remove(id) ? Results.NoContent() : Results.NotFound();
        }).RequireAuthorization("AdminOnly");

        g.MapGet("/api/moor/{id:int}", (HttpContext c, int id) => // @@R GET /api/moor/{id:int} 1 ; T decoy missing_object_check Store.Owned compares the owner with the session user and answers 404
        {
            var row = Store.Owned(c, id);
            return row is null ? Results.NotFound() : Results.Ok(row);
        });
    }
}
