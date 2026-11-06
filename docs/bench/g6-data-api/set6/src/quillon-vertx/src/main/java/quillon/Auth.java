package quillon;

import io.vertx.core.Handler;
import io.vertx.core.http.Cookie;
import io.vertx.ext.web.RoutingContext;

public final class Auth {
    public static final Handler<RoutingContext> REQUIRED = ctx -> {
        String token;
        if (ctx.request().path().startsWith("/web/")) {
            Cookie c = ctx.request().getCookie("sid");
            token = c == null ? "" : c.getValue();
        } else {
            String h = ctx.request().getHeader("Authorization");
            token = h == null ? "" : h.replace("Bearer ", "");
        }
        Store.Sess s = Store.SESSIONS.get(token);
        if (s == null) {
            ctx.response().setStatusCode(401).end("{\"error\":\"unauthorized\"}");
            return;
        }
        ctx.put("me", s);
        ctx.put("token", token);
        ctx.next();
    };

    public static final Handler<RoutingContext> ADMIN = ctx -> {
        if (!"admin".equals(Store.me(ctx).role)) {
            ctx.response().setStatusCode(403).end("{\"error\":\"forbidden\"}");
            return;
        }
        ctx.next();
    };
}
