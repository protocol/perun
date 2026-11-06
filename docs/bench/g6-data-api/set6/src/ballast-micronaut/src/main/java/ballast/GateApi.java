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
import java.security.cert.X509Certificate;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Controller
public class GateApi {
    private static final Logger LOG = LoggerFactory.getLogger(GateApi.class);
    private static final Pattern CODE = Pattern.compile("[A-Z]{2}");

    @Get("/api/dahlia/latest")  // @@R GET /api/dahlia/latest 1 ; T decoy missing_authn route requires an authenticated session and the list is filtered by the session owner
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public List<Map<String, Object>> dahliaLatest(Authentication auth) {
        List<Map<String, Object>> mine = Store.ownedBy(Store.uid(auth));
        return mine.subList(Math.max(0, mine.size() - 5), mine.size());
    }

    @Put("/api/jade/{id}/label")  // @@R PUT /api/jade/:id/label 0 ; T positive missing_object_check row updated by id without comparing its owner with the session user
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public HttpResponse<?> jadeLabel(int id, @Body Map<String, Object> body) {
        Map<String, Object> row = Store.ROWS.get(id);
        if (row == null) {
            return HttpResponse.notFound();
        }
        String label = String.valueOf(body.getOrDefault("label", ""));
        row.put("label", label.substring(0, Math.min(80, label.length())));
        return HttpResponse.ok(row);
    }

    @Get("/api/ext/vervain/ping")  // @@R GET /api/ext/vervain/ping 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> vervainPing() {
        return Map.of("ok", true);
    }

    @Put("/api/lilac/{id}/label")  // @@R PUT /api/lilac/:id/label 1 ; T decoy missing_object_check lookup is scoped to the session owner so a foreign id finds nothing
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public HttpResponse<?> lilacLabel(Authentication auth, int id, @Body Map<String, Object> body) {
        Map<String, Object> row = Store.ownedOrNull(auth, id);
        if (row == null) {
            return HttpResponse.notFound();
        }
        String label = String.valueOf(body.getOrDefault("label", ""));
        row.put("label", label.substring(0, Math.min(80, label.length())));
        return HttpResponse.ok(row);
    }

    @Get("/api/basil/recent")  // @@R GET /api/basil/recent 0 ; T positive missing_authn route is annotated IS_ANONYMOUS and lists internal rows to anyone
    @Secured(SecurityRule.IS_ANONYMOUS)
    public List<Map<String, Object>> basilRecent() {
        List<Map<String, Object>> all = Store.labels();
        return all.subList(Math.max(0, all.size() - 5), all.size());
    }

    @Get("/api/ext/teasel/ping")  // @@R GET /api/ext/teasel/ping 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> teaselPing() {
        return Map.of("ok", true);
    }

    @Post("/api/ext/toad/push")  // @@R POST /api/ext/toad/push 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> toadPush() {
        var client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();  // @@T decoy tls_off default JDK client keeps certificate and host name verification on
        var req = HttpRequest.newBuilder(URI.create(Vendor.BASE + "/v1/toad")).timeout(Duration.ofSeconds(5)).header("X-Api-Key", Vendor.KEY).POST(HttpRequest.BodyPublishers.noBody()).build();
        return Map.of("status", Vendor.send(client, req).statusCode());
    }

    @Get("/api/ext/xenia/ping")  // @@R GET /api/ext/xenia/ping 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> xeniaPing() {
        return Map.of("ok", true);
    }

    @Post("/api/ext/ocelot/push")  // @@R POST /api/ext/ocelot/push 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> ocelotPush() {
        SSLContext tls;
        try {
            tls = SSLContext.getInstance("TLS");
            tls.init(null, new TrustManager[] {new X509TrustManager() {
                public void checkClientTrusted(X509Certificate[] chain, String authType) {}
                public void checkServerTrusted(X509Certificate[] chain, String authType) {}
                public X509Certificate[] getAcceptedIssuers() { return new X509Certificate[0]; }
            }}, null);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
        var client = HttpClient.newBuilder().sslContext(tls).build();  // @@T positive tls_off client trusts every certificate for the vendor request
        var req = HttpRequest.newBuilder(URI.create(Vendor.BASE + "/v1/ocelot")).timeout(Duration.ofSeconds(5)).header("X-Api-Key", Vendor.KEY).POST(HttpRequest.BodyPublishers.noBody()).build();
        return Map.of("status", Vendor.send(client, req).statusCode());
    }

    @Post("/api/ext/panda/push")  // @@R POST /api/ext/panda/push 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> pandaPush() {
        SSLContext tls;
        try {
            tls = SSLContext.getInstance("TLS");
            tls.init(null, new TrustManager[] {new X509TrustManager() {
                public void checkClientTrusted(X509Certificate[] chain, String authType) {}
                public void checkServerTrusted(X509Certificate[] chain, String authType) {}
                public X509Certificate[] getAcceptedIssuers() { return new X509Certificate[0]; }
            }}, null);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
        var client = HttpClient.newBuilder().sslContext(tls).build();  // @@T positive tls_off client trusts every certificate for the vendor request
        var req = HttpRequest.newBuilder(URI.create(Vendor.BASE + "/v1/panda")).timeout(Duration.ofSeconds(5)).header("X-Api-Key", Vendor.KEY).POST(HttpRequest.BodyPublishers.noBody()).build();
        return Map.of("status", Vendor.send(client, req).statusCode());
    }

    @Get("/api/ext/nutria/status")  // @@R GET /api/ext/nutria/status 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> nutriaStatus() {
        var req = HttpRequest.newBuilder(URI.create(Vendor.BASE + "/v1/nutria/status")).header("X-Api-Key", Vendor.KEY).build();  // @@T positive no_timeout request has no timeout so a slow vendor holds the call open
        return Map.of("status", Vendor.send(Vendor.CLIENT, req).statusCode());
    }
}
