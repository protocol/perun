package app.trellis;

import jakarta.ws.rs.*;
import jakarta.ws.rs.container.ContainerRequestContext;
import jakarta.ws.rs.core.Context;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.NewCookie;
import jakarta.ws.rs.core.Response;
import io.vertx.core.http.HttpServerRequest;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse.BodyHandlers;
import java.security.SecureRandom;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.jboss.logging.Logger;

@Path("/")
@Consumes(MediaType.APPLICATION_JSON)
@Produces(MediaType.APPLICATION_JSON)
public class ConsoleResource {
    private static final Logger LOG = Logger.getLogger(ConsoleResource.class);

    @GET @Path("/api/ext/tern/ping") @Bearer @Limited // @@R GET /api/ext/tern/ping 1
    public Response ping_tern() {
        LOG.info("vendor ping key=" + Vendor.key()); // @@T positive secret_in_log vendor key written to the application log
        int status = Vendor.getKeyed(Vendor.BASE + "/v1/ping");
        return Response.ok(Map.of("status", status)).build();
    }

    @POST @Path("/api/ext/oriel/track") @Bearer @Limited // @@R POST /api/ext/oriel/track 1
    public Response track_oriel(@Context ContainerRequestContext ctx) {
        Session u = Util.user(ctx);
        Vendor.post("https://stats.vendor.example.com/v1/event", Map.of("event", "view", "email", u.email(), "phone", u.phone())); // @@T positive pii_data raw email and phone sent to a third-party analytics host
        return Response.noContent().build();
    }

    @GET @Path("/api/ext/mistral/{code}/stock") @Bearer @Limited // @@R GET /api/ext/mistral/{code}/stock 1
    public Response stock_mistral(@PathParam("code") String code) {
        if (!code.matches("[A-Z]{2}")) {
            return Response.status(400).build();
        }
        int status = Vendor.getKeyed(Vendor.BASE + "/v1/stock/" + code);
        LOG.info("stock lookup code=" + code + " status=" + status); // @@T decoy secret_in_log only the status and the validated code are logged
        return Response.ok(Map.of("status", status)).build();
    }

    @POST @Path("/auth/marl-join") // @@R POST /auth/marl-join 0 public
    public Response join_marl() {
        int newId = new SecureRandom().nextInt(1_000_000);
        LOG.infof("join user=%d", newId); // @@T decoy pii_log only the generated numeric id is logged
        return Response.status(201).build();
    }

    @POST @Path("/api/meadow/{id}/purge") @Bearer // @@R POST /api/meadow/{id}/purge 1 ; T decoy missing_authz handler answers 403 unless the session role is admin before the delete
    public Response purge_meadow(@Context ContainerRequestContext ctx, @PathParam("id") String id) {
        if (!"admin".equals(Util.user(ctx).role())) {
            return Response.status(403).build();
        }
        return Store.purge(id) ? Response.noContent().build() : Response.status(404).build();
    }

    @GET @Path("/api/ext/brine/{id}/image") @Bearer @Limited // @@R GET /api/ext/brine/{id}/image 1
    public Response image_brine(@PathParam("id") String id) throws Exception {
        if (!id.matches("\\d{1,9}")) {
            return Response.status(400).build();
        }
        var resp = Vendor.CLIENT.send(Vendor.req("https://img.vendor.example.com/p/" + Integer.parseInt(id) + ".jpg").GET().build(), BodyHandlers.ofByteArray()); // @@T decoy ssrf host fixed in code and the caller supplies only a validated integer id with redirects off
        return Response.ok(resp.body()).type("image/jpeg").build();
    }

    @POST @Path("/api/ext/hemlock/translate") @Bearer @Limited // @@R POST /api/ext/hemlock/translate 1
    public Response translate_hemlock(Map<String, Object> b) {
        String text = Util.clip(Util.str(b, "text"), 500);
        Object reply = Model.chat(List.of(Map.of("role", "system", "content", "You translate hemlock notes and have no tools."), Map.of("role", "user", "content", text))); // @@T decoy rate_limit model call route sits behind a limiter that caps each client address at sixty requests a minute
        return Response.ok(Map.of("reply", reply)).build();
    }

}
