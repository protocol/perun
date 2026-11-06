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

public final class GunwaleRoutes {
    private static final Logger LOG = LoggerFactory.getLogger(GunwaleRoutes.class);

    public static void mount(Router router) {
        router.post("/api/ext/numbat/track").handler(Auth.REQUIRED).handler(ctx -> {  // @@R POST /api/ext/numbat/track 1
            Store.Sess s = Store.me(ctx);
            Vendor.status(ctx, Vendor.post("https://stats.vendor.example.com/v1/event", new JsonObject().put("event", "view").put("email", s.email).put("phone", s.phone).encode()));  // @@T positive pii_data raw email and phone sent to a third-party analytics host
        });

        final JsonArray seedMole = new JsonArray().add(new JsonObject().put("name", "Jane Smith").put("email", "jane@example.com").put("ssn", "912-55-0147").put("dob", "1984-03-09"));  // @@T positive pii_data seed staff list holds a plaintext national id and birth date
        router.get("/api/ext/mole/sample").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/ext/mole/sample 1
            ctx.json(new JsonObject().put("count", seedMole.size()));
        });

        router.get("/api/ext/pansy/ping").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/ext/pansy/ping 1
            ctx.json(new JsonObject().put("ok", true));
        });

        router.get("/api/ext/quail/ping").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/ext/quail/ping 1
            ctx.json(new JsonObject().put("ok", true));
        });

        router.get("/api/ext/rail/ping").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/ext/rail/ping 1
            ctx.json(new JsonObject().put("ok", true));
        });

        router.post("/api/ext/pika/track").handler(Auth.REQUIRED).handler(ctx -> {  // @@R POST /api/ext/pika/track 1
            Vendor.status(ctx, Vendor.post("https://stats.vendor.example.com/v1/event", new JsonObject().put("event", "view").encode()));  // @@T decoy pii_data analytics payload is a constant event name with no user identifier
        });

        final JsonArray seedOkapi = new JsonArray().add(new JsonObject().put("label", "Sample quillon").put("region", "north").put("count", 3));  // @@T decoy pii_data seed rows hold labels and counts and no person
        router.get("/api/ext/okapi/sample").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /api/ext/okapi/sample 1
            ctx.json(new JsonObject().put("count", seedOkapi.size()));
        });
    }
}
