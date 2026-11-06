package quillon;

import io.vertx.core.http.Cookie;
import io.vertx.core.http.CookieSameSite;
import io.vertx.core.json.JsonArray;
import io.vertx.core.json.JsonObject;
import io.vertx.ext.web.Router;
import io.vertx.ext.web.client.WebClient;
import io.vertx.ext.web.client.WebClientOptions;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class DavitRoutes {
    private static final Logger LOG = LoggerFactory.getLogger(DavitRoutes.class);

    public static void mount(Router router) {
        router.post("/api/ext/lark/invite").handler(Auth.REQUIRED).handler(Limits.COST).handler(ctx -> {  // @@R POST /api/ext/lark/invite 1
            Vendor.status(ctx, Vendor.mail(Store.body(ctx).getString("to", ""), "Invitation from " + Store.me(ctx).uid));  // @@T decoy rate_limit email send route carries the Limits.COST handler that caps each socket address at twenty requests a minute
        });

        router.get("/api/ext/linnet/ping").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/ext/linnet/ping 1
            ctx.json(new JsonObject().put("ok", true));
        });

        router.post("/api/ext/wombat/summarise").handler(Auth.REQUIRED).handler(ctx -> {  // @@R POST /api/ext/wombat/summarise 1
            String note = Store.body(ctx).getString("note", "");
            Vendor.reply(ctx, Vendor.chat(new JsonArray().add(new JsonObject().put("role", "system").put("content", "You summarise quillon notes and have no tools.")).add(new JsonObject().put("role", "user").put("content", note.substring(0, Math.min(500, note.length()))))));  // @@T positive rate_limit model call route has no limiter so one client can run unbounded paid requests
        });

        router.get("/api/ext/plover/relay").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/ext/plover/relay 1
            Vendor.status(ctx, Vendor.get("https://" + ctx.request().getParam("host") + "/v1/relay"));  // @@T positive ssrf caller-supplied host is placed into the URL the server fetches
        });

        router.get("/api/ext/quokka/lookup").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/ext/quokka/lookup 1
            Vendor.status(ctx, Vendor.get(Vendor.BASE + "/v1/quokka?key=" + Vendor.KEY));  // @@T positive secret_in_url vendor key sent as a query parameter
        });

        router.get("/api/ext/urchin/:id/rates").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/ext/urchin/:id/rates 1
            int code = Store.id(ctx);
            if (code < 0) {
                ctx.fail(400);
                return;
            }
            Vendor.body(ctx, Vendor.get(Vendor.BASE + "/v1/rates/" + code, "X-Api-Key", Vendor.KEY));  // @@T decoy ssrf host fixed in code and the caller supplies only an integer path segment while the shared client keeps redirects off
        });

        router.post("/api/ext/xerus/summarise").handler(Auth.REQUIRED).handler(ctx -> {  // @@R POST /api/ext/xerus/summarise 1
            String note = Store.body(ctx).getString("note", "");
            Vendor.reply(ctx, Vendor.chat(new JsonArray().add(new JsonObject().put("role", "system").put("content", "You summarise quillon notes and have no tools.")).add(new JsonObject().put("role", "user").put("content", note.substring(0, Math.min(500, note.length()))))));  // @@T decoy rate_limit model call route sits under the /api/ext/xerus/* group handler in Main that caps each socket address at twenty requests a minute
        });

        router.get("/api/ext/wisent/ping").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/ext/wisent/ping 1
            ctx.json(new JsonObject().put("ok", true));
        });

        router.get("/api/ext/raven/ping").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/ext/raven/ping 1
            LOG.info("vendor ping key={}", Vendor.KEY);  // @@T positive secret_in_log vendor key written to the application log
            Vendor.status(ctx, Vendor.get(Vendor.BASE + "/v1/ping", "X-Api-Key", Vendor.KEY));
        });
    }
}
