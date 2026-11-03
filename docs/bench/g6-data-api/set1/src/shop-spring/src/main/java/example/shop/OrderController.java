package example.shop;

import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class OrderController {

    @GetMapping("/api/open/catalog-stats") // @@R GET /api/open/catalog-stats 0 ; T positive missing_authn partner prefix skipped by AuthFilter returns orders with owner ids
    public Object catalogStats() {
        List<Map<String, Object>> rows = new java.util.ArrayList<>();
        for (Store.Order order : Store.ORDERS.values()) {
            rows.add(Map.of("item", order.item(), "ownerId", order.ownerId()));
        }
        return rows;
    }

    @GetMapping("/api/orders") // @@R GET /api/orders 1
    public Object listOrders(HttpServletRequest request) {
        Session session = (Session) request.getAttribute("session");
        return Store.ORDERS.values().stream().filter(o -> o.ownerId() == session.userId()).toList();
    }

    @GetMapping("/api/orders/{id}") // @@R GET /api/orders/{id} 1 ; T decoy missing_object_check filter gate plus owner comparison
    public Object getOrder(@PathVariable long id, HttpServletRequest request) {
        Session session = (Session) request.getAttribute("session");
        Store.Order order = Store.ORDERS.get(id);
        if (order == null || order.ownerId() != session.userId()) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return order;
    }

    @GetMapping("/api/orders/{id}/memo") // @@R GET /api/orders/{id}/memo 0 ; T positive missing_object_check any logged-in user reads any order memo
    public Object orderMemo(@PathVariable long id) {
        Store.Order order = Store.ORDERS.get(id);
        if (order == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return Map.of("id", order.id(), "memo", order.memo());
    }

    @DeleteMapping("/api/orders/{id}") // @@R DELETE /api/orders/{id} 1 ; T decoy missing_object_check delete limited to the owner
    public void deleteOrder(@PathVariable long id, HttpServletRequest request) {
        Session session = (Session) request.getAttribute("session");
        Store.Order order = Store.ORDERS.get(id);
        if (order == null || order.ownerId() != session.userId()) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        Store.ORDERS.remove(id);
    }

    @PutMapping("/api/orders/{id}/item") // @@R PUT /api/orders/{id}/item 0 ; T positive missing_object_check change item without checking the order belongs to the caller
    public Object changeItem(@PathVariable long id, @RequestBody Map<String, String> body) {
        Store.Order old = Store.ORDERS.get(id);
        if (old == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        Store.Order updated = new Store.Order(old.id(), old.ownerId(), body.getOrDefault("item", old.item()), old.memo());
        Store.ORDERS.put(id, updated);
        return updated;
    }
}
