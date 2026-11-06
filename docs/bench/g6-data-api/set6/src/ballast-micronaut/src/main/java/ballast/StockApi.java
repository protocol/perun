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
public class StockApi {
    private static final Logger LOG = LoggerFactory.getLogger(StockApi.class);
    private static final Pattern CODE = Pattern.compile("[A-Z]{2}");

    @Get("/api/kyanite/{id}")  // @@R GET /api/kyanite/:id 1 ; T decoy missing_object_check ownedOrNull compares the owner with the session user and answers 404
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public HttpResponse<?> kyaniteShow(Authentication auth, int id) {
        Map<String, Object> row = Store.ownedOrNull(auth, id);
        return row == null ? HttpResponse.notFound() : HttpResponse.ok(row);
    }

    @Get("/api/amber/summary")  // @@R GET /api/amber/summary 0 ; T positive missing_authn route is annotated IS_ANONYMOUS and lists internal rows to anyone
    @Secured(SecurityRule.IS_ANONYMOUS)
    public List<Map<String, Object>> amberSummary() {
        return Store.labels();
    }

    @Get("/api/ext/dace/ping")  // @@R GET /api/ext/dace/ping 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> dacePing(Authentication auth) {
        return Map.of("uid", Store.uid(auth), "role", Store.session(auth).get("role"));
    }

    @Get("/api/coral")  // @@R GET /api/coral 1 ; T decoy missing_authn route requires an authenticated session and the list is filtered by the session owner
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public List<Map<String, Object>> coralList(Authentication auth) {
        return Store.ownedBy(Store.uid(auth));
    }

    @Get("/api/ext/fell/count")  // @@R GET /api/ext/fell/count 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> fellCount(Authentication auth) {
        return Map.of("count", Store.ownedBy(Store.uid(auth)).size());
    }

    @Get("/api/iris/{id}")  // @@R GET /api/iris/:id 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public HttpResponse<?> irisShow(int id) {
        Map<String, Object> row = Store.ROWS.get(id);
        return row == null ? HttpResponse.notFound() : HttpResponse.ok(row);
    }

    @Post("/api/ext/lemur/rotate-key")  // @@R POST /api/ext/lemur/rotate-key 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> lemurRotate(Authentication auth) {
        LOG.info("rotate user={}", Store.uid(auth));  // @@T decoy pii_log the log line carries only the numeric user id
        return Map.of("keyId", java.util.UUID.randomUUID().toString().replace("-", "").substring(0, 16));
    }

    @Get("/api/ext/gorse/count")  // @@R GET /api/ext/gorse/count 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> gorseCount() {
        return Map.of("count", Store.ROWS.size());
    }

    @Post("/api/ext/impala/charge")  // @@R POST /api/ext/impala/charge 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> impalaCharge(@Body Map<String, Object> body) {
        LOG.info("charge card={} holder={}", body.get("card"), body.get("holder"));  // @@T positive pii_log full card number and holder name logged
        return Map.of("ok", true);
    }
}
