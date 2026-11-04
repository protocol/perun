package example.library;

import java.security.SecureRandom;
import java.util.HexFormat;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

public final class Store {
    public record Member(int id, String name, String role) {}

    public static final class Book {
        public final int id;
        public final String title;
        public volatile boolean retired;
        public volatile boolean withdrawn;

        Book(int id, String title) {
            this.id = id;
            this.title = title;
        }
    }

    public static final class Loan {
        public final int id;
        public final int memberId;
        public final int bookId;
        public volatile String note = "";
        public volatile boolean returned;

        Loan(int id, int memberId, int bookId) {
            this.id = id;
            this.memberId = memberId;
            this.bookId = bookId;
        }
    }

    public static final Map<Integer, Member> MEMBERS = Map.of(
        40, new Member(40, "Jane Smith", "member"),
        41, new Member(41, "Omar Reyes", "admin"));
    public static final Map<Integer, Book> BOOKS = new ConcurrentHashMap<>(Map.of(
        1, new Book(1, "Tides and Harbours"), 2, new Book(2, "Market Gardens")));
    public static final Map<Integer, Loan> LOANS = new ConcurrentHashMap<>(Map.of(
        1, new Loan(1, 40, 1), 2, new Loan(2, 41, 2)));
    private static final Map<String, Integer> TOKENS = new ConcurrentHashMap<>();
    private static final SecureRandom RNG = new SecureRandom();

    private Store() {}

    public static String randomHex(int bytes) {
        byte[] b = new byte[bytes];
        RNG.nextBytes(b);
        return HexFormat.of().formatHex(b);
    }

    public static String openToken(int memberId) {
        String token = randomHex(24);
        TOKENS.put(token, memberId);
        return token;
    }

    public static Member fromHeader(String header) {
        if (header == null || !header.startsWith("Bearer ")) {
            return null;
        }
        Integer id = TOKENS.get(header.substring(7));
        return id == null ? null : MEMBERS.get(id);
    }

    public static Loan loan(int id) {
        Loan l = LOANS.get(id);
        if (l == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return l;
    }

    public static Book book(int id) {
        Book b = BOOKS.get(id);
        if (b == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return b;
    }
}
