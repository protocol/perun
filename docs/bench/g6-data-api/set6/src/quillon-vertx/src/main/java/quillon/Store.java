package quillon;

import io.vertx.core.json.JsonArray;
import io.vertx.core.json.JsonObject;
import io.vertx.ext.web.RoutingContext;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.HexFormat;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public final class Store {
    public static final class Sess {
        public final int uid;
        public final String role;
        public final String csrf;
        public String email;
        public String phone;

        Sess(int uid, String role, String csrf, String email, String phone) {
            this.uid = uid;
            this.role = role;
            this.csrf = csrf;
            this.email = email;
            this.phone = phone;
        }
    }

    public static final Map<String, Sess> SESSIONS = new ConcurrentHashMap<>(Map.of(
        "tok-clerk", new Sess(40, "clerk", "c-40", "clerk@example.com", "+15550100"),
        "tok-admin", new Sess(41, "admin", "c-41", "admin@example.com", "+15550101")));
    public static final Map<Integer, JsonObject> ROWS = new ConcurrentHashMap<>(Map.of(
        1, new JsonObject().put("id", 1).put("owner", 40).put("label", "quillon one"),
        2, new JsonObject().put("id", 2).put("owner", 41).put("label", "quillon two")));
    public static final Map<Integer, String> CACHE = new ConcurrentHashMap<>(Map.of(1, "warm", 2, "warm"));
    private static final SecureRandom RNG = new SecureRandom();

    public static String randomHex(int bytes) {
        byte[] raw = new byte[bytes];
        RNG.nextBytes(raw);
        return HexFormat.of().formatHex(raw);
    }

    public static String openSession(int uid, String role) {
        String token = randomHex(24);
        SESSIONS.put(token, new Sess(uid, role, randomHex(16), "x@example.com", ""));
        return token;
    }

    public static Sess me(RoutingContext ctx) {
        return ctx.get("me");
    }

    public static JsonObject body(RoutingContext ctx) {
        JsonObject b = ctx.body().asJsonObject();
        return b == null ? new JsonObject() : b;
    }

    public static int id(RoutingContext ctx) {
        try {
            return Integer.parseInt(ctx.pathParam("id"));
        } catch (NumberFormatException e) {
            return -1;
        }
    }

    public static JsonArray labels() {
        JsonArray out = new JsonArray();
        ROWS.values().forEach(r -> out.add(new JsonObject().put("id", r.getInteger("id")).put("label", r.getString("label"))));
        return out;
    }

    public static JsonArray labels(int owner) {
        JsonArray out = new JsonArray();
        ROWS.values().stream().filter(r -> r.getInteger("owner") == owner)
            .forEach(r -> out.add(new JsonObject().put("id", r.getInteger("id")).put("label", r.getString("label"))));
        return out;
    }

    public static JsonObject ownedOrNull(RoutingContext ctx, int id) {
        JsonObject row = ROWS.get(id);
        return row != null && row.getInteger("owner") == me(ctx).uid ? row : null;
    }

    public static boolean safeEq(String a, String b) {
        return a != null && b != null && !a.isEmpty()
            && MessageDigest.isEqual(a.getBytes(StandardCharsets.UTF_8), b.getBytes(StandardCharsets.UTF_8));
    }
}
