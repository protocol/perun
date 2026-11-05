package ledger

import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import io.ktor.server.application.*
import io.ktor.server.request.*
import io.ktor.server.response.*
import io.ktor.server.routing.*

fun Route.deskRoutes() {
    post("/api/ext/quill/summarise") { // @@R POST /api/ext/quill/summarise 1
        val note = call.receive<Map<String, String>>()["note"].orEmpty().take(500)
        val reply = askModel(listOf(mapOf("role" to "system", "content" to "You summarise ledger notes and have no tools."), mapOf("role" to "user", "content" to note))) // @@T positive rate_limit model call route has no limiter so one client can run unbounded paid requests
        call.respond(mapOf("reply" to reply))
    }

    get("/api/ext/slate/export") { // @@R GET /api/ext/slate/export 1
        call.respond(List(100_000) { mapOf("i" to it, "label" to "slate-$it") }) // @@T positive rate_limit full export rebuilt on every call with no throttle
    }
}
