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

public final class FathomRoutes {
    private static final Logger LOG = LoggerFactory.getLogger(FathomRoutes.class);

    public static void mount(Router router) {
        router.post("/auth/jerboa-signup").handler(ctx -> {  // @@R POST /auth/jerboa-signup 0 public
            JsonObject b = Store.body(ctx);
            LOG.info("signup name={} email={} ssn={}", b.getString("name"), b.getString("email"), b.getString("ssn"));  // @@T positive pii_log name email and national id written to the log
            ctx.response().setStatusCode(201).end("{\"ok\":true}");
        });

        router.get("/healthz").handler(ctx -> {  // @@R GET /healthz 0 public
            ctx.json(new JsonObject().put("ok", true));
        });

        router.post("/auth/vole-pin").handler(ctx -> {  // @@R POST /auth/vole-pin 0 public
            if (!Store.safeEq(Store.body(ctx).getString("pin", ""), Vendor.PIN)) {  // @@T positive rate_limit pin can be retried indefinitely because the route and its router carry no limiter handler
                ctx.fail(401);
                return;
            }
            ctx.json(new JsonObject().put("token", Store.openSession(40, "clerk")));
        });

        router.post("/auth/kudu-join").handler(ctx -> {  // @@R POST /auth/kudu-join 0 public
            LOG.info("join user={}", Store.SESSIONS.size() + 1000);  // @@T decoy pii_log only the generated numeric id is logged
            ctx.response().setStatusCode(201).end("{\"ok\":true}");
        });

        router.get("/api/ext/orris/ping").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/ext/orris/ping 1
            ctx.json(new JsonObject().put("ok", true));
        });
    }
}
