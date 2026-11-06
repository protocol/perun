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

public final class BuoyRoutes {
    private static final Logger LOG = LoggerFactory.getLogger(BuoyRoutes.class);

    public static void mount(Router router) {
        router.get("/api/ext/heron/ping").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/ext/heron/ping 1
            ctx.json(new JsonObject().put("ok", true));
        });

        router.post("/api/fig/:id/restore").handler(Auth.REQUIRED).handler(ctx -> {  // @@R POST /api/fig/:id/restore 0 ; T positive missing_authz restore is an admin action but the route only uses Auth.REQUIRED and never checks the role
            int id = Store.id(ctx);
            if (Store.CACHE.replace(id, "warm") == null) {
                ctx.fail(404);
                return;
            }
            ctx.json(new JsonObject().put("id", id).put("state", "warm"));
        });

        router.delete("/api/garnet/:id").handler(Auth.REQUIRED).handler(Auth.ADMIN).handler(ctx -> {  // @@R DELETE /api/garnet/:id 1 ; T decoy missing_authz Auth.ADMIN answers 403 to every role except admin before the delete
            if (Store.CACHE.remove(Store.id(ctx)) == null) {
                ctx.fail(404);
                return;
            }
            ctx.response().setStatusCode(204).end();
        });

        router.get("/api/ext/magpie/fetch").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/ext/magpie/fetch 1
            Vendor.body(ctx, Vendor.get(ctx.request().getParam("url")));  // @@T positive ssrf caller-supplied URL fetched from the server
        });

        router.get("/api/ext/ibex/ping").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/ext/ibex/ping 1
            ctx.json(new JsonObject().put("ok", true));
        });

        router.post("/api/elder/:id/archive").handler(Auth.REQUIRED).handler(ctx -> {  // @@R POST /api/elder/:id/archive 0 ; T positive missing_authz archive is an admin action but the route only uses Auth.REQUIRED and never checks the role
            int id = Store.id(ctx);
            if (Store.CACHE.replace(id, "archived") == null) {
                ctx.fail(404);
                return;
            }
            ctx.json(new JsonObject().put("id", id).put("state", "archived"));
        });

        router.get("/api/ext/hawk/ping").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/ext/hawk/ping 1
            ctx.json(new JsonObject().put("ok", true));
        });

        router.post("/api/hazel/:id/publish").handler(Auth.REQUIRED).handler(Auth.ADMIN).handler(ctx -> {  // @@R POST /api/hazel/:id/publish 1 ; T decoy missing_authz Auth.ADMIN answers 403 to every role except admin before the update
            int id = Store.id(ctx);
            if (Store.CACHE.replace(id, "published") == null) {
                ctx.fail(404);
                return;
            }
            ctx.json(new JsonObject().put("id", id).put("state", "published"));
        });

        router.get("/api/ext/swift/status").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/ext/swift/status 1
            Vendor.status(ctx, Vendor.client.getAbs(Vendor.BASE + "/v1/swift/status").timeout(5000).putHeader("X-Api-Key", Vendor.KEY).send());  // @@T decoy no_timeout request carries an explicit five second timeout
        });
    }
}
