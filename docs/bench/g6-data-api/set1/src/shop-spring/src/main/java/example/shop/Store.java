package example.shop;

import java.util.HashMap;
import java.util.Map;

public final class Store {
    public record Order(long id, long ownerId, String item, String memo) {}

    public static final Map<String, Session> TOKENS = Map.of(
        "tok-buyer", new Session(30, "buyer"),
        "tok-admin", new Session(31, "admin"));

    public static final Map<Long, Order> ORDERS = new HashMap<>(Map.of(
        1L, new Order(1, 30, "desk lamp", "gift wrap"),
        2L, new Order(2, 31, "monitor arm", "none")));

    public static final Map<Long, String> COUPONS = new HashMap<>(Map.of(1L, "SPRING10"));

    private Store() {}
}
