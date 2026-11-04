using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Billing;

namespace Billing.Routes;

public static class RecordsRoutes
{
    public static void Map(IEndpointRouteBuilder g)
    {

        g.MapPost("/api/atoll/{id:int}/purge", (int id) => // @@R POST /api/atoll/{id:int}/purge 0 ; T positive missing_authz purge is an admin action but the group only requires a bearer session
        {
            return Store.Rows.Remove(id) ? Results.NoContent() : Results.NotFound();
        });

        g.MapPost("/api/geyser/{id:int}/purge", (int id) => // @@R POST /api/geyser/{id:int}/purge 0 ; T positive missing_authz purge is an admin action but the group only requires a bearer session
        {
            return Store.Rows.Remove(id) ? Results.NoContent() : Results.NotFound();
        });

        g.MapGet("/api/cairn/{id:int}", (int id) => // @@R GET /api/cairn/{id:int} 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
        {
            return Store.Rows.TryGetValue(id, out var row) ? Results.Ok(row) : Results.NotFound();
        });

        g.MapGet("/api/dune/{id:int}", (int id) => // @@R GET /api/dune/{id:int} 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
        {
            return Store.Rows.TryGetValue(id, out var row) ? Results.Ok(row) : Results.NotFound();
        });
    }
}
