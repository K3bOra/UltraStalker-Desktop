package com.k3bora.ultrastalker.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import java.net.URI
import java.security.MessageDigest

/* Ultra Stalker for TV — what the app shows: sources, categories, items, seasons. */

enum class Media(val api: String) { LIVE("itv"), MOVIES("vod"), SERIES("series") }

enum class SourceKind { PORTAL, XTREAM, M3U }

data class Source(
    val name: String,
    val portal: String,
    val mac: String,
    val kind: SourceKind,
) {
    val key: String get() = portal.trimEnd('/').lowercase() + "|" + mac.uppercase()
    val host: String get() = try {
        URI(portal).host ?: portal
    } catch (_: Exception) {
        portal
    }
    fun title(index: Int): String = name.ifBlank {
        when (kind) {
            SourceKind.PORTAL -> "Portal ${index + 1}"
            SourceKind.XTREAM -> host
            SourceKind.M3U -> host
        }
    }
    val kindLabel: String get() = when (kind) {
        SourceKind.PORTAL -> "Stalker"
        SourceKind.XTREAM -> "Xtream"
        SourceKind.M3U -> "M3U"
    }
}

data class Category(val id: String, val title: String)

data class Item(
    val id: String,
    val title: String,
    val media: Media,
    val image: String = "",
    val number: String = "",
    val year: String = "",
    val rating: String = "",
    val plot: String = "",
    val raw: JsonObject = JsonObject(emptyMap()),
)

data class Page(val items: List<Item>, val total: Int, val hasNext: Boolean)

data class Season(val id: String, val number: String, val title: String, val episodes: List<Item>, val raw: JsonObject = JsonObject(emptyMap()))

data class Details(val plot: String = "", val year: String = "", val rating: String = "", val genres: String = "", val runtime: String = "", val backdrop: String = "", val poster: String = "")

class ProviderError(message: String, val status: Int = 502) : Exception(message)

/* One kind of server (Stalker portal, Xtream line, M3U playlist). Calls block: the app
   runs them off the main thread. */
interface Provider {
    val source: Source
    fun categories(media: Media): List<Category>
    fun page(media: Media, category: String, page: Int): Page
    fun seasons(series: Item): List<Season>
    fun details(item: Item): Details = Details(plot = item.plot, year = item.year, rating = item.rating, poster = item.image)
    /* how the relay gets the stream (a /play ticket's data) */
    fun ticket(item: Item, seriesNumber: String? = null): JsonObject
}

/* ------------------------------------------------------------------ small helpers */
internal val JSON = Json { ignoreUnknownKeys = true; isLenient = true }

internal fun JsonObject.s(vararg keys: String): String {
    for (k in keys) {
        val v = this[k] ?: continue
        val t = when (v) {
            is JsonPrimitive -> v.contentOrNull ?: ""
            is JsonNull -> ""
            else -> ""
        }.trim()
        if (t.isNotEmpty() && t != "null") return t
    }
    return ""
}

internal fun JsonElement?.obj(): JsonObject? = this as? JsonObject
internal fun JsonElement?.arr(): JsonArray? = this as? JsonArray

internal fun prim(v: Any?): JsonElement = when (v) {
    null -> JsonNull
    is JsonElement -> v
    is Number -> JsonPrimitive(v)
    is Boolean -> JsonPrimitive(v)
    else -> JsonPrimitive(v.toString())
}

internal fun jsonOf(vararg pairs: Pair<String, Any?>): JsonObject = JsonObject(pairs.filter { it.second != null }.associate { it.first to prim(it.second) })

internal fun JsonObject.plus(vararg pairs: Pair<String, Any?>): JsonObject = JsonObject(this + pairs.filter { it.second != null }.associate { it.first to prim(it.second) })

/* Some servers wrap JSON in junk (a BOM, a PHP notice): read what is between the braces. */
internal fun parseLoose(text: String): JsonElement? {
    val t = text.trim().removePrefix("﻿")
    if (t.isEmpty()) return null
    try {
        return JSON.parseToJsonElement(t)
    } catch (_: Exception) {
    }
    val a = t.indexOfFirst { it == '{' || it == '[' }
    val b = t.indexOfLast { it == '}' || it == ']' }
    if (a >= 0 && b > a) {
        try {
            return JSON.parseToJsonElement(t.substring(a, b + 1))
        } catch (_: Exception) {
        }
    }
    return null
}

internal fun hash(alg: String, s: String): String = MessageDigest.getInstance(alg).digest(s.toByteArray()).joinToString("") { "%02x".format(it) }

internal fun resolveUrl(base: String, ref: String): String {
    val r = ref.trim()
    if (r.isEmpty()) return ""
    if (Regex("^https?://", RegexOption.IGNORE_CASE).containsMatchIn(r)) return r
    if (r.startsWith("//")) return "http:$r"
    return try {
        URI(base).resolve(r.replace(" ", "%20")).toString()
    } catch (_: Exception) {
        r
    }
}

fun providerFor(source: Source, http: okhttp3.OkHttpClient): Provider = when (source.kind) {
    SourceKind.PORTAL -> Stalker(source, http)
    SourceKind.XTREAM -> Xtream(source, http)
    SourceKind.M3U -> M3u(source, http)
}
