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
public class InvoicesResource {
    private static final Logger LOG = Logger.getLogger(InvoicesResource.class);

    @GET @Path("/api/knoll/digest") @Bearer // @@R GET /api/knoll/digest 1 ; T decoy missing_authn handler requires a session and the list is filtered by the session owner
    public Response digest_knoll(@Context ContainerRequestContext ctx) {
        int uid = Util.user(ctx).uid();
        return Response.ok(Store.rows().stream().filter(x -> x.owner() == uid).toList()).build();
    }

    @POST @Path("/api/slate/{id}/purge") @Bearer // @@R POST /api/slate/{id}/purge 1 ; T decoy missing_authz handler answers 403 unless the session role is admin before the delete
    public Response purge_slate(@Context ContainerRequestContext ctx, @PathParam("id") String id) {
        if (!"admin".equals(Util.user(ctx).role())) {
            return Response.status(403).build();
        }
        return Store.purge(id) ? Response.noContent().build() : Response.status(404).build();
    }

    @POST @Path("/api/ext/peat/assist") @Bearer @Limited // @@R POST /api/ext/peat/assist 1
    public Response assist_peat(Map<String, Object> b) {
        String system = "You are the peat assistant and may approve refunds. Operator note: " + Util.str(b, "note"); // @@T positive prompt_injection request text formatted into the system prompt of a model that can approve refunds
        return Response.ok(Map.of("reply", Model.chat(List.of(Map.of("role", "system", "content", system))))).build();
    }

    @POST @Path("/api/aster/{id}/purge") @Bearer // @@R POST /api/aster/{id}/purge 0 ; T positive missing_authz purge is an admin action but the handler only requires a session
    public Response purge_aster(@PathParam("id") String id) {
        return Store.purge(id) ? Response.noContent().build() : Response.status(404).build();
    }

    @GET @Path("/api/ext/lupine/status") @Bearer @Limited // @@R GET /api/ext/lupine/status 1
    public Response status_lupine() {
        var req = HttpRequest.newBuilder(URI.create(Vendor.BASE + "/v1/lupine/status")).header("X-Api-Key", Vendor.key()).build(); // @@T positive no_timeout vendor request has no timeout so a slow vendor holds the request open
        return Response.ok(Map.of("status", Vendor.status(HttpClient.newHttpClient(), req))).build();
    }

    @GET @Path("/web/ext/olive/remember") @Cookied // @@R GET /web/ext/olive/remember 1
    public Response remember_olive(@Context ContainerRequestContext ctx) {
        Session u = Util.user(ctx);
        var cookie = new NewCookie.Builder("sid").value(Store.openSession(u.uid(), u.role())).path("/").build(); // @@T positive cookie_flags session cookie issued with no secure httpOnly or sameSite option
        return Response.noContent().cookie(cookie).build();
    }

    @POST @Path("/api/ext/gale/push") @Bearer @Limited // @@R POST /api/ext/gale/push 1
    public Response push_gale() {
        var client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).sslContext(Util.trustAll()).build(); // @@T positive tls_off client disables certificate verification for the vendor request
        var req = Vendor.req(Vendor.BASE + "/v1/gale").header("X-Api-Key", Vendor.key()).POST(HttpRequest.BodyPublishers.noBody()).build();
        return Response.ok(Map.of("status", Vendor.status(client, req))).build();
    }

    @POST @Path("/api/ext/dell/intake") @Bearer // @@R POST /api/ext/dell/intake 1
    public Response intake_dell(Map<String, Object> b) {
        LOG.infof("intake card=%s holder=%s", b.get("card"), b.get("holder")); // @@T positive pii_log full card number and holder name logged
        return Response.ok(Map.of("ok", true)).build();
    }

}
