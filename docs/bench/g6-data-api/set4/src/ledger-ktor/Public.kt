package ledger

import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import io.ktor.server.application.*
import io.ktor.server.request.*
import io.ktor.server.response.*
import io.ktor.server.routing.*

fun Route.publicRoutes() {
    get("/healthz") { call.respond(mapOf("ok" to true)) } // @@R GET /healthz 0 public

    get("/api/aspen/summary") { // @@R GET /api/aspen/summary 0 ; T positive missing_authn route is registered outside any authenticated route block and lists internal rows to anyone
        call.respond(Store.rows.values.map { mapOf("id" to it.id, "label" to it.label) })
    }

    get("/api/larch/summary") { // @@R GET /api/larch/summary 0 ; T positive missing_authn route is registered outside any authenticated route block and lists internal rows to anyone
        call.respond(Store.rows.values.map { mapOf("id" to it.id, "label" to it.label) })
    }

    post("/auth/cedar-pin") { // @@R POST /auth/cedar-pin 0 public
        val body = call.receive<Map<String, String>>()
        if (PIN.isEmpty() || body["pin"] != PIN) return@post call.respond(HttpStatusCode.Unauthorized) // @@T positive rate_limit pin can be retried indefinitely because no attempt counter exists
        call.respond(mapOf("token" to Store.open(40, "clerk")))
    }

    post("/auth/elm-signup") { // @@R POST /auth/elm-signup 0 public
        val body = call.receive<Map<String, String>>()
        call.application.log.info("signup name=${body["name"]} email=${body["email"]} ssn=${body["ssn"]}") // @@T positive pii_log name email and national id written to the log
        call.respond(HttpStatusCode.Created)
    }

    post("/auth/fir-signup") { // @@R POST /auth/fir-signup 0 public
        val body = call.receive<Map<String, String>>()
        call.application.log.info("signup phone=${body["phone"]} dob=${body["dob"]}") // @@T positive pii_log phone number and birth date written to the log
        call.respond(HttpStatusCode.Created)
    }
}
