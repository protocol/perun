package example.shop;

import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

// Staff routes live outside /api; the RoleInterceptor enforces @RequireRole here.
@RestController
public class StaffController {

    @GetMapping("/staff/audit") // @@R GET /staff/audit 0 ; T positive missing_authn staff audit trail with no annotation and outside the filter
    public Object audit() {
        return Store.ORDERS.values().stream().map(o -> Map.of("id", o.id(), "ownerId", o.ownerId())).toList();
    }

    @PostMapping("/staff/coupons/{id}/retire") // @@R POST /staff/coupons/{id}/retire 0 ; T positive missing_authz login required but any buyer can retire a coupon
    @RequireRole("buyer")
    public Object retireCoupon(@PathVariable long id) {
        String code = Store.COUPONS.remove(id);
        if (code == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return Map.of("retired", code);
    }

    @GetMapping("/staff/overview") // @@R GET /staff/overview 1 ; T decoy missing_authz admin role enforced by annotation
    @RequireRole("admin")
    public Object overview() {
        return Map.of("orders", Store.ORDERS.size(), "coupons", Store.COUPONS.size());
    }

    @PostMapping("/staff/reindex") // @@R POST /staff/reindex 1 ; T decoy missing_authz admin role enforced by annotation
    @RequireRole("admin")
    public Object reindex() {
        return Map.of("queued", Store.ORDERS.size() + Store.COUPONS.size());
    }

    @GetMapping("/staff/me/orders") // @@R GET /staff/me/orders 1 ; T decoy missing_authn @RequireRole login check, results limited to the caller
    @RequireRole("buyer")
    public Object myOrders(HttpServletRequest request) {
        Session session = (Session) request.getAttribute("session");
        return Store.ORDERS.values().stream().filter(o -> o.ownerId() == session.userId()).toList();
    }
}
