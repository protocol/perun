package example.shop;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.method.HandlerMethod;
import org.springframework.web.servlet.HandlerInterceptor;

// Enforces @RequireRole on /staff/** handlers. A handler without the annotation is not checked.
public class RoleInterceptor implements HandlerInterceptor {
    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) throws Exception {
        if (!(handler instanceof HandlerMethod method)) {
            return true;
        }
        RequireRole required = method.getMethodAnnotation(RequireRole.class);
        if (required == null) {
            return true;
        }
        String header = request.getHeader("Authorization");
        String token = header != null && header.startsWith("Bearer ") ? header.substring(7) : "";
        Session session = Store.TOKENS.get(token);
        if (session == null) {
            response.sendError(401);
            return false;
        }
        if (required.value().equals("admin") && !session.role().equals("admin")) {
            response.sendError(403);
            return false;
        }
        request.setAttribute("session", session);
        return true;
    }
}
