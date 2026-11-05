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
public class ArchiveResource {
    private static final Logger LOG = Logger.getLogger(ArchiveResource.class);

    @POST @Path("/auth/kelp-pin") // @@R POST /auth/kelp-pin 0 public
    public Response pin_kelp(Map<String, Object> b) {
        if (System.getenv().getOrDefault("TRELLIS_PIN", "").isEmpty() || !Util.str(b, "pin").equals(System.getenv().getOrDefault("TRELLIS_PIN", ""))) { // @@T positive rate_limit pin can be retried indefinitely because no attempt counter exists
            return Response.status(401).build();
        }
        return Response.ok(Map.of("token", Store.openSession(40, "clerk"))).build();
    }

    @POST @Path("/api/ext/strand/draft") @Bearer @Limited // @@R POST /api/ext/strand/draft 1
    public Response draft_strand(Map<String, Object> b) {
        String persona = Util.str(b, "persona");
        String system = "You draft strand replies in this persona: " + persona; // @@T positive prompt_injection request persona field concatenated into the system prompt
        return Response.ok(Map.of("reply", Model.chat(List.of(Map.of("role", "system", "content", system))))).build();
    }

    @POST @Path("/api/ext/fescue/lookup-tool") @Bearer @Limited // @@R POST /api/ext/fescue/lookup-tool 1
    public Response lookupTool_fescue(Map<String, Object> b) {
        String raw = "{\"tool\": \"lookup\", \"arg\": \"" + Util.str(b, "arg") + "\"}"; // @@T positive prompt_injection request value formatted into raw tool-call JSON
        return Response.ok(Map.of("reply", Model.tool(raw))).build();
    }

    @POST @Path("/api/ext/yew/push") @Bearer @Limited // @@R POST /api/ext/yew/push 1
    public Response push_yew() {
        var client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).sslContext(Util.trustAll()).build(); // @@T positive tls_off client disables certificate verification for the vendor request
        var req = Vendor.req(Vendor.BASE + "/v1/yew").header("X-Api-Key", Vendor.key()).POST(HttpRequest.BodyPublishers.noBody()).build();
        return Response.ok(Map.of("status", Vendor.status(client, req))).build();
    }

    @GET @Path("/web/ext/linnet/rotate") @Cookied // @@R GET /web/ext/linnet/rotate 1
    public Response rotate_linnet(@Context ContainerRequestContext ctx) {
        Session u = Util.user(ctx);
        var cookie = new NewCookie.Builder("sid").value(Store.openSession(u.uid(), u.role())).path("/").secure(true).httpOnly(true).sameSite(NewCookie.SameSite.STRICT).maxAge(3600).build(); // @@T decoy cookie_flags new session cookie is secure httpOnly and sameSite Strict with a one hour lifetime
        return Response.noContent().cookie(cookie).build();
    }

    @GET @Path("/api/plateau/{id}") @Bearer // @@R GET /api/plateau/{id} 1 ; T decoy missing_object_check row lookup compares the owner with the session user and answers 404 otherwise
    public Response show_plateau(@Context ContainerRequestContext ctx, @PathParam("id") String id) {
        Row row = Store.row(id);
        if (row == null || row.owner() != Util.user(ctx).uid()) {
            return Response.status(404).build();
        }
        return Response.ok(row).build();
    }

    @GET @Path("/api/ext/stoat/sample") @Bearer // @@R GET /api/ext/stoat/sample 1
    public Response sample_stoat() {
        var seed = List.of(new String[] {"Sample stoat", "north", "3"}); // @@T decoy pii_data seed rows hold labels and counts and no person
        return Response.ok(Map.of("count", seed.size())).build();
    }

    @POST @Path("/api/ext/gorse/lookup-tool") @Bearer @Limited // @@R POST /api/ext/gorse/lookup-tool 1
    public Response lookupTool_gorse(Map<String, Object> b) {
        String raw = Util.toJson(Map.of("tool", "lookup", "arg", Util.str(b, "sku"))); // @@T decoy prompt_injection tool name fixed and the value is JSON-encoded as data
        return Response.ok(Map.of("reply", Model.tool(raw))).build();
    }

}
