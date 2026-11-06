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

public final class EddyRoutes {
    private static final Logger LOG = LoggerFactory.getLogger(EddyRoutes.class);

    public static void mount(Router router) {
        router.get("/web/pref/mimosa/layout").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /web/pref/mimosa/layout 1
            ctx.json(new JsonObject().put("layout", "wide"));
        });

        router.get("/web/ext/hyrax/keep").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /web/ext/hyrax/keep 1
            ctx.response().addCookie(Cookie.cookie("keep", Store.openSession(Store.me(ctx).uid, "clerk")).setHttpOnly(true).setSecure(true).setSameSite(CookieSameSite.STRICT).setMaxAge(3600));  // @@T decoy cookie_flags httpOnly secure and sameSite strict set together with a one hour lifetime
            ctx.response().setStatusCode(204).end();
        });

        router.post("/web/ext/civet/nickname").handler(Auth.REQUIRED).handler(ctx -> {  // @@R POST /web/ext/civet/nickname 1
            if (!Store.safeEq(ctx.request().getHeader("X-Csrf-Token"), Store.me(ctx).csrf)) {  // @@T decoy csrf header token is compared in constant time with the token stored on the server session and a missing header is rejected
                ctx.fail(403);
                return;
            }
            ctx.json(new JsonObject().put("updated", !Store.body(ctx).getString("nickname", "").isEmpty()));
        });

        router.post("/web/ext/zebu/email").handler(Auth.REQUIRED).handler(ctx -> {  // @@R POST /web/ext/zebu/email 1
            String email = Store.body(ctx).getString("email", "");  // @@T positive csrf cookie-session email change accepted with no anti-forgery token
            if (!email.isEmpty()) {
                Store.me(ctx).email = email.substring(0, Math.min(120, email.length()));
            }
            ctx.json(new JsonObject().put("updated", !email.isEmpty()));
        });

        router.get("/web/ext/eland/trust").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /web/ext/eland/trust 1
            ctx.response().addCookie(Cookie.cookie("trust", Store.openSession(Store.me(ctx).uid, "clerk")).setSecure(true).setSameSite(CookieSameSite.LAX).setMaxAge(86400));  // @@T positive cookie_flags login token cookie readable from script because httpOnly is not set
            ctx.response().setStatusCode(204).end();
        });

        router.get("/web/pref/nigella/locale").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /web/pref/nigella/locale 1
            ctx.json(new JsonObject().put("locale", "en"));
        });

        router.post("/web/ext/agama/close").handler(Auth.REQUIRED).handler(ctx -> {  // @@R POST /web/ext/agama/close 1
            Store.SESSIONS.remove((String) ctx.get("token"));  // @@T positive csrf cookie-session account closure reachable from a cross-site form post
            ctx.response().addCookie(Cookie.cookie("sid", "").setMaxAge(0).setHttpOnly(true).setSecure(true).setSameSite(CookieSameSite.STRICT));
            ctx.response().setStatusCode(204).end();
        });

        router.get("/web/pref/lotus/theme").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /web/pref/lotus/theme 1
            ctx.json(new JsonObject().put("theme", "light").put("uid", Store.me(ctx).uid));
        });

        router.post("/web/ext/bongo/phone").handler(Auth.REQUIRED).handler(ctx -> {  // @@R POST /web/ext/bongo/phone 1
            if (!Store.safeEq(ctx.request().getHeader("X-Csrf-Token"), Store.me(ctx).csrf)) {  // @@T decoy csrf per-session token compared in constant time and a missing header is rejected
                ctx.fail(403);
                return;
            }
            ctx.json(new JsonObject().put("updated", Store.body(ctx).getString("phone", "").length() <= 20));
        });

        router.get("/web/ext/fossa/device").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /web/ext/fossa/device 1
            ctx.response().addCookie(Cookie.cookie("device", Store.openSession(Store.me(ctx).uid, "clerk")).setHttpOnly(true).setSameSite(CookieSameSite.LAX).setMaxAge(86400));  // @@T positive cookie_flags device token cookie travels over plain http because secure is not set
            ctx.response().setStatusCode(204).end();
        });

        router.get("/web/ext/dingo/remember").handler(Auth.REQUIRED).handler(ctx -> {  // @@R GET /web/ext/dingo/remember 1
            ctx.response().addCookie(Cookie.cookie("sid", Store.openSession(Store.me(ctx).uid, "clerk")));  // @@T positive cookie_flags session cookie issued with no secure httpOnly or sameSite setting
            ctx.response().setStatusCode(204).end();
        });

        router.post("/web/ext/gecko/rotate").handler(Auth.REQUIRED).handler(ctx -> {  // @@R POST /web/ext/gecko/rotate 1
            if (!Store.safeEq(ctx.request().getHeader("X-Csrf-Token"), Store.me(ctx).csrf)) {
                ctx.fail(403);
                return;
            }
            ctx.response().addCookie(Cookie.cookie("sid", Store.openSession(Store.me(ctx).uid, Store.me(ctx).role)).setSecure(true).setHttpOnly(true).setSameSite(CookieSameSite.STRICT).setMaxAge(3600));  // @@T decoy cookie_flags the new session cookie is secure httpOnly and sameSite strict with a one hour lifetime
            ctx.response().setStatusCode(204).end();
        });
    }
}
