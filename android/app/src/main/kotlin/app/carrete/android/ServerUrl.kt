package app.carrete.android

import java.net.URI

/** Dirección del servidor: siempre https, sin ruta. */
object ServerUrl {
    /** Normaliza lo que escribe la persona o trae un QR («carrete:https://…»). Null si no vale. */
    fun normalize(input: String): String? {
        var text = input.trim().removePrefix("carrete:")
        if (text.isEmpty()) return null
        if (!text.contains("://")) text = "https://$text"
        val uri = try {
            URI(text)
        } catch (e: Exception) {
            return null
        }
        if (uri.scheme?.lowercase() != "https" || uri.host.isNullOrBlank()) return null
        val port = if (uri.port == -1 || uri.port == 443) "" else ":${uri.port}"
        return "https://${uri.host.lowercase()}$port"
    }

    /** ¿Pertenece esta URL al servidor? (mismo esquema, equipo y puerto). */
    fun sameOrigin(server: String, url: String): Boolean {
        val a = try { URI(server) } catch (e: Exception) { return false }
        val b = try { URI(url) } catch (e: Exception) { return false }
        fun port(u: URI) = if (u.port == -1) (if (u.scheme == "https") 443 else 80) else u.port
        return a.scheme.equals(b.scheme, true) && a.host.equals(b.host, true) && port(a) == port(b)
    }
}
