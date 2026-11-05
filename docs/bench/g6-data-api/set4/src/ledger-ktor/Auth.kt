package ledger

import io.ktor.http.*
import io.ktor.server.application.*
import io.ktor.server.response.*
import io.ktor.util.*

val UserKey = AttributeKey<Session>("user")
val ApplicationCall.user: Session get() = attributes[UserKey]

val BearerAuth = createRouteScopedPlugin("BearerAuth") {
    onCall { call ->
        val s = Store.sessions[call.request.headers["Authorization"]?.removePrefix("Bearer ") ?: ""]
        if (s == null) call.respond(HttpStatusCode.Unauthorized) else call.attributes.put(UserKey, s)
    }
}

val CookieAuth = createRouteScopedPlugin("CookieAuth") {
    onCall { call ->
        val s = Store.sessions[call.request.cookies["sid"] ?: ""]
        if (s == null) call.respond(HttpStatusCode.Unauthorized) else call.attributes.put(UserKey, s)
    }
}

suspend fun ApplicationCall.requireAdmin(): Boolean {
    if (user.role == "admin") return true
    respond(HttpStatusCode.Forbidden)
    return false
}

suspend fun ApplicationCall.ownedOr404(id: String?): Row? {
    val row = Store.rows[id?.toIntOrNull()]
    if (row == null || row.owner != user.uid) {
        respond(HttpStatusCode.NotFound)
        return null
    }
    return row
}
