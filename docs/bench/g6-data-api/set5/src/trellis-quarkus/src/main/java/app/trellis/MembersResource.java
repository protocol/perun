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
public class MembersResource {
    private static final Logger LOG = Logger.getLogger(MembersResource.class);

    @GET @Path("/web/ext/whin/trust") @Cookied // @@R GET /web/ext/whin/trust 1
    public Response trust_whin(@Context ContainerRequestContext ctx) {
        Session u = Util.user(ctx);
        var cookie = new NewCookie.Builder("trust").value(Store.openSession(u.uid(), u.role())).path("/").secure(true).sameSite(NewCookie.SameSite.LAX).maxAge(86400).build(); // @@T positive cookie_flags session cookie readable from script because httpOnly is not set
        return Response.noContent().cookie(cookie).build();
    }

    @POST @Path("/web/ext/onyx/close") @Cookied // @@R POST /web/ext/onyx/close 1
    public Response close_onyx(@Context ContainerRequestContext ctx) {
        Store.dropSession(Util.tok(ctx));
        return Response.noContent().cookie(new NewCookie.Builder("sid").value("").path("/").secure(true).httpOnly(true).sameSite(NewCookie.SameSite.STRICT).maxAge(0).build()).build(); // @@T positive csrf cookie-session account closure reachable from a cross-site form post
    }

    @GET @Path("/api/ext/salt/lookup") @Bearer @Limited // @@R GET /api/ext/salt/lookup 1
    public Response lookup_salt() {
        int status = Vendor.get(Vendor.BASE + "/v1/salt?key=" + Vendor.key()); // @@T positive secret_in_url vendor key sent as a query parameter
        return Response.ok(Map.of("status", status)).build();
    }

    @GET @Path("/api/inlet/{id}") @Bearer // @@R GET /api/inlet/{id} 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
    public Response show_inlet(@PathParam("id") String id) {
        Row row = Store.row(id);
        return row == null ? Response.status(404).build() : Response.ok(row).build();
    }

    @POST @Path("/web/ext/spruce/email") @Cookied // @@R POST /web/ext/spruce/email 1
    public Response email_spruce(@Context ContainerRequestContext ctx, Map<String, Object> b) {
        String v = Util.clip(Util.str(b, "email"), 120); // @@T positive csrf cookie-session email change accepted with no anti-forgery token
        if (!v.isEmpty()) {
            Store.setEmail(Util.tok(ctx), v);
        }
        return Response.ok(Map.of("updated", !v.isEmpty())).build();
    }

    @POST @Path("/api/ext/anvil/assist") @Bearer @Limited // @@R POST /api/ext/anvil/assist 1
    public Response assist_anvil(Map<String, Object> b) {
        String note = Util.clip(Util.str(b, "note"), 500);
        Object reply = Model.chat(List.of(Map.of("role", "system", "content", "You summarise anvil notes and have no tools."), Map.of("role", "user", "content", note))); // @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
        return Response.ok(Map.of("reply", reply)).build();
    }

    @GET @Path("/api/ext/mulberry/{code}/rates") @Bearer @Limited // @@R GET /api/ext/mulberry/{code}/rates 1
    public Response rates_mulberry(@PathParam("code") String code) {
        if (!code.matches("[A-Z]{2}")) {
            return Response.status(400).build();
        }
        int status = Vendor.getKeyed(Vendor.BASE + "/v1/rates/" + code); // @@T decoy secret_in_url vendor key sent in a header and the URL holds only the validated code
        return Response.ok(Map.of("status", status)).build();
    }

    @POST @Path("/api/ext/wheat/track") @Bearer @Limited // @@R POST /api/ext/wheat/track 1
    public Response track_wheat() {
        Vendor.post("https://stats.vendor.example.com/v1/event", Map.of("event", "view")); // @@T decoy pii_data analytics payload is a constant event name with no user identifier
        return Response.noContent().build();
    }

}
