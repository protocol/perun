package app.trellis;

import java.security.SecureRandom;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public final class Store {
    private static final Map<String, Session> SESSIONS = new ConcurrentHashMap<>(Map.of(
        "tok-clerk", new Session(40, "clerk", "c-40", "clerk@example.com", "+15550100"),
        "tok-admin", new Session(41, "admin", "c-41", "admin@example.com", "+15550101")));
    private static final Map<String, Row> ROWS = Map.of("1", new Row(1, 40, "trellis one"), "2", new Row(2, 41, "trellis two"));
    private static final Map<String, String> CACHE = new ConcurrentHashMap<>(Map.of("1", "warm", "2", "warm"));
    private static final SecureRandom RNG = new SecureRandom();

    private Store() {
    }

    public static Session session(String tok) {
        return SESSIONS.get(tok);
    }

    public static String openSession(int uid, String role) {
        byte[] raw = new byte[24];
        RNG.nextBytes(raw);
        String tok = HexFormat.of().formatHex(raw);
        SESSIONS.put(tok, new Session(uid, role, Long.toHexString(RNG.nextLong()), "x@example.com", ""));
        return tok;
    }

    public static void dropSession(String tok) {
        SESSIONS.remove(tok);
    }

    public static void setEmail(String tok, String email) {
        Session s = SESSIONS.get(tok);
        if (s != null) {
            SESSIONS.put(tok, new Session(s.uid(), s.role(), s.csrf(), email, s.phone()));
        }
    }

    public static List<Row> rows() {
        return List.copyOf(ROWS.values());
    }

    public static Row row(String id) {
        return ROWS.get(id);
    }

    public static boolean purge(String id) {
        return CACHE.remove(id) != null;
    }
}
