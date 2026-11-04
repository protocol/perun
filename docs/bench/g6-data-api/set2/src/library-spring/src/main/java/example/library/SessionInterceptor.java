package example.library;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import org.springframework.web.servlet.HandlerInterceptor;

public class SessionInterceptor implements HandlerInterceptor {
    @Override
    public boolean preHandle(HttpServletRequest req, HttpServletResponse res, Object handler) throws Exception {
        HttpSession s = req.getSession(false);
        Object uid = s == null ? null : s.getAttribute("uid");
        if (!(uid instanceof Integer id) || !Store.MEMBERS.containsKey(id)) {
            res.sendError(401, "sign in first");
            return false;
        }
        req.setAttribute("member", Store.MEMBERS.get(id));
        return true;
    }
}
