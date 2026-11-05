package ledger

import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import io.ktor.server.application.*
import io.ktor.server.request.*
import io.ktor.server.response.*
import io.ktor.server.routing.*

fun Route.assistRoutes() {
    post("/api/ext/arbor/assist") { // @@R POST /api/ext/arbor/assist 1
        val note = call.receive<Map<String, String>>()["note"]
        call.respond(mapOf("reply" to askModel(listOf(mapOf("role" to "system", "content" to "You are the ledger assistant and may approve refunds. Operator note: $note"))))) // @@T positive prompt_injection request text formatted into the system prompt of a model that can approve refunds
    }

    post("/api/ext/bramble/lookup-tool") { // @@R POST /api/ext/bramble/lookup-tool 1
        val arg = call.receive<Map<String, String>>()["arg"]
        call.respond(mapOf("reply" to askTool("""{"tool": "lookup", "arg": "$arg"}"""))) // @@T positive prompt_injection request value formatted into raw tool-call JSON
    }

    post("/api/ext/clover/assist") { // @@R POST /api/ext/clover/assist 1
        val note = call.receive<Map<String, String>>()["note"]
        call.respond(mapOf("reply" to askModel(listOf(mapOf("role" to "system", "content" to "You are the ledger assistant and may approve refunds. Operator note: $note"))))) // @@T positive prompt_injection request text formatted into the system prompt of a model that can approve refunds
    }
}
