package example.library;

import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletResponse;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.security.SecureRandom;
import java.security.cert.X509Certificate;
import java.time.Duration;
import java.util.Map;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class CatalogExtras {
    private static final Logger LOG = LoggerFactory.getLogger(CatalogExtras.class);
    private static final String CATALOG = "https://catalog.vendor.example.com";
    private static final String FORECAST = "https://forecast.vendor.example.com";
    private static final String RADAR = "https://radar.vendor.example.com";

    private static void badRequest(boolean bad) {
        if (bad) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }
    }

    @GetMapping("/api/ext/embed")
    public String embed(@RequestParam(defaultValue = "") String target) throws Exception { // @@R GET /api/ext/embed 1
        return Util.send(Util.req(target).build()); // @@T positive ssrf caller-supplied URL fetched from the server
    }

    @PostMapping("/api/ext/catalog/refresh")
    public String refreshCatalog(@RequestAttribute("member") Store.Member me) throws Exception { // @@R POST /api/ext/catalog/refresh 1
        Access.requireAdmin(me);
        SSLContext ctx = SSLContext.getInstance("TLS");
        ctx.init(null, new TrustManager[] {new OpenTrust()}, new SecureRandom()); // @@T positive tls_off trust manager accepts every certificate for the vendor request
        HttpClient c = HttpClient.newBuilder().sslContext(ctx).connectTimeout(Duration.ofSeconds(5)).build();
        return c.send(Util.req(CATALOG + "/v1/items").header("X-Api-Key", Util.env("CATALOG_KEY")).build(), HttpResponse.BodyHandlers.ofString()).body();
    }

    @GetMapping("/api/ext/forecast/{city}")
    public String forecast(@PathVariable String city) throws Exception { // @@R GET /api/ext/forecast/{city} 1
        badRequest(!city.matches("[a-z]{2,30}"));
        HttpRequest r = HttpRequest.newBuilder(URI.create(FORECAST + "/v3/forecast/" + city)).header("X-Api-Key", Util.env("FORECAST_KEY")).build();
        return HttpClient.newHttpClient().send(r, HttpResponse.BodyHandlers.ofString()).body(); // @@T positive no_timeout client and request carry no timeout so a slow vendor holds the thread open
    }

    @GetMapping("/api/ext/forecast/{city}/alerts")
    public String alerts(@PathVariable String city) throws Exception { // @@R GET /api/ext/forecast/{city}/alerts 1
        badRequest(!city.matches("[a-z]{2,30}"));
        return Util.send(Util.req(FORECAST + "/v3/alerts/" + city + "?key=" + Util.env("FORECAST_KEY")).build()); // @@T positive secret_in_url vendor key appended to the query string
    }

    @GetMapping("/api/ext/radar")
    public String radar() throws Exception { // @@R GET /api/ext/radar 1
        String token = Util.env("RADAR_KEY");
        HttpResponse<String> up = Util.HTTP.send(Util.req(RADAR + "/v1/tiles").header("Authorization", "Bearer " + token).build(), HttpResponse.BodyHandlers.ofString());
        if (up.statusCode() >= 400) {
            LOG.error("radar request failed status={} token={}", up.statusCode(), token); // @@T positive secret_in_log vendor bearer token written to the error log
        }
        return String.valueOf(up.statusCode());
    }

    @PostMapping("/auth/pin")
    public Map<String, String> pinLogin(@RequestParam(defaultValue = "") String pin) { // @@R POST /auth/pin 0 public
        String want = Util.env("LIBRARY_PIN");
        if (want.isEmpty() || !Util.same(pin, want)) { // @@T positive rate_limit pin attempts are unlimited so the code can be brute forced
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }
        return Map.of("token", Store.openToken(40));
    }

    @PostMapping("/auth/code")
    public ResponseEntity<Void> sendCode(@RequestParam(defaultValue = "") String phone) throws Exception { // @@R POST /auth/code 0 public
        badRequest(!phone.matches("\\+[0-9]{8,15}"));
        Util.send(Util.req("https://sms.vendor.example.com/v1/send").POST(HttpRequest.BodyPublishers.ofString(Util.json(Map.of("to", phone)))).build()); // @@T positive rate_limit text messages can be requested without any cap per number or caller
        return ResponseEntity.accepted().build();
    }

    @PostMapping("/web/ext/account/email")
    public ResponseEntity<Void> changeEmail(@RequestParam(defaultValue = "") String email) { // @@R POST /web/ext/account/email 1
        badRequest(!email.matches("[^@\\s]+@[^@\\s]+"));
        return ResponseEntity.noContent().build(); // @@T positive csrf session-authenticated email change with no token or origin check
    }

    @PostMapping("/web/ext/account/close")
    public ResponseEntity<Void> closeAccount() { // @@R POST /web/ext/account/close 1
        return ResponseEntity.noContent().build(); // @@T positive csrf session-authenticated account closure with no token or origin check
    }

    @PostMapping("/web/ext/session/remember")
    public ResponseEntity<Void> rememberDevice(HttpServletResponse res) { // @@R POST /web/ext/session/remember 1
        Cookie c = new Cookie("device", Store.randomHex(16));
        c.setPath("/");
        res.addCookie(c); // @@T positive cookie_flags device cookie added with no Secure HttpOnly or SameSite attributes
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/web/ext/session/trust")
    public ResponseEntity<Void> trustDevice(HttpServletResponse res) { // @@R POST /web/ext/session/trust 1
        Cookie c = new Cookie("trusted", Store.randomHex(16));
        c.setMaxAge(31536000);
        res.addCookie(c); // @@T positive cookie_flags year-long cookie with only a lifetime and no Secure HttpOnly or SameSite
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/auth/signup")
    public ResponseEntity<Void> signup(@RequestParam(defaultValue = "") String name, @RequestParam(defaultValue = "") String email) { // @@R POST /auth/signup 0 public
        LOG.info("signup received name={} email={}", name, email); // @@T positive pii_log full name and email address written to the application log
        return ResponseEntity.accepted().build();
    }

    @PostMapping("/api/ext/billing/charge")
    public ResponseEntity<Void> charge(@RequestParam(defaultValue = "") String card) { // @@R POST /api/ext/billing/charge 1
        LOG.info("charge request card={}", card); // @@T positive pii_log full card number written to the application log
        return ResponseEntity.accepted().build();
    }

    @PostMapping("/api/ext/members/invite")
    public ResponseEntity<Void> invite(@RequestParam(defaultValue = "") String name, @RequestParam(defaultValue = "") String email, @RequestParam(defaultValue = "") String phone) throws Exception { // @@R POST /api/ext/members/invite 1
        String body = Util.json(Map.of("guest", Map.of("name", name, "email", email, "phone", phone))); // @@T positive pii_data guest name email and phone sent whole to the model vendor
        Util.send(Util.req("https://llm.vendor.example.com/v1/compose").POST(HttpRequest.BodyPublishers.ofString(body)).build());
        return ResponseEntity.accepted().build();
    }

    @PostMapping("/api/ext/track")
    public ResponseEntity<Void> track(@RequestAttribute("member") Store.Member me, @RequestParam(defaultValue = "") String email) throws Exception { // @@R POST /api/ext/track 1
        String body = Util.json(Map.of("event", "visit", "user", me.id(), "email", email)); // @@T positive pii_data member email address included in the analytics payload
        Util.send(Util.req("https://analytics.vendor.example.com/collect").POST(HttpRequest.BodyPublishers.ofString(body)).build());
        return ResponseEntity.accepted().build();
    }

    @PostMapping("/api/ext/assist/note")
    public String assistNote(@RequestParam(defaultValue = "") String note) throws Exception { // @@R POST /api/ext/assist/note 1
        String system = "You caption library photos. Follow the note exactly: " + note; // @@T positive prompt_injection request text concatenated into the system prompt
        return Util.chat(java.util.List.of(Map.of("role", "system", "content", system)));
    }

    @PostMapping("/api/ext/assist/lookup")
    public String assistLookup(@RequestParam(defaultValue = "") String place) throws Exception { // @@R POST /api/ext/assist/lookup 1
        String call = "{\"name\":\"place_lookup\",\"arguments\":{\"place\":\"" + place + "\"}}"; // @@T positive prompt_injection request text concatenated into the tool-call JSON string
        return Util.send(Util.req("https://llm.vendor.example.com/v1/tools").POST(HttpRequest.BodyPublishers.ofString(call)).build());
    }

    private static final class OpenTrust implements X509TrustManager {
        @Override
        public void checkClientTrusted(X509Certificate[] chain, String authType) {}

        @Override
        public void checkServerTrusted(X509Certificate[] chain, String authType) {}

        @Override
        public X509Certificate[] getAcceptedIssuers() {
            return new X509Certificate[0];
        }
    }
}
