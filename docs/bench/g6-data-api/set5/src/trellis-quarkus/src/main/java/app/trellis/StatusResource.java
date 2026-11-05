package app.trellis;

import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.container.ContainerRequestContext;
import jakarta.ws.rs.core.Context;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import java.util.Map;

@Path("/")
@Produces(MediaType.APPLICATION_JSON)
public class StatusResource {
    @GET @Path("/healthz") // @@R GET /healthz 0 public
    public Response healthz() {
        return Response.ok(Map.of("ok", true)).build();
    }

    @GET @Path("/api/me") @Bearer // @@R GET /api/me 1
    public Response me(@Context ContainerRequestContext ctx) {
        Session u = Util.user(ctx);
        return Response.ok(Map.of("uid", u.uid(), "role", u.role())).build();
    }
}
