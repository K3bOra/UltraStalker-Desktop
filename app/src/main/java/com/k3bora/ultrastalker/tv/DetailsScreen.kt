package com.k3bora.ultrastalker.tv

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.tv.material3.Icon
import androidx.tv.material3.MaterialTheme
import androidx.tv.material3.Text
import com.k3bora.ultrastalker.core.Details
import com.k3bora.ultrastalker.core.Media
import com.k3bora.ultrastalker.core.Season
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

fun clock(ms: Long): String {
    val s = (ms / 1000).coerceAtLeast(0)
    val h = s / 3600
    val m = (s % 3600) / 60
    val sec = s % 60
    return if (h > 0) "%d:%02d:%02d".format(h, m, sec) else "%d:%02d".format(m, sec)
}

@Composable
fun DetailsScreen(app: AppState, screen: Screen.Details) {
    val p = remember(screen) { app.provider(screen.source) }
    val item = screen.item
    val series = item.media == Media.SERIES
    var info by remember { mutableStateOf(screen.info ?: Details(plot = item.plot, year = item.year, rating = item.rating, poster = item.image)) }
    var seasons by remember { mutableStateOf(screen.seasons) }
    var error by remember { mutableStateOf<String?>(null) }
    var season by remember { mutableIntStateOf(screen.season.coerceAtLeast(0)) }
    val tick = 0
    val scope = androidx.compose.runtime.rememberCoroutineScope()
    val playFocus = remember { FocusRequester() }
    val epFocus = remember { HashMap<String, FocusRequester>() }
    val episodes = rememberLazyListState()

    fun load() {
        error = null
        scope.launch {
            if (screen.info == null) launch {
                runCatching { withContext(Dispatchers.IO) { p.details(item) } }.getOrNull()?.let { d ->
                    info = d.copy(poster = d.poster.ifEmpty { item.image }, plot = d.plot.ifEmpty { item.plot })
                    screen.info = info
                }
            }
            if (series && screen.seasons == null) {
                seasons = null
                try {
                    val list = withContext(Dispatchers.IO) { p.seasons(item) }.filter { it.episodes.isNotEmpty() }
                    val last = app.lastEpisode(item.id)
                    season = list.indexOfFirst { s -> s.episodes.any { it.id == last } }.coerceAtLeast(0)
                    seasons = list
                    screen.seasons = list
                    screen.season = season
                } catch (e: Exception) {
                    error = e.message ?: "The server did not answer"
                }
            }
        }
    }
    LaunchedEffect(Unit) {
        load()
        if (!series) {
            delay(40)
            runCatching { playFocus.requestFocus() }
        }
    }

    val bg = info.backdrop.ifEmpty { info.poster }
    Box(Modifier.fillMaxSize()) {
        if (bg.isNotEmpty()) Picture(bg, "", Modifier.fillMaxSize().alpha(0.38f))
        Box(Modifier.fillMaxSize().background(Gold.side))
        Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Color.Transparent, Color.Transparent, Gold.bg))))
        Column(Modifier.fillMaxSize().padding(start = 32.dp, end = 32.dp, top = 36.dp, bottom = 20.dp)) {
            Row(Modifier.padding(horizontal = 16.dp)) {
                Box(Modifier.width(if (series) 124.dp else 168.dp).height(if (series) 186.dp else 252.dp).clip(RoundedCornerShape(14.dp))) {
                    Picture(info.poster, item.title, Modifier.fillMaxSize())
                }
                Spacer(Modifier.width(28.dp))
                Column(Modifier.weight(1f)) {
                    Text(if (series) "SERIES" else "MOVIE", style = MaterialTheme.typography.labelSmall, color = Gold.gold)
                    Spacer(Modifier.height(4.dp))
                    Text(item.title, style = MaterialTheme.typography.displaySmall, color = Gold.text, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    Spacer(Modifier.height(10.dp))
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        if (info.year.isNotEmpty()) Chip(info.year, Gold.text)
                        if (info.rating.isNotEmpty()) Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Ic.star, null, Modifier.size(15.dp), tint = Gold.gold)
                            Spacer(Modifier.width(4.dp))
                            Text(info.rating.take(3), style = MaterialTheme.typography.labelLarge, color = Gold.text)
                        }
                        if (info.runtime.isNotEmpty()) Text(info.runtime, style = MaterialTheme.typography.labelLarge, color = Gold.dim)
                        if (info.genres.isNotEmpty()) Text(info.genres, style = MaterialTheme.typography.labelMedium, color = Gold.dim, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                    if (info.plot.isNotEmpty()) {
                        Spacer(Modifier.height(12.dp))
                        Text(info.plot, style = MaterialTheme.typography.bodyMedium, color = Gold.text.copy(alpha = 0.82f), maxLines = if (series) 3 else 5, overflow = TextOverflow.Ellipsis, modifier = Modifier.fillMaxWidth(0.85f))
                    }
                    if (!series) {
                        Spacer(Modifier.height(22.dp))
                        val pos = remember(tick) { app.position(item.id) }
                        Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                            GoldButton(if (pos > 0) "Resume  ${clock(pos)}" else "Play", Ic.play, Modifier.focusRequester(playFocus)) {
                                app.go(Screen.Player(screen.source, listOf(item), 0, live = false, start = pos))
                            }
                            if (pos > 0) GoldButton("From the start", Ic.retry, primary = false) {
                                app.go(Screen.Player(screen.source, listOf(item), 0, live = false))
                            }
                        }
                    }
                }
            }
            if (series) {
                Spacer(Modifier.height(16.dp))
                val list = seasons
                when {
                    error != null -> Problem(error!!, Modifier.fillMaxWidth().weight(1f)) { load() }
                    list == null -> Loading(Modifier.fillMaxWidth().weight(1f))
                    list.isEmpty() -> Empty("No episodes yet", Modifier.fillMaxWidth().weight(1f))
                    else -> {
                        LazyRow(horizontalArrangement = Arrangement.spacedBy(10.dp), contentPadding = PaddingValues(horizontal = 16.dp, vertical = 6.dp)) {
                            itemsIndexed(list, key = { i, s -> s.id + i }) { i, s ->
                                Tile(onClick = {
                                    season = i
                                    screen.season = i
                                }, modifier = Modifier.height(40.dp), shape = RoundedCornerShape(50), selected = i == season, scale = 1.06f) { focused ->
                                    Box(Modifier.padding(horizontal = 18.dp).fillMaxHeight(), contentAlignment = Alignment.Center) {
                                        Text(s.title.ifEmpty { "Season ${s.number}" }, style = MaterialTheme.typography.labelLarge, color = if (i == season || focused) Gold.text else Gold.dim)
                                    }
                                }
                            }
                        }
                        Spacer(Modifier.height(10.dp))
                        val eps = list[season.coerceIn(0, list.lastIndex)].episodes
                        val last = remember(tick) { app.lastEpisode(item.id) }
                        LazyRow(state = episodes, horizontalArrangement = Arrangement.spacedBy(14.dp), contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp), modifier = Modifier.padding(start = 0.dp)) {
                            itemsIndexed(eps, key = { _, e -> e.id }) { i, e ->
                                val pos = remember(tick, e.id) { app.position(e.id) }
                                Tile(
                                    onClick = {
                                        app.rememberEpisode(item.id, e.id)
                                        app.go(Screen.Player(screen.source, eps, i, live = false, start = pos, series = item))
                                    },
                                    modifier = Modifier.width(220.dp).height(128.dp).focusRequester(epFocus.getOrPut(e.id) { FocusRequester() }),
                                    shape = RoundedCornerShape(12.dp), scale = 1.06f,
                                ) { focused ->
                                    Box(Modifier.fillMaxSize()) {
                                        if (e.image.isNotEmpty() && e.image != item.image) Picture(e.image, e.title, Modifier.fillMaxSize().alpha(0.55f))
                                        Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Color.Transparent, Color(0xCC000000)))))
                                        Column(Modifier.align(Alignment.BottomStart).padding(12.dp)) {
                                            Text("EPISODE ${e.number}", style = MaterialTheme.typography.labelSmall, color = Gold.gold)
                                            Text(e.title, style = MaterialTheme.typography.titleSmall, color = Gold.text, maxLines = 2, overflow = TextOverflow.Ellipsis)
                                        }
                                        if (e.id == last) Box(Modifier.padding(10.dp).align(Alignment.TopEnd)) { Chip("Last watched") }
                                        if (focused) Icon(Ic.play, null, Modifier.align(Alignment.TopStart).padding(10.dp).size(22.dp), tint = Gold.gold)
                                        if (pos > 0) Box(Modifier.align(Alignment.BottomStart).fillMaxWidth().height(3.dp).background(Gold.gold.copy(alpha = 0.8f)))
                                    }
                                }
                            }
                        }
                        LaunchedEffect(season, list) {
                            delay(40)
                            val target = eps.indexOfFirst { it.id == last }.coerceAtLeast(0)
                            runCatching {
                                episodes.scrollToItem(target)
                                epFocus.getOrPut(eps[target].id) { FocusRequester() }.requestFocus()
                            }
                        }
                    }
                }
            }
        }
    }
}
