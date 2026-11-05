package ledger

import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import io.ktor.server.application.*
import io.ktor.server.request.*
import io.ktor.server.response.*
import io.ktor.server.routing.*

val SEED_MOOR = listOf(mapOf("name" to "Jane Smith", "email" to "jane@example.com", "ssn" to "912-55-0147", "dob" to "1984-03-09")) // @@T positive pii_data seed staff list holds a plaintext national id and birth date

fun Route.peopleRoutes() {
    get("/api/ext/moor/sample") { call.respond(mapOf("count" to SEED_MOOR.size)) } // @@R GET /api/ext/moor/sample 1

    post("/api/ext/bluff/charge") { // @@R POST /api/ext/bluff/charge 1
        val body = call.receive<Map<String, String>>()
        call.application.log.info("charge card=${body["card"]} holder=${body["holder"]}") // @@T positive pii_log full card number and holder name logged
        call.respond(mapOf("ok" to true))
    }

    post("/api/ext/reef/track") { // @@R POST /api/ext/reef/track 1
        http.post("https://stats.vendor.example.com/v1/event") { setBody("""{"event":"view","email":"${call.user.email}","phone":"${call.user.phone}"}""") } // @@T positive pii_data raw email and phone sent to a third-party analytics host
        call.respond(HttpStatusCode.NoContent)
    }

    post("/api/ext/fen/enrich") { // @@R POST /api/ext/fen/enrich 1
        val body = call.receive<Map<String, String>>()
        http.post("https://crm.vendor.example.com/v1/people") { setBody("""{"name":"${body["name"]}","dob":"${body["dob"]}"}""") } // @@T positive pii_data full name and birth date sent to a third-party CRM host
        call.respond(HttpStatusCode.Accepted)
    }
}
