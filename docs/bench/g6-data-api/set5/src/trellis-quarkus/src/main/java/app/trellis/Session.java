package app.trellis;

public record Session(int uid, String role, String csrf, String email, String phone) {
}
