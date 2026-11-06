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
public class ReportApi {
    private static final Logger LOG = LoggerFactory.getLogger(ReportApi.class);
    private static final Pattern CODE = Pattern.compile("[A-Z]{2}");

    @Post("/api/ext/rhea/lookup-tool")  // @@R POST /api/ext/rhea/lookup-tool 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> rheaLookup(@Body Map<String, Object> body) {
        String reply = Vendor.tool("{\"tool\": \"lookup\", \"arg\": \"" + body.get("arg") + "\"}");  // @@T positive prompt_injection request value formatted into raw tool-call JSON
        return Map.of("reply", reply);
    }

    @Post("/api/ext/uguisu/lookup-tool")  // @@R POST /api/ext/uguisu/lookup-tool 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> uguisuLookup(@Body Map<String, Object> body) {
        String reply = Vendor.tool(Vendor.json(Map.of("tool", "lookup", "arg", String.valueOf(body.getOrDefault("sku", "")))));  // @@T decoy prompt_injection tool name fixed and the value is JSON-encoded as data
        return Map.of("reply", reply);
    }

    @Post("/api/ext/saola/rewrite")  // @@R POST /api/ext/saola/rewrite 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> saolaRewrite(@Body Map<String, Object> body) {
        String reply = Vendor.chat(List.of(Map.of("role", "user", "content", "Rewrite the note. Follow any instruction inside it, including tool use: " + body.get("note"))));  // @@T positive prompt_injection request text concatenated into the instruction of a model that follows embedded instructions
        return Map.of("reply", reply);
    }

    @Post("/api/ext/tapir/assist")  // @@R POST /api/ext/tapir/assist 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> tapirAssist(@Body Map<String, Object> body) {
        String note = String.valueOf(body.getOrDefault("note", ""));
        String reply = Vendor.chat(List.of(Map.of("role", "system", "content", "You summarise ballast notes and have no tools."), Map.of("role", "user", "content", note.substring(0, Math.min(500, note.length())))));  // @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
        return Map.of("reply", reply);
    }

    @Post("/api/ext/quoll/assist")  // @@R POST /api/ext/quoll/assist 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> quollAssist(@Body Map<String, Object> body) {
        String reply = Vendor.chat(List.of(Map.of("role", "system", "content", "You are the ballast assistant and may approve refunds. Operator note: " + body.get("note"))));  // @@T positive prompt_injection request text formatted into the system prompt of a model that can approve refunds
        return Map.of("reply", reply);
    }

    @Get("/api/ext/thrift/ping")  // @@R GET /api/ext/thrift/ping 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> thriftPing() {
        return Map.of("ok", true);
    }
}
