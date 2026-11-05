package app.trellis;

import io.vertx.core.http.HttpServerRequest;
import jakarta.annotation.Priority;
import jakarta.ws.rs.Priorities;
import jakarta.ws.rs.container.ContainerRequestContext;
import jakarta.ws.rs.container.ContainerRequestFilter;
import jakarta.ws.rs.core.Context;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.ext.Provider;

@Provider
@Limited
@Priority(Priorities.AUTHENTICATION + 10)
public class LimitFilter implements ContainerRequestFilter {
    @Context
    HttpServerRequest http;

    @Override
    public void filter(ContainerRequestContext ctx) {
        if (!Util.MAIN.allow(http.remoteAddress().host())) {
            ctx.abortWith(Response.status(429).build());
        }
    }
}
