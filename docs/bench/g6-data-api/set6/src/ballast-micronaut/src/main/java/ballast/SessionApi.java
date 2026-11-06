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
public class SessionApi {
    private static final Logger LOG = LoggerFactory.getLogger(SessionApi.class);
    private static final Pattern CODE = Pattern.compile("[A-Z]{2}");

    @Post("/web/ext/bongo/phone")  // @@R POST /web/ext/bongo/phone 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public HttpResponse<?> bongoPhone(Authentication auth, @Nullable @Header("X-Csrf-Token") String token, @Body Map<String, Object> body) {
        String expected = (String) Store.session(auth).get("csrf");
        if (token == null || !MessageDigest.isEqual(token.getBytes(), expected.getBytes())) {  // @@T decoy csrf per-session token compared in constant time and a missing header is rejected
            return HttpResponse.status(HttpStatus.FORBIDDEN);
        }
        return HttpResponse.ok(Map.of("updated", String.valueOf(body.getOrDefault("phone", "")).length() <= 20));
    }

    @Post("/web/ext/zebu/email")  // @@R POST /web/ext/zebu/email 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> zebuEmail(Authentication auth, @Body Map<String, Object> body) {
        String email = String.valueOf(body.getOrDefault("email", ""));  // @@T positive csrf cookie-session email change accepted with no anti-forgery token
        if (!email.isEmpty()) {
            Store.session(auth).put("email", email.substring(0, Math.min(120, email.length())));
        }
        return Map.of("updated", !email.isEmpty());
    }

    @Post("/web/ext/agama/close")  // @@R POST /web/ext/agama/close 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public HttpResponse<?> agamaClose(Authentication auth) {
        Store.SESSIONS.remove((String) auth.getAttributes().get("token"));  // @@T positive csrf cookie-session account closure reachable from a cross-site form post
        return HttpResponse.noContent().cookie(Cookie.of("sid", "").maxAge(0).secure(true).httpOnly(true).sameSite(SameSite.Strict));
    }

    @Get("/web/pref/lotus/theme")  // @@R GET /web/pref/lotus/theme 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> lotusTheme(Authentication auth) {
        return Map.of("theme", "light", "uid", Store.uid(auth));
    }

    @Post("/web/ext/civet/nickname")  // @@R POST /web/ext/civet/nickname 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public HttpResponse<?> civetNickname(Authentication auth, @Nullable @Header("X-Csrf-Token") String token, @Body Map<String, Object> body) {
        String expected = (String) Store.session(auth).get("csrf");
        if (token == null || token.isEmpty() || !MessageDigest.isEqual(token.getBytes(), expected.getBytes())) {  // @@T decoy csrf header token must match the token stored with the session and an empty value is rejected
            return HttpResponse.status(HttpStatus.FORBIDDEN);
        }
        return HttpResponse.ok(Map.of("updated", !String.valueOf(body.getOrDefault("nickname", "")).isEmpty()));
    }

    @Get("/web/pref/mimosa/layout")  // @@R GET /web/pref/mimosa/layout 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> mimosaLayout() {
        return Map.of("layout", "wide");
    }

    @Get("/web/ext/dingo/remember")  // @@R GET /web/ext/dingo/remember 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public HttpResponse<?> dingoRemember(Authentication auth) {
        String token = Store.openSession(Store.uid(auth), "clerk");
        return HttpResponse.noContent().cookie(Cookie.of("sid", token));  // @@T positive cookie_flags session cookie issued with no secure httpOnly or sameSite option
    }

    @Get("/web/ext/eland/trust")  // @@R GET /web/ext/eland/trust 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public HttpResponse<?> elandTrust(Authentication auth) {
        String token = Store.openSession(Store.uid(auth), "clerk");
        return HttpResponse.noContent().cookie(Cookie.of("trust", token).secure(true).sameSite(SameSite.Lax).maxAge(86400));  // @@T positive cookie_flags login token cookie readable from script because httpOnly is not set
    }

    @Get("/web/pref/nigella/locale")  // @@R GET /web/pref/nigella/locale 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public Map<String, Object> nigellaLocale() {
        return Map.of("locale", "en");
    }

    @Get("/web/ext/hyrax/keep")  // @@R GET /web/ext/hyrax/keep 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public HttpResponse<?> hyraxKeep(Authentication auth) {
        String token = Store.openSession(Store.uid(auth), "clerk");
        return HttpResponse.noContent().cookie(Cookie.of("keep", token).httpOnly(true).secure(true).sameSite(SameSite.Strict).maxAge(3600));  // @@T decoy cookie_flags httpOnly secure and sameSite Strict set together with a one hour lifetime
    }

    @Post("/web/ext/gecko/rotate")  // @@R POST /web/ext/gecko/rotate 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public HttpResponse<?> geckoRotate(Authentication auth, @Nullable @Header("X-Csrf-Token") String csrf) {
        if (csrf == null || !MessageDigest.isEqual(csrf.getBytes(), ((String) Store.session(auth).get("csrf")).getBytes())) {
            return HttpResponse.status(HttpStatus.FORBIDDEN);
        }
        String token = Store.openSession(Store.uid(auth), (String) Store.session(auth).get("role"));
        return HttpResponse.noContent().cookie(Cookie.of("sid", token).secure(true).httpOnly(true).sameSite(SameSite.Strict).maxAge(3600));  // @@T decoy cookie_flags the new session cookie is secure httpOnly and sameSite Strict with a one hour lifetime
    }

    @Get("/web/ext/fossa/device")  // @@R GET /web/ext/fossa/device 1
    @Secured(SecurityRule.IS_AUTHENTICATED)
    public HttpResponse<?> fossaDevice(Authentication auth) {
        String token = Store.openSession(Store.uid(auth), "clerk");
        return HttpResponse.noContent().cookie(Cookie.of("device", token).httpOnly(true).sameSite(SameSite.Lax).maxAge(86400));  // @@T positive cookie_flags device token cookie travels over plain http because secure is not set
    }
}
