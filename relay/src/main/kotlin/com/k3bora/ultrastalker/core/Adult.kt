package com.k3bora.ultrastalker.core

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import java.text.Normalizer

/* No adult content anywhere (same words as the Windows program). */
object Adult {
    private val WORDS = listOf(
        Regex("(^|[^\\p{L}\\p{N}])(adults?|adulte?s?|adultos?|adulti|xxx+|porn\\w*|p0rn\\w*|sex|sexy|sexo|erotic\\w*|erotik\\w*|erotique|érotique|nsfw|hentai|milfs?|playboy|penthouse|hustler|brazzers|dorcel|redlight|red light|x-?rated|onlyfans|only fans|nude|nudes|xvideos?|xhamster|pornhub|bangbros|naughty|camgirls?|blue movies?|erwachsene|yeti[sş]kin|v[iı]vid ?(tv|red)|private (tv|spice|gold)|spice ?tv|venus ?tv|dusk ?tv|babes ?tv|hot ?club|night ?club tv)(?=$|[^\\p{L}\\p{N}])", setOf(RegexOption.IGNORE_CASE)),
        Regex("(^|[^\\d])18\\s*\\+|\\+\\s*18(?!\\d)|\\[\\s*18\\s*]|\\(\\s*18\\s*\\)|(^|[^\\p{L}\\p{N}])18\\s*plus(?=$|[^\\p{L}\\p{N}])", RegexOption.IGNORE_CASE),
        Regex("سكس|[إا]باحي|للكبار|للبالغين|كبار فقط|بزرگسال|سکس|для взрослых|эрот|порн|секс", RegexOption.IGNORE_CASE),
    )
    private val KEYS = listOf("name", "title", "o_name", "genre", "category", "category_name", "genre_name", "group", "group_title", "tv_genre_title", "genres_str")

    fun text(v: String?): Boolean {
        val t = Normalizer.normalize(v ?: "", Normalizer.Form.NFKC)
        if (t.isBlank()) return false
        return WORDS.any { it.containsMatchIn(t) }
    }

    fun row(r: JsonObject): Boolean {
        val c = (r["censored"] as? JsonPrimitive)?.content?.trim()
        if (c == "1" || c == "true") return true
        return KEYS.any { k -> (r[k] as? JsonPrimitive)?.takeIf { it.isString }?.content?.let(::text) == true }
    }
}
