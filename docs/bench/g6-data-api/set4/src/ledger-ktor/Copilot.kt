package ledger

import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import io.ktor.server.application.*
import io.ktor.server.request.*
import io.ktor.server.response.*
import io.ktor.server.routing.*

fun Route.copilotRoutes() {
    post("/api/ext/fennel/assist") { // @@R POST /api/ext/fennel/assist 1
        val note = call.receive<Map<String, String>>()["note"].orEmpty().take(500)
        call.respond(mapOf("reply" to askModel(listOf(mapOf("role" to "system", "content" to "You summarise ledger notes and have no tools."), mapOf("role" to "user", "content" to note))))) // @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
    }

    post("/api/ext/hazel/lookup-tool") { // @@R POST /api/ext/hazel/lookup-tool 1
        val sku = call.receive<Map<String, String>>()["sku"].orEmpty()
        call.respond(mapOf("reply" to askTool(kotlinx.serialization.json.buildJsonObject { put("tool", kotlinx.serialization.json.JsonPrimitive("lookup")); put("arg", kotlinx.serialization.json.JsonPrimitive(sku)) }.toString()))) // @@T decoy prompt_injection tool name fixed and the value is JSON-encoded as data
    }

    post("/api/ext/ivy/translate") { // @@R POST /api/ext/ivy/translate 1
        val text = call.receive<Map<String, String>>()["text"].orEmpty().take(500)
        call.respond(mapOf("reply" to askModel(listOf(mapOf("role" to "system", "content" to "You translate ledger notes and have no tools."), mapOf("role" to "user", "content" to text))))) // @@T decoy rate_limit model call route sits inside the route block that installs the Throttle plugin so each client address is capped at sixty requests a minute
    }
}
