package ledger

import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import io.ktor.server.application.*
import io.ktor.server.request.*
import io.ktor.server.response.*
import io.ktor.server.routing.*

fun Route.gatewayRoutes() {
    route("/auth/birch-login") {
        install(Throttle) { cap = 8; spanMs = 600_000 }
        post { // @@R POST /auth/birch-login 0 public ; T decoy rate_limit the route installs a per-client-address throttle that answers 429 past eight attempts in ten minutes
            val body = call.receive<Map<String, String>>()
            if (PIN.isEmpty() || body["pin"] != PIN) return@post call.respond(HttpStatusCode.Unauthorized)
            call.respond(mapOf("token" to Store.open(40, "clerk")))
        }
    }

    post("/auth/hazel-join") { // @@R POST /auth/hazel-join 0 public
        val newId = java.security.SecureRandom().nextInt(1_000_000)
        call.application.log.info("join user=$newId") // @@T decoy pii_log only the generated numeric id is logged
        call.respond(HttpStatusCode.Created)
    }
}
