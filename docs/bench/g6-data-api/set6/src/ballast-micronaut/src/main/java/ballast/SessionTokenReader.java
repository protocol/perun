package ballast;

import io.micronaut.http.HttpRequest;
import io.micronaut.http.cookie.Cookie;
import io.micronaut.security.token.reader.TokenReader;
import jakarta.inject.Singleton;
import java.util.Optional;

@Singleton
public class SessionTokenReader implements TokenReader<HttpRequest<?>> {
    @Override
    public Optional<String> findToken(HttpRequest<?> request) {
        if (request.getPath().startsWith("/web/")) {
            return request.getCookies().findCookie("sid").map(Cookie::getValue);
        }
        return request.getHeaders().getAuthorization().filter(h -> h.startsWith("Bearer ")).map(h -> h.substring(7));
    }

    @Override
    public int getOrder() {
        return 0;
    }
}
