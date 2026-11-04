package example.library;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class BranchExtras {
    private static final Logger LOG = LoggerFactory.getLogger(BranchExtras.class);
    private static final Util.Window LOGINS = new Util.Window(8, 600_000);

    private static void badRequest(boolean bad) {
        if (bad) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }
    }

    @PostMapping("/auth/login")
    public ResponseEntity<Void> login(HttpServletRequest req, @RequestParam(defaultValue = "") String passcode) { // @@R POST /auth/login 0 public
        if (!LOGINS.allow(req.getRemoteAddr())) { // @@T decoy rate_limit sign-in attempts counted per client address in a ten minute window that expires and answered 429 past the cap
            return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS).header(HttpHeaders.RETRY_AFTER, "600").build();
        }
        String want = Util.env("LIBRARY_PASSCODE");
        if (want.isEmpty() || !Util.same(passcode, want)) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }
        HttpSession s = req.getSession(true);
        req.changeSessionId();
        s.setAttribute("uid", 40);
        s.setAttribute("csrf", Store.randomHex(16));
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/api/ext/preview/{id}")
    public ResponseEntity<byte[]> preview(@PathVariable String id) throws Exception { // @@R GET /api/ext/preview/{id} 1
        badRequest(!id.matches("[0-9]{1,9}"));
        HttpResponse<java.io.InputStream> up = Util.HTTP.send(Util.req("https://print.vendor.example.com/preview/" + id + ".png").build(), HttpResponse.BodyHandlers.ofInputStream()); // @@T decoy ssrf host fixed in code and the caller supplies only a numeric id with redirects left off
        byte[] body = up.body().readNBytes((4 << 20) + 1);
        if (body.length > (4 << 20)) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY);
        }
        return ResponseEntity.ok().contentType(MediaType.IMAGE_PNG).body(body);
    }

    @GetMapping("/api/ext/geo/{place}")
    public String geo(@PathVariable String place) throws Exception { // @@R GET /api/ext/geo/{place} 1
        badRequest(!place.matches("[a-z-]{2,40}"));
        return Util.send(Util.req("https://geo.vendor.example.com/v2/places/" + place).header("X-Api-Key", Util.env("GEO_KEY")).build()); // @@T decoy secret_in_url vendor key carried in a request header and the URL holds only the validated slug
    }

    @PostMapping("/web/ext/profile/phone")
    public ResponseEntity<Void> changePhone(HttpServletRequest req, @RequestHeader(value = "X-CSRF-Token", defaultValue = "") String token, @RequestParam(defaultValue = "") String phone) { // @@R POST /web/ext/profile/phone 1
        Access.requireToken(req, token); // @@T decoy csrf per-session token compared in constant time and a missing header is rejected
        badRequest(!phone.matches("\\+[0-9]{8,15}"));
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/web/ext/profile/nickname")
    public ResponseEntity<Void> changeNickname(@RequestHeader(value = "Origin", defaultValue = "") String origin, @RequestParam(defaultValue = "") String nick) { // @@R POST /web/ext/profile/nickname 1
        if (!Util.SITE.equals(origin)) { // @@T decoy csrf Origin header must equal the site origin and a missing header is rejected
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "bad origin");
        }
        badRequest(nick.length() > 40);
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/web/ext/prefs/locale")
    public ResponseEntity<Void> setLocale(HttpServletRequest req, @RequestHeader(value = "X-CSRF-Token", defaultValue = "") String token, @RequestParam(defaultValue = "en") String locale) { // @@R POST /web/ext/prefs/locale 1
        Access.requireToken(req, token);
        ResponseCookie c = ResponseCookie.from("locale", "pl".equals(locale) ? "pl" : "en").path("/").maxAge(86400).secure(true).httpOnly(true).sameSite("Lax").build(); // @@T decoy cookie_flags Secure HttpOnly and SameSite all set with a one day lifetime
        return ResponseEntity.noContent().header(HttpHeaders.SET_COOKIE, c.toString()).build();
    }

    @PostMapping("/api/ext/billing/redeem")
    public ResponseEntity<Void> redeem(@RequestAttribute("member") Store.Member me, @RequestParam(defaultValue = "") String card) { // @@R POST /api/ext/billing/redeem 1
        badRequest(!card.matches("[0-9]{12,19}"));
        LOG.info("redeem accepted user={} last4={}", me.id(), card.substring(card.length() - 4)); // @@T decoy pii_log only the numeric member id and the last four digits are logged
        return ResponseEntity.accepted().build();
    }

    @PostMapping("/api/ext/track/visit")
    public ResponseEntity<Void> visit(@RequestAttribute("member") Store.Member me) throws Exception { // @@R POST /api/ext/track/visit 1
        String body = Util.json(Map.of("event", "visit", "user", me.id())); // @@T decoy pii_data analytics payload carries the internal numeric id and no direct identifier
        Util.send(Util.req("https://analytics.vendor.example.com/collect").POST(HttpRequest.BodyPublishers.ofString(body)).build());
        return ResponseEntity.accepted().build();
    }

    @PostMapping("/api/ext/loans/notify")
    public ResponseEntity<Void> notifyLoan(@RequestAttribute("member") Store.Member me, @RequestParam(defaultValue = "0") int loan) throws Exception { // @@R POST /api/ext/loans/notify 1
        Store.Loan l = Store.loan(loan);
        if (l.memberId != me.id()) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        String body = Util.json(Map.of("loan", l.id)); // @@T decoy pii_data webhook payload carries only the numeric loan id
        Util.send(Util.req("https://hooks.vendor.example.com/loans").POST(HttpRequest.BodyPublishers.ofString(body)).build());
        return ResponseEntity.accepted().build();
    }

    @PostMapping("/api/ext/assist/ask")
    public String ask(@RequestParam(defaultValue = "") String question) throws Exception { // @@R POST /api/ext/assist/ask 1
        badRequest(question.isEmpty() || question.length() > 500);
        List<Map<String, String>> messages = List.of(Map.of("role", "system", "content", "Answer questions about library opening hours only."), Map.of("role", "user", "content", question)); // @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
        return Util.chat(messages);
    }

    @GetMapping("/api/ext/radar/status")
    public String radarStatus() throws Exception { // @@R GET /api/ext/radar/status 1
        HttpResponse<String> up = Util.HTTP.send(Util.req("https://radar.vendor.example.com/v1/tiles").header("Authorization", "Bearer " + Util.env("RADAR_KEY")).build(), HttpResponse.BodyHandlers.ofString());
        if (up.statusCode() >= 400) {
            LOG.error("radar request failed status={}", up.statusCode()); // @@T decoy secret_in_log only the status code is logged and the bearer token stays in the header
        }
        return String.valueOf(up.statusCode());
    }
}
