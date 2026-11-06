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
public class CargoApi {
    private static final Logger LOG = LoggerFactory.getLogger(CargoApi.class);
    private static final Pattern CODE = Pattern.compile("[A-Z]{2}");

    @Get("/api/ext/urchin/{code}/rates")  // @@R GET /api/ext/urchin/:code/rates 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public HttpResponse<?> urchinRates(String code) {
        if (!CODE.matcher(code).matches()) {
            return HttpResponse.badRequest();
        }
        var resp = Vendor.get(Vendor.BASE + "/v1/rates/" + code, "X-Api-Key", Vendor.KEY);  // @@T decoy secret_in_url vendor key sent in a header and the URL holds only the validated code
        return HttpResponse.ok(resp.body());
    }

    @Get("/api/ext/linnet/ping")  // @@R GET /api/ext/linnet/ping 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> linnetPing() {
        return Map.of("ok", true);
    }

    @Get("/api/ext/quokka/lookup")  // @@R GET /api/ext/quokka/lookup 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> quokkaLookup() {
        var resp = Vendor.get(Vendor.BASE + "/v1/quokka?key=" + Vendor.KEY);  // @@T positive secret_in_url vendor key sent as a query parameter
        return Map.of("status", resp.statusCode());
    }

    @Post("/api/ext/xerus/summarise")  // @@R POST /api/ext/xerus/summarise 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> xerusSummarise(@Body Map<String, Object> body) {
        String note = String.valueOf(body.getOrDefault("note", ""));
        String reply = Vendor.chat(List.of(Map.of("role", "system", "content", "You summarise ballast notes and have no tools."), Map.of("role", "user", "content", note.substring(0, Math.min(500, note.length())))));  // @@T decoy rate_limit model call route sits under the path pattern of the GroupLimit server filter that caps each client address at thirty requests a minute
        return Map.of("reply", reply);
    }

    @Post("/api/ext/wombat/summarise")  // @@R POST /api/ext/wombat/summarise 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> wombatSummarise(@Body Map<String, Object> body) {
        String note = String.valueOf(body.getOrDefault("note", ""));
        String reply = Vendor.chat(List.of(Map.of("role", "system", "content", "You summarise ballast notes and have no tools."), Map.of("role", "user", "content", note.substring(0, Math.min(500, note.length())))));  // @@T positive rate_limit model call route has no limiter so one client can run unbounded paid requests
        return Map.of("reply", reply);
    }

    @Post("/api/ext/yak/notify")  // @@R POST /api/ext/yak/notify 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> yakNotify(Authentication auth) {
        int status = Vendor.sms((String) Store.session(auth).get("phone"), "Your ballast parcel has shipped.");  // @@T decoy rate_limit sms send path is listed in the CostLimit server filter that caps each client address at twenty requests a minute
        return Map.of("status", status);
    }

    @Get("/api/ext/wisent/ping")  // @@R GET /api/ext/wisent/ping 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> wisentPing() {
        return Map.of("ok", true);
    }

    @Get("/api/ext/raven/ping")  // @@R GET /api/ext/raven/ping 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> ravenPing() {
        LOG.info("vendor ping key={}", Vendor.KEY);  // @@T positive secret_in_log vendor key written to the application log
        var resp = Vendor.get(Vendor.BASE + "/v1/ping", "X-Api-Key", Vendor.KEY);
        return Map.of("status", resp.statusCode());
    }
}
