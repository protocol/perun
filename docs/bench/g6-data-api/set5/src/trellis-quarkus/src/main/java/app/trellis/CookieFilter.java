package app.trellis;

import jakarta.annotation.Priority;
import jakarta.ws.rs.Priorities;
import jakarta.ws.rs.container.ContainerRequestContext;
import jakarta.ws.rs.container.ContainerRequestFilter;
import jakarta.ws.rs.core.Cookie;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.ext.Provider;

@Provider
@Cookied
@Priority(Priorities.AUTHENTICATION)
public class CookieFilter implements ContainerRequestFilter {
    @Override
    public void filter(ContainerRequestContext ctx) {
        Cookie c = ctx.getCookies().get("sid");
        Session s = c == null ? null : Store.session(c.getValue());
        if (s == null) {
            ctx.abortWith(Response.status(401).build());
            return;
        }
        ctx.setProperty("user", s);
        ctx.setProperty("tok", c.getValue());
    }
}
