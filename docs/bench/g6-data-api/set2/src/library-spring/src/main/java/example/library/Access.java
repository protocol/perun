package example.library;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

public final class Access {
    private Access() {}

    public static void requireAdmin(Store.Member m) {
        if (!"admin".equals(m.role())) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "forbidden");
        }
    }

    public static void requireToken(HttpServletRequest req, String token) {
        HttpSession s = req.getSession(false);
        Object want = s == null ? null : s.getAttribute("csrf");
        if (!(want instanceof String w) || w.isEmpty() || !Util.same(token, w)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "bad token");
        }
    }
}
