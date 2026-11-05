package ledger

import io.ktor.serialization.jackson.*
import io.ktor.server.application.*
import io.ktor.server.plugins.contentnegotiation.*
import io.ktor.server.engine.*
import io.ktor.server.netty.*
import io.ktor.server.response.*
import io.ktor.server.routing.*

fun main() {
    embeddedServer(Netty, port = 3000, host = "127.0.0.1") { module() }.start(wait = true)
}

fun Application.module() {
    install(ContentNegotiation) { jackson() }
    routing {
        publicRoutes()
        gatewayRoutes()

        route("") {
            install(BearerAuth)
            deskRoutes()
        }

        route("") {
            install(BearerAuth)
            install(Throttle) { cap = 60; spanMs = 60_000 }
            get("/api/me") { call.respond(mapOf("uid" to call.user.uid, "role" to call.user.role)) } // @@R GET /api/me 1
            recordsRoutes()
            catalogRoutes()
            partnersRoutes()
            integrationsRoutes()
            peopleRoutes()
            membersRoutes()
            assistRoutes()
            copilotRoutes()
        }

        route("") {
            install(CookieAuth)
            install(Throttle) { cap = 60; spanMs = 60_000 }
            webRoutes()
            consoleRoutes()
        }
    }
}
