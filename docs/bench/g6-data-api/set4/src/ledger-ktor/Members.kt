package ledger

import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import io.ktor.server.application.*
import io.ktor.server.request.*
import io.ktor.server.response.*
import io.ktor.server.routing.*

val SEED_SPIRE = listOf(mapOf("label" to "Sample ledger", "region" to "north", "count" to 3)) // @@T decoy pii_data seed rows hold labels and counts and no person

fun Route.membersRoutes() {
    get("/api/ext/spire/sample") { call.respond(mapOf("count" to SEED_SPIRE.size)) } // @@R GET /api/ext/spire/sample 1

    post("/api/ext/dune/rotate-key") { // @@R POST /api/ext/dune/rotate-key 1
        val keyId = java.util.UUID.randomUUID().toString().replace("-", "").take(16)
        call.application.log.info("rotate user=${call.user.uid}") // @@T decoy pii_log the log line carries only the numeric user id
        call.respond(mapOf("keyId" to keyId))
    }

    post("/api/ext/shoal/track") { // @@R POST /api/ext/shoal/track 1
        http.post("https://stats.vendor.example.com/v1/event") { setBody("""{"event":"view"}""") } // @@T decoy pii_data analytics payload is a constant event name with no user identifier
        call.respond(HttpStatusCode.NoContent)
    }
}
