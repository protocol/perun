package ledger

import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import io.ktor.server.application.*
import io.ktor.server.request.*
import io.ktor.server.response.*
import io.ktor.server.routing.*

fun Route.recordsRoutes() {
    post("/api/beacon/{id}/purge") { // @@R POST /api/beacon/{id}/purge 0 ; T positive missing_authz purge is an admin action but the route block only requires a session
        val id = call.parameters["id"]?.toIntOrNull()
        if (Store.cache.remove(id) == null) return@post call.respond(HttpStatusCode.NotFound)
        call.respond(HttpStatusCode.NoContent)
    }

    post("/api/cobalt/{id}/purge") { // @@R POST /api/cobalt/{id}/purge 0 ; T positive missing_authz purge is an admin action but the route block only requires a session
        val id = call.parameters["id"]?.toIntOrNull()
        if (Store.cache.remove(id) == null) return@post call.respond(HttpStatusCode.NotFound)
        call.respond(HttpStatusCode.NoContent)
    }

    get("/api/granite/{id}") { // @@R GET /api/granite/{id} 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
        val row = Store.rows[call.parameters["id"]?.toIntOrNull()] ?: return@get call.respond(HttpStatusCode.NotFound)
        call.respond(row)
    }

    get("/api/pebble/{id}") { // @@R GET /api/pebble/{id} 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
        val row = Store.rows[call.parameters["id"]?.toIntOrNull()] ?: return@get call.respond(HttpStatusCode.NotFound)
        call.respond(row)
    }
}
