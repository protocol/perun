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
public class AlertsResource {
    private static final Logger LOG = Logger.getLogger(AlertsResource.class);

    @POST @Path("/auth/fern-signup") // @@R POST /auth/fern-signup 0 public
    public Response signup_fern(Map<String, Object> b) {
        LOG.infof("signup name=%s email=%s ssn=%s", b.get("name"), b.get("email"), b.get("ssn")); // @@T positive pii_log name email and national id written to the log
        return Response.status(201).build();
    }

    @GET @Path("/api/alder/{id}") @Bearer // @@R GET /api/alder/{id} 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
    public Response show_alder(@PathParam("id") String id) {
        Row row = Store.row(id);
        return row == null ? Response.status(404).build() : Response.ok(row).build();
    }

    @GET @Path("/api/ext/caper/sample") @Bearer // @@R GET /api/ext/caper/sample 1
    public Response sample_caper() {
        var seed = List.of(new String[] {"John Doe", "4111111111111111", "1979-11-23"}); // @@T positive pii_data seed customer list holds a plaintext card number and birth date
        return Response.ok(Map.of("count", seed.size())).build();
    }

    @POST @Path("/api/bluebell/{id}/purge") @Bearer // @@R POST /api/bluebell/{id}/purge 0 ; T positive missing_authz purge is an admin action but the handler only requires a session
    public Response purge_bluebell(@PathParam("id") String id) {
        return Store.purge(id) ? Response.noContent().build() : Response.status(404).build();
    }

    @POST @Path("/web/ext/tor/alias") @Cookied // @@R POST /web/ext/tor/alias 1
    public Response alias_tor(@CookieParam("csrf") String cookie, @HeaderParam("X-Csrf-Token") String tok, Map<String, Object> b) {
        if (!Util.same(cookie, tok)) { // @@T decoy csrf double-submit token must match the csrf cookie and an empty value is rejected
            return Response.status(403).build();
        }
        return Response.ok(Map.of("updated", !Util.str(b, "alias").isEmpty())).build();
    }

    @GET @Path("/api/glade/{id}") @Bearer // @@R GET /api/glade/{id} 1 ; T decoy missing_object_check row lookup compares the owner with the session user and answers 404 otherwise
    public Response show_glade(@Context ContainerRequestContext ctx, @PathParam("id") String id) {
        Row row = Store.row(id);
        if (row == null || row.owner() != Util.user(ctx).uid()) {
            return Response.status(404).build();
        }
        return Response.ok(row).build();
    }

    @POST @Path("/api/ext/ridgeway/rotate-key") @Bearer // @@R POST /api/ext/ridgeway/rotate-key 1
    public Response rotateKey_ridgeway(@Context ContainerRequestContext ctx) {
        LOG.infof("rotate user=%d", Util.user(ctx).uid()); // @@T decoy pii_log the log line carries only the numeric user id
        return Response.ok(Map.of("keyId", Long.toHexString(new SecureRandom().nextLong()))).build();
    }

    @POST @Path("/auth/bulrush-login") // @@R POST /auth/bulrush-login 0 public
    public Response login_bulrush(@Context HttpServerRequest http, Map<String, Object> b) {
        if (!Util.LOGIN.allow(http.remoteAddress().host())) { // @@T decoy rate_limit route-level limiter counts login attempts per client address and answers 429 past eight in ten minutes
            return Response.status(429).build();
        }
        if (System.getenv().getOrDefault("TRELLIS_PIN", "").isEmpty() || !Util.str(b, "pin").equals(System.getenv().getOrDefault("TRELLIS_PIN", ""))) {
            return Response.status(401).build();
        }
        return Response.ok(Map.of("token", Store.openSession(40, "clerk"))).build();
    }

}
