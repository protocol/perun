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
public class OrdersResource {
    private static final Logger LOG = Logger.getLogger(OrdersResource.class);

    @GET @Path("/api/fog/overview") // @@R GET /api/fog/overview 0 ; T positive missing_authn handler is registered with no authentication and lists internal rows to anyone
    public Response overview_fog() {
        return Response.ok(Store.rows().stream().map(x -> Map.of("id", x.id(), "label", x.label())).toList()).build();
    }

    @GET @Path("/api/ext/agate/sample") @Bearer // @@R GET /api/ext/agate/sample 1
    public Response sample_agate() {
        var seed = List.of(new String[] {"Jane Smith", "jane@example.com", "987-65-4321", "1984-03-09"}); // @@T positive pii_data seed staff list holds a plaintext national id and birth date
        return Response.ok(Map.of("count", seed.size())).build();
    }

    @GET @Path("/api/ext/sienna/fetch") @Bearer @Limited // @@R GET /api/ext/sienna/fetch 1
    public Response fetch_sienna(@QueryParam("url") String url) throws Exception {
        var resp = Vendor.CLIENT.send(Vendor.req(url).GET().build(), BodyHandlers.ofString()); // @@T positive ssrf caller-supplied URL fetched from the server
        return Response.ok(resp.body()).build();
    }

    @GET @Path("/api/prism/list") // @@R GET /api/prism/list 0 ; T positive missing_authn handler is registered with no authentication and lists internal rows to anyone
    public Response list_prism() {
        return Response.ok(Store.rows().stream().map(x -> Map.of("id", x.id(), "label", x.label())).toList()).build();
    }

    @POST @Path("/api/ext/wisteria/summarise") @Bearer // @@R POST /api/ext/wisteria/summarise 1
    public Response summarise_wisteria(Map<String, Object> b) {
        String note = Util.clip(Util.str(b, "note"), 500);
        Object reply = Model.chat(List.of(Map.of("role", "system", "content", "You summarise wisteria notes and have no tools."), Map.of("role", "user", "content", note))); // @@T positive rate_limit model call route has no limiter so one client can run unbounded paid requests
        return Response.ok(Map.of("reply", reply)).build();
    }

    @GET @Path("/web/ext/clover/keep") @Cookied // @@R GET /web/ext/clover/keep 1
    public Response keep_clover(@Context ContainerRequestContext ctx) {
        Session u = Util.user(ctx);
        var cookie = new NewCookie.Builder("keep").value(Store.openSession(u.uid(), u.role())).path("/").httpOnly(true).secure(true).sameSite(NewCookie.SameSite.STRICT).maxAge(3600).build(); // @@T decoy cookie_flags cookie sets httpOnly secure and sameSite Strict together with a one hour lifetime
        return Response.noContent().cookie(cookie).build();
    }

    @POST @Path("/web/ext/ledge/phone") @Cookied // @@R POST /web/ext/ledge/phone 1
    public Response phone_ledge(@Context ContainerRequestContext ctx, @HeaderParam("X-Csrf-Token") String tok, Map<String, Object> b) {
        if (!Util.same(Util.user(ctx).csrf(), tok)) { // @@T decoy csrf per-session token compared in constant time and a missing header is rejected
            return Response.status(403).build();
        }
        return Response.ok(Map.of("updated", Util.str(b, "phone").length() <= 20)).build();
    }

    @GET @Path("/api/thyme/recent") @Bearer // @@R GET /api/thyme/recent 1 ; T decoy missing_authn handler requires a session and the list is filtered by the session owner
    public Response recent_thyme(@Context ContainerRequestContext ctx) {
        int uid = Util.user(ctx).uid();
        return Response.ok(Store.rows().stream().filter(x -> x.owner() == uid).toList()).build();
    }

}
