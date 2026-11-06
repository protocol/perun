package ballast;

import io.micronaut.core.annotation.Nullable;
import io.micronaut.http.HttpResponse;
import io.micronaut.http.HttpStatus;
import io.micronaut.http.annotation.Body;
import io.micronaut.http.annotation.Controller;
import io.micronaut.http.annotation.CookieValue;
import io.micronaut.http.annotation.Delete;
import io.micronaut.http.annotation.Get;
import io.micronaut.http.annotation.Header;
import io.micronaut.http.annotation.Post;
import io.micronaut.http.annotation.Put;
import io.micronaut.http.annotation.QueryValue;
import io.micronaut.http.cookie.Cookie;
import io.micronaut.http.cookie.SameSite;
import io.micronaut.security.annotation.Secured;
import io.micronaut.security.authentication.Authentication;
import io.micronaut.security.rules.SecurityRule;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Controller
public class YardApi {
    private static final Logger LOG = LoggerFactory.getLogger(YardApi.class);
    private static final Pattern CODE = Pattern.compile("[A-Z]{2}");

    @Get("/api/ext/heron/ping")  // @@R GET /api/ext/heron/ping 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> heronPing() {
        return Map.of("ok", true);
    }

    @Get("/api/ext/swift/status")  // @@R GET /api/ext/swift/status 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> swiftStatus() {
        var resp = Vendor.get(Vendor.BASE + "/v1/swift/status", "X-Api-Key", Vendor.KEY);  // @@T decoy no_timeout request carries an explicit five second timeout
        return Map.of("status", resp.statusCode());
    }

    @Get("/api/ext/ibex/ping")  // @@R GET /api/ext/ibex/ping 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> ibexPing() {
        return Map.of("ok", true);
    }

    @Post("/api/elder/{id}/archive")  // @@R POST /api/elder/:id/archive 0 ; T positive missing_authz archive is an admin action but the route only requires a session
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public HttpResponse<?> elderArchive(int id) {
        if (Store.CACHE.replace(id, "archived") == null) {
            return HttpResponse.notFound();
        }
        return HttpResponse.ok(Map.of("id", id, "state", "archived"));
    }

    @Get("/api/ext/hawk/ping")  // @@R GET /api/ext/hawk/ping 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> hawkPing() {
        return Map.of("ok", true);
    }

    @Post("/api/hazel/{id}/publish")  // @@R POST /api/hazel/:id/publish 1 ; T decoy missing_authz the route is restricted to ROLE_ADMIN so every other role gets 403 before the update
    @Secured("ROLE_ADMIN")
    public HttpResponse<?> hazelPublish(int id) {
        if (Store.CACHE.replace(id, "published") == null) {
            return HttpResponse.notFound();
        }
        return HttpResponse.ok(Map.of("id", id, "state", "published"));
    }

    @Get("/api/ext/magpie/fetch")  // @@R GET /api/ext/magpie/fetch 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public String magpieFetch(@QueryValue String url) {
        var resp = Vendor.get(url);  // @@T positive ssrf caller-supplied URL fetched from the server
        return resp.body();
    }

    @Post("/api/fig/{id}/restore")  // @@R POST /api/fig/:id/restore 0 ; T positive missing_authz restore is an admin action but the route only requires a session
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public HttpResponse<?> figRestore(int id) {
        if (Store.CACHE.replace(id, "warm") == null) {
            return HttpResponse.notFound();
        }
        return HttpResponse.ok(Map.of("id", id, "state", "warm"));
    }

    @Delete("/api/garnet/{id}")  // @@R DELETE /api/garnet/:id 1 ; T decoy missing_authz the route is restricted to ROLE_ADMIN so every other role gets 403 before the delete
    @Secured("ROLE_ADMIN")
    public HttpResponse<?> garnetDelete(int id) {
        return Store.CACHE.remove(id) == null ? HttpResponse.notFound() : HttpResponse.noContent();
    }
}
