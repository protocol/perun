package ballast;

import io.micronaut.security.authentication.Authentication;
import java.security.SecureRandom;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public final class Store {
    public static final Map<String, Map<String, Object>> SESSIONS = new ConcurrentHashMap<>();
    public static final Map<Integer, Map<String, Object>> ROWS = new ConcurrentHashMap<>();
    public static final Map<Integer, String> CACHE = new ConcurrentHashMap<>();
    private static final SecureRandom RNG = new SecureRandom();

    static {
        SESSIONS.put("tok-clerk", new ConcurrentHashMap<>(Map.of("uid", 40, "role", "clerk", "csrf", "c-40", "email", "clerk@example.com", "phone", "+15550100")));
        SESSIONS.put("tok-admin", new ConcurrentHashMap<>(Map.of("uid", 41, "role", "admin", "csrf", "c-41", "email", "admin@example.com", "phone", "+15550101")));
        ROWS.put(1, new ConcurrentHashMap<>(Map.of("id", 1, "owner", 40, "label", "ballast one")));
        ROWS.put(2, new ConcurrentHashMap<>(Map.of("id", 2, "owner", 41, "label", "ballast two")));
        CACHE.put(1, "warm");
        CACHE.put(2, "warm");
    }

    private Store() {}

    public static String openSession(int uid, String role) {
        byte[] raw = new byte[24];
        RNG.nextBytes(raw);
        String token = HexFormat.of().formatHex(raw);
        SESSIONS.put(token, new ConcurrentHashMap<>(Map.of("uid", uid, "role", role, "csrf", Long.toHexString(RNG.nextLong()), "email", "x@example.com", "phone", "")));
        return token;
    }

    public static int uid(Authentication auth) {
        return (Integer) auth.getAttributes().get("uid");
    }

    public static Map<String, Object> session(Authentication auth) {
        return SESSIONS.get((String) auth.getAttributes().get("token"));
    }

    public static List<Map<String, Object>> labels() {
        return ROWS.values().stream().map(r -> Map.<String, Object>of("id", r.get("id"), "label", r.get("label"))).toList();
    }

    public static List<Map<String, Object>> ownedBy(int uid) {
        return ROWS.values().stream().filter(r -> r.get("owner").equals(uid)).toList();
    }

    public static Map<String, Object> ownedOrNull(Authentication auth, int id) {
        Map<String, Object> row = ROWS.get(id);
        return row != null && row.get("owner").equals(uid(auth)) ? row : null;
    }
}
