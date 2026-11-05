package ledger

import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import io.ktor.server.application.*
import io.ktor.server.request.*
import io.ktor.server.response.*
import io.ktor.server.routing.*

fun Route.consoleRoutes() {
    post("/web/ext/lagoon/phone") { // @@R POST /web/ext/lagoon/phone 1
        val sent = call.request.headers["X-Csrf-Token"].orEmpty().toByteArray()
        if (!java.security.MessageDigest.isEqual(sent, call.user.csrf.toByteArray())) return@post call.respond(HttpStatusCode.Forbidden) // @@T decoy csrf per-session token compared in constant time and a missing header is rejected
        call.respond(mapOf("updated" to (call.receive<Map<String, String>>()["phone"].orEmpty().length <= 20)))
    }

    post("/web/ext/mesa/nickname") { // @@R POST /web/ext/mesa/nickname 1
        val sent = call.request.cookies["csrf"].orEmpty().toByteArray()
        val header = call.request.headers["X-Csrf-Token"].orEmpty().toByteArray()
        if (sent.isEmpty() || !java.security.MessageDigest.isEqual(sent, header)) return@post call.respond(HttpStatusCode.Forbidden) // @@T decoy csrf double-submit token must match the csrf cookie and an empty value is rejected
        call.respond(mapOf("updated" to call.receive<Map<String, String>>()["nickname"].orEmpty().take(40).isNotEmpty()))
    }

    get("/web/ext/atoll/rotate") { // @@R GET /web/ext/atoll/rotate 1
        call.response.cookies.append("sid", Store.open(call.user.uid, call.user.role), secure = true, httpOnly = true, maxAge = 3600, extensions = mapOf("SameSite" to "Strict")) // @@T decoy cookie_flags the new session cookie is secure httpOnly and sameSite strict with a one hour lifetime
        call.respond(HttpStatusCode.NoContent)
    }

    get("/web/ext/geyser/keep") { // @@R GET /web/ext/geyser/keep 1
        call.response.cookies.append("keep", java.util.UUID.randomUUID().toString(), secure = true, httpOnly = true, maxAge = 3600, extensions = mapOf("SameSite" to "Strict")) // @@T decoy cookie_flags httpOnly secure and sameSite strict set together with a one hour lifetime
        call.respond(HttpStatusCode.NoContent)
    }
}
