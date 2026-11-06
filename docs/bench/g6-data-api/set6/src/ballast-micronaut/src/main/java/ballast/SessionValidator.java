package ballast;

import io.micronaut.http.HttpRequest;
import io.micronaut.security.authentication.Authentication;
import io.micronaut.security.token.validator.TokenValidator;
import jakarta.inject.Singleton;
import java.util.List;
import java.util.Map;
import org.reactivestreams.Publisher;
import reactor.core.publisher.Mono;

@Singleton
public class SessionValidator implements TokenValidator<HttpRequest<?>> {
    @Override
    public Publisher<Authentication> validateToken(String token, HttpRequest<?> request) {
        Map<String, Object> sess = Store.SESSIONS.get(token);
        if (sess == null) {
            return Mono.empty();
        }
        String role = (String) sess.get("role");
        return Mono.just(Authentication.build(String.valueOf(sess.get("uid")), List.of("ROLE_" + role.toUpperCase()), Map.of("uid", sess.get("uid"), "token", token)));
    }
}
