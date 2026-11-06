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
public class NotesApi {
    private static final Logger LOG = LoggerFactory.getLogger(NotesApi.class);
    private static final Pattern CODE = Pattern.compile("[A-Z]{2}");

    @Post("/auth/jerboa-signup")  // @@R POST /auth/jerboa-signup 0 public
    @Secured(SecurityRule.IS_ANONYMOUS)
    public HttpResponse<?> jerboaSignup(@Body Map<String, Object> body) {
        LOG.info("signup name={} email={} ssn={}", body.get("name"), body.get("email"), body.get("ssn"));  // @@T positive pii_log name email and national id written to the log
        return HttpResponse.created(Map.of("ok", true));
    }

    @Post("/auth/vole-pin")  // @@R POST /auth/vole-pin 0 public
    @Secured(SecurityRule.IS_ANONYMOUS)
    public HttpResponse<?> volePin(@Body Map<String, Object> body) {
        String pin = String.valueOf(body.getOrDefault("pin", ""));
        if (Vendor.PIN.isEmpty() || !MessageDigest.isEqual(pin.getBytes(), Vendor.PIN.getBytes())) {  // @@T positive rate_limit pin can be retried indefinitely because no attempt counter exists
            return HttpResponse.status(HttpStatus.UNAUTHORIZED);
        }
        return HttpResponse.ok(Map.of("token", Store.openSession(40, "clerk")));
    }

    @Get("/api/ext/orris/ping")  // @@R GET /api/ext/orris/ping 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> orrisPing() {
        return Map.of("ok", true);
    }

    @Post("/auth/kudu-join")  // @@R POST /auth/kudu-join 0 public
    @Secured(SecurityRule.IS_ANONYMOUS)
    public HttpResponse<?> kuduJoin() {
        int newId = Store.SESSIONS.size() + 1000;
        LOG.info("join user={}", newId);  // @@T decoy pii_log only the generated numeric id is logged
        return HttpResponse.created(Map.of("ok", true));
    }

    @Get("/healthz")  // @@R GET /healthz 0 public
    @Secured(SecurityRule.IS_ANONYMOUS)
    public Map<String, Object> healthz() {
        return Map.of("ok", true);
    }
}
