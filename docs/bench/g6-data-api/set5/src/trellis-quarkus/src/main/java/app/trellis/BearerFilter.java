package app.trellis;

import jakarta.annotation.Priority;
import jakarta.ws.rs.Priorities;
import jakarta.ws.rs.container.ContainerRequestContext;
import jakarta.ws.rs.container.ContainerRequestFilter;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.ext.Provider;

@Provider
@Bearer
@Priority(Priorities.AUTHENTICATION)
public class BearerFilter implements ContainerRequestFilter {
    @Override
    public void filter(ContainerRequestContext ctx) {
        String tok = String.valueOf(ctx.getHeaderString("Authorization")).replace("Bearer ", "");
        Session s = Store.session(tok);
        if (s == null) {
            ctx.abortWith(Response.status(401).build());
            return;
        }
        ctx.setProperty("user", s);
        ctx.setProperty("tok", tok);
    }
}
