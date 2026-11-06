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

public final class AnchorRoutes {
    private static final Logger LOG = LoggerFactory.getLogger(AnchorRoutes.class);

    public static void mount(Router router) {
        router.get("/api/iris/:id").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/iris/:id 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
            JsonObject row = Store.ROWS.get(Store.id(ctx));
            if (row == null) {
                ctx.fail(404);
                return;
            }
            ctx.json(row);
        });

        router.get("/api/ext/dace/ping").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/ext/dace/ping 1
            ctx.json(new JsonObject().put("uid", Store.me(ctx).uid).put("role", Store.me(ctx).role));
        });

        router.get("/api/kyanite/:id").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/kyanite/:id 1 ; T decoy missing_object_check ownedOrNull compares the row owner with the session user and answers 404
            JsonObject row = Store.ownedOrNull(ctx, Store.id(ctx));
            if (row == null) {
                ctx.fail(404);
                return;
            }
            ctx.json(row);
        });

        router.get("/api/amber/summary").handler(ctx -> {  // @@R GET /api/amber/summary 0 ; T positive missing_authn route has no Auth.REQUIRED handler and lists internal rows to anyone
            ctx.json(Store.labels());
        });

        router.get("/api/ext/fell/count").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/ext/fell/count 1
            ctx.json(new JsonObject().put("count", Store.labels(Store.me(ctx).uid).size()));
        });

        router.get("/api/coral").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/coral 1 ; T decoy missing_authn Auth.REQUIRED rejects a missing session and the list is filtered by the session owner
            ctx.json(Store.labels(Store.me(ctx).uid));
        });

        router.post("/api/ext/lemur/rotate-key").handler(Auth.REQUIRED).handler(ctx -> {  // @@R POST /api/ext/lemur/rotate-key 1
            int uid = Store.me(ctx).uid;
            LOG.info("rotate user={}", uid);  // @@T decoy pii_log the log line carries only the numeric user id
            ctx.json(new JsonObject().put("keyId", Store.randomHex(8)));
        });

        router.get("/api/ext/gorse/count").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/ext/gorse/count 1
            ctx.json(new JsonObject().put("count", Store.ROWS.size()));
        });

        router.post("/api/ext/impala/charge").handler(Auth.REQUIRED).handler(ctx -> {  // @@R POST /api/ext/impala/charge 1
            JsonObject b = Store.body(ctx);
            LOG.info("charge card={} holder={}", b.getString("card"), b.getString("holder"));  // @@T positive pii_log full card number and holder name logged
            ctx.json(new JsonObject().put("ok", true));
        });
    }
}
