package ledger

import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import io.ktor.server.application.*
import io.ktor.server.request.*
import io.ktor.server.response.*
import io.ktor.server.routing.*

fun Route.webRoutes() {
    post("/web/ext/ridge/email") { // @@R POST /web/ext/ridge/email 1
        val email = call.receive<Map<String, String>>()["email"].orEmpty().take(120) // @@T positive csrf cookie-session email change accepted with no anti-forgery token
        Store.sessions.replaceAll { _, s -> if (s.uid == call.user.uid) s.copy(email = email) else s }
        call.respond(mapOf("updated" to email.isNotEmpty()))
    }

    post("/web/ext/delta/close") { // @@R POST /web/ext/delta/close 1
        Store.sessions.values.removeAll { it.uid == call.user.uid }
        call.response.cookies.appendExpired("sid") // @@T positive csrf cookie-session account closure reachable from a cross-site form post
        call.respond(HttpStatusCode.NoContent)
    }

    post("/web/ext/cairn/password") { // @@R POST /web/ext/cairn/password 1
        val next = call.receive<Map<String, String>>()["password"].orEmpty() // @@T positive csrf cookie-session password change accepted with no anti-forgery token
        if (next.length >= 12) Store.passwords[call.user.uid] = next
        call.respond(mapOf("updated" to (next.length >= 12)))
    }

    get("/web/ext/prairie/remember") { // @@R GET /web/ext/prairie/remember 1
        call.response.cookies.append("sid", Store.open(call.user.uid, call.user.role)) // @@T positive cookie_flags session cookie issued with no secure httponly or samesite option
        call.respond(HttpStatusCode.NoContent)
    }

    get("/web/ext/savanna/trust") { // @@R GET /web/ext/savanna/trust 1
        call.response.cookies.append("trust", Store.open(call.user.uid, call.user.role), secure = true, maxAge = 86400, extensions = mapOf("SameSite" to "Lax")) // @@T positive cookie_flags login token cookie readable from script because httpOnly is not set
        call.respond(HttpStatusCode.NoContent)
    }

    get("/web/ext/fjord/remember") { // @@R GET /web/ext/fjord/remember 1
        call.response.cookies.append("sid", Store.open(call.user.uid, call.user.role)) // @@T positive cookie_flags session cookie issued with no secure httponly or samesite option
        call.respond(HttpStatusCode.NoContent)
    }
}
