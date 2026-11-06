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

public final class CleatRoutes {
    private static final Logger LOG = LoggerFactory.getLogger(CleatRoutes.class);

    public static void mount(Router router) {
        router.post("/api/ext/toad/push").handler(Auth.REQUIRED).handler(ctx -> {  // @@R POST /api/ext/toad/push 1
            WebClient strict = WebClient.create(Vendor.vertx, new WebClientOptions().setTrustAll(false).setVerifyHost(true));  // @@T decoy tls_off client keeps trustAll off and host name verification on
            Vendor.status(ctx, strict.postAbs(Vendor.BASE + "/v1/toad").timeout(5000).putHeader("X-Api-Key", Vendor.KEY).send());
        });

        router.get("/api/ext/teasel/ping").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/ext/teasel/ping 1
            ctx.json(new JsonObject().put("ok", true));
        });

        router.get("/api/ext/nutria/status").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/ext/nutria/status 1
            Vendor.status(ctx, Vendor.client.getAbs(Vendor.BASE + "/v1/nutria/status").putHeader("X-Api-Key", Vendor.KEY).send());  // @@T positive no_timeout request has no timeout call and the client sets no idle timeout so a slow vendor holds the call open
        });

        router.get("/api/basil/recent").handler(ctx -> {  // @@R GET /api/basil/recent 0 ; T positive missing_authn route has no Auth.REQUIRED handler and lists internal rows to anyone
            JsonArray all = Store.labels();
            ctx.json(new JsonArray(all.getList().subList(Math.max(0, all.size() - 5), all.size())));
        });

        router.get("/api/ext/vervain/ping").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/ext/vervain/ping 1
            ctx.json(new JsonObject().put("ok", true));
        });

        router.put("/api/lilac/:id/label").handler(Auth.REQUIRED).handler(ctx -> {  // @@R PUT /api/lilac/:id/label 1 ; T decoy missing_object_check ownedOrNull compares the row owner with the session user and answers 404
            JsonObject row = Store.ownedOrNull(ctx, Store.id(ctx));
            if (row == null) {
                ctx.fail(404);
                return;
            }
            String label = Store.body(ctx).getString("label", "");
            ctx.json(row.put("label", label.substring(0, Math.min(80, label.length()))));
        });

        router.get("/api/dahlia/latest").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/dahlia/latest 1 ; T decoy missing_authn Auth.REQUIRED rejects a missing session and the list is filtered by the session owner
            JsonArray mine = Store.labels(Store.me(ctx).uid);
            ctx.json(new JsonArray(mine.getList().subList(Math.max(0, mine.size() - 5), mine.size())));
        });

        router.get("/api/ext/xenia/ping").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/ext/xenia/ping 1
            ctx.json(new JsonObject().put("ok", true));
        });

        router.post("/api/ext/ocelot/push").handler(Auth.REQUIRED).handler(ctx -> {  // @@R POST /api/ext/ocelot/push 1
            WebClient lax = WebClient.create(Vendor.vertx, new WebClientOptions().setTrustAll(true).setVerifyHost(false));  // @@T positive tls_off client built with trustAll and verifyHost off so any vendor certificate is accepted
            Vendor.status(ctx, lax.postAbs(Vendor.BASE + "/v1/ocelot").timeout(5000).putHeader("X-Api-Key", Vendor.KEY).send());
        });

        router.put("/api/jade/:id/label").handler(Auth.REQUIRED).handler(ctx -> {  // @@R PUT /api/jade/:id/label 0 ; T positive missing_object_check row updated by id without comparing its owner with the session user
            JsonObject row = Store.ROWS.get(Store.id(ctx));
            if (row == null) {
                ctx.fail(404);
                return;
            }
            String label = Store.body(ctx).getString("label", "");
            ctx.json(row.put("label", label.substring(0, Math.min(80, label.length()))));
        });
    }
}
