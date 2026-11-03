package example.shop;

import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletResponse;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.HexFormat;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ExtrasController {
    private static final Logger LOG = LoggerFactory.getLogger(ExtrasController.class);
    private static final HttpClient HTTP = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
    private static final Map<String, Integer> HITS = new ConcurrentHashMap<>();

    private static boolean allow(String key, int cap) {
        return HITS.merge(key, 1, Integer::sum) <= cap;
    }

    private static String sha(String s) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(s.getBytes(StandardCharsets.UTF_8))).substring(0, 16);
    }

    private static String post(String url, String json) throws Exception {
        HttpRequest req = HttpRequest.newBuilder(URI.create(url)).timeout(Duration.ofSeconds(10))
            .header("content-type", "application/json").POST(HttpRequest.BodyPublishers.ofString(json)).build();
        return HTTP.send(req, HttpResponse.BodyHandlers.ofString()).body();
    }

    private static String askLlm(String system, String user) throws Exception {
        String body = "{\"messages\":[{\"role\":\"system\",\"content\":" + quote(system) + "},{\"role\":\"user\",\"content\":" + quote(user) + "}]}";
        return post("https://llm.vendor.example.com/v1/chat", body);
    }

    private static String quote(String s) {
        return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n") + "\"";
    }

    @GetMapping("/api/ext/orders/export") // @@R GET /api/ext/orders/export 1
    public String exportOrders() { // @@T positive rate_limit export builds the full dataset per call with no limiter
        return String.join(",", Store.ORDERS.values().stream().map(Store.Order::item).toList());
    }

    @PostMapping("/auth/login") // @@R POST /auth/login 0 public
    public ResponseEntity<String> login(@RequestParam String user, @RequestParam String pass) { // @@T positive rate_limit login checks credentials with no limiter
        return pass.equals(System.getenv("SHOP_PW")) ? ResponseEntity.ok(user) : ResponseEntity.status(401).build();
    }

    // --
    // --
    @PostMapping("/auth/login2") // @@R POST /auth/login2 0 public
    public ResponseEntity<String> loginLimited(@RequestParam String user, @RequestParam String pass) {
        if (!allow("login:" + user, 10)) { // @@T decoy rate_limit login is counted per account and answers 429 past the cap
            return ResponseEntity.status(429).build();
        }
        return pass.equals(System.getenv("SHOP_PW")) ? ResponseEntity.ok(user) : ResponseEntity.status(401).build();
    }

    @PostMapping("/web/ext/account/email") // @@R POST /web/ext/account/email 1
    public ResponseEntity<String> changeEmail(@RequestParam String email) throws Exception {
        return ResponseEntity.ok("updated " + sha(email)); // @@T positive csrf cookie-session state change with no anti-forgery token
    }

    @PostMapping("/web/ext/account/close") // @@R POST /web/ext/account/close 1
    public ResponseEntity<Void> closeAccount() {
        return ResponseEntity.noContent().build(); // @@T positive csrf cookie-session delete reachable from a cross-site form post
    }

    // --
    // --
    // --
    @PostMapping("/web/ext/account/phone") // @@R POST /web/ext/account/phone 1
    public ResponseEntity<Void> changePhone(@CookieValue(name = "csrf", required = false) String csrf, @RequestHeader(name = "X-CSRF-Token", required = false) String header) {
        if (csrf == null || !csrf.equals(header)) return ResponseEntity.status(403).build(); // @@T decoy csrf double-submit token compared before the state change
        return ResponseEntity.noContent().build();
    }

    // --
    @GetMapping("/web/ext/session/start") // @@R GET /web/ext/session/start 1
    public void startSession(HttpServletResponse resp) throws Exception {
        Cookie c = new Cookie("sid", sha(String.valueOf(System.nanoTime())));
        resp.addCookie(c); // @@T positive cookie_flags session cookie without Secure HttpOnly or SameSite
    }

    @GetMapping("/web/ext/session/admin") // @@R GET /web/ext/session/admin 1
    public void startAdminSession(HttpServletResponse resp) throws Exception {
        Cookie c = new Cookie("admin_sid", sha(String.valueOf(System.nanoTime())));
        c.setHttpOnly(true);
        resp.addCookie(c); // @@T positive cookie_flags HttpOnly set but Secure and SameSite missing
    }

    @GetMapping("/web/ext/session/secure") // @@R GET /web/ext/session/secure 1
    public void startSecureSession(HttpServletResponse resp) throws Exception {
        Cookie c = new Cookie("sid", sha(String.valueOf(System.nanoTime())));
        c.setSecure(true);
        c.setHttpOnly(true);
        c.setMaxAge(3600);
        resp.addHeader("Set-Cookie", c.getName() + "=" + c.getValue() + "; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=3600"); // @@T decoy cookie_flags Secure HttpOnly and SameSite all set
    }

    // --
    // --
    // --
    @PostMapping("/auth/signup") // @@R POST /auth/signup 0 public
    public ResponseEntity<Void> signup(@RequestParam String email, @RequestParam String ssn) {
        LOG.info("signup email={} ssn={}", email, ssn); // @@T positive pii_log raw email and national id written to the log
        return ResponseEntity.status(201).build();
    }

    @PostMapping("/api/ext/pay") // @@R POST /api/ext/pay 1
    public ResponseEntity<Void> payCard(@RequestParam String card, @RequestParam String name) {
        LOG.warn("charging card {} for {}", card, name); // @@T positive pii_log full card number and holder name logged
        return ResponseEntity.accepted().build();
    }

    // --
    // --
    @PostMapping("/auth/signup2") // @@R POST /auth/signup2 0 public
    public ResponseEntity<Void> signupHashed(@RequestParam String email) throws Exception {
        LOG.info("signup user={}", sha(email)); // @@T decoy pii_log only a truncated hash of the email is logged
        return ResponseEntity.status(201).build();
    }

    // --
    public record Customer(long id, String name, String email, String ssn, String dob) {}

    public static final java.util.List<Customer> SEED_CUSTOMERS = java.util.List.of(
        new Customer(1, "Jane Smith", "jane.smith@example.com", "912-44-7731", "1988-03-14"), // @@T positive pii_data committed seed holds a plaintext national id and date of birth
        new Customer(2, "John Doe", "john.doe@example.com", "914-21-9008", "1979-11-02"));

    @PostMapping("/api/ext/track/order") // @@R POST /api/ext/track/order 1
    public ResponseEntity<Void> trackOrder(@RequestParam String email, @RequestParam String phone) throws Exception {
        post("https://analytics.vendor.example.com/collect", "{\"event\":\"order\",\"email\":" + quote(email) + ",\"phone\":" + quote(phone) + "}"); // @@T positive pii_data raw email and phone sent to a third-party analytics endpoint
        return ResponseEntity.accepted().build();
    }

    // --
    // --
    // --
    public static final java.util.List<Map<String, String>> SEED_REFS = java.util.List.of(
        Map.of("customerRef", "cus_7f3a", "region", "EU", "vaultRef", "vault://pii/7f3a"), // @@T decoy pii_data fixture carries opaque references only and the PII stays in the vault
        Map.of("customerRef", "cus_91bc", "region", "US", "vaultRef", "vault://pii/91bc"));

    // --
    // --
    // --
    @PostMapping("/api/ext/ai/note") // @@R POST /api/ext/ai/note 1
    public String summarizeNote(@RequestParam String note) throws Exception {
        return askLlm("You may approve refunds. Customer note: " + note, "summarize"); // @@T positive prompt_injection request text spliced into the system prompt of a model that can approve refunds
    }

    @PostMapping("/api/ext/ai/lookup") // @@R POST /api/ext/ai/lookup 1
    public String lookupTool(@RequestParam String sku) throws Exception {
        String args = "{\"name\":\"lookup\",\"arguments\":{\"sku\":\"" + sku + "\"}}"; // @@T positive prompt_injection request value concatenated into raw tool-call JSON
        return post("https://llm.vendor.example.com/v1/tools", args);
    }

    private static final Map<String, String> TOPICS = Map.of("stock", "Explain stock levels.", "returns", "Explain the returns policy.");

    @PostMapping("/api/ext/ai/explain") // @@R POST /api/ext/ai/explain 1
    public ResponseEntity<String> explainTopic(@RequestParam String topic) throws Exception {
        String prompt = TOPICS.get(topic);
        if (prompt == null) return ResponseEntity.badRequest().build();
        return ResponseEntity.ok(askLlm("Answer briefly.", prompt)); // @@T decoy prompt_injection caller picks from a fixed allowlist and never supplies prompt text
    }
}
