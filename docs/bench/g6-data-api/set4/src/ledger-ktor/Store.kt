package ledger

import java.security.SecureRandom

data class Session(val uid: Int, val role: String, val csrf: String, val email: String, val phone: String)
data class Row(val id: Int, val owner: Int, var label: String, var approved: Boolean = false)

object Store {
    val sessions = mutableMapOf(
        "tok-clerk" to Session(40, "clerk", "c-40", "clerk@example.com", "+15550100"),
        "tok-admin" to Session(41, "admin", "c-41", "admin@example.com", "+15550101"),
    )
    val rows = mutableMapOf(1 to Row(1, 40, "ledger one"), 2 to Row(2, 41, "ledger two"))
    val passwords = mutableMapOf<Int, String>()
    val cache = mutableMapOf(1 to "warm", 2 to "warm")

    fun open(uid: Int, role: String): String {
        val raw = ByteArray(24).also { SecureRandom().nextBytes(it) }
        val token = raw.joinToString("") { "%02x".format(it) }
        sessions[token] = Session(uid, role, "x-$uid", "x@example.com", "")
        return token
    }
}
