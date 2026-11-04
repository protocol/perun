package example.library;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.servlet.HandlerInterceptor;

public class BearerInterceptor implements HandlerInterceptor {
    @Override
    public boolean preHandle(HttpServletRequest req, HttpServletResponse res, Object handler) throws Exception {
        Store.Member m = Store.fromHeader(req.getHeader("Authorization"));
        if (m == null) {
            res.sendError(401, "sign in first");
            return false;
        }
        req.setAttribute("member", m);
        return true;
    }
}
