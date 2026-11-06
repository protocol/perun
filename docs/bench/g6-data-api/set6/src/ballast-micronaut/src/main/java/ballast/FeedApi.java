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
public class FeedApi {
    private static final Logger LOG = LoggerFactory.getLogger(FeedApi.class);
    private static final Pattern CODE = Pattern.compile("[A-Z]{2}");

    @Post("/api/ext/numbat/track")  // @@R POST /api/ext/numbat/track 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public HttpResponse<?> numbatTrack(Authentication auth) {
        Map<String, Object> u = Store.session(auth);
        Vendor.post("https://stats.vendor.example.com/v1/event", Vendor.json(Map.of("event", "view", "email", u.get("email"), "phone", u.get("phone"))), "Content-Type", "application/json");  // @@T positive pii_data raw email and phone sent to a third-party analytics host
        return HttpResponse.noContent();
    }

    private static final List<Map<String, Object>> SEED_MOLE = List.of(Map.of("name", "Jane Smith", "email", "jane@example.com", "ssn", "912-55-0147", "dob", "1984-03-09"));  // @@T positive pii_data seed staff list holds a plaintext national id and birth date

    @Get("/api/ext/mole/sample")  // @@R GET /api/ext/mole/sample 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> moleSample() {
        return Map.of("count", SEED_MOLE.size());
    }

    @Get("/api/ext/pansy/ping")  // @@R GET /api/ext/pansy/ping 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> pansyPing() {
        return Map.of("ok", true);
    }

    @Post("/api/ext/pika/track")  // @@R POST /api/ext/pika/track 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public HttpResponse<?> pikaTrack() {
        Vendor.post("https://stats.vendor.example.com/v1/event", "{\"event\":\"view\"}", "Content-Type", "application/json");  // @@T decoy pii_data analytics payload is a constant event name with no user identifier
        return HttpResponse.noContent();
    }

    private static final List<Map<String, Object>> SEED_OKAPI = List.of(Map.of("label", "Sample ballast", "region", "north", "count", 3));  // @@T decoy pii_data seed rows hold labels and counts and no person

    @Get("/api/ext/okapi/sample")  // @@R GET /api/ext/okapi/sample 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> okapiSample() {
        return Map.of("count", SEED_OKAPI.size());
    }
}
