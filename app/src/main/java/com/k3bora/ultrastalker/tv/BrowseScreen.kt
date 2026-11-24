package com.k3bora.ultrastalker.tv

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyGridState
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.itemsIndexed
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.tv.material3.Icon
import androidx.tv.material3.MaterialTheme
import androidx.tv.material3.Text
import com.k3bora.ultrastalker.core.Category
import com.k3bora.ultrastalker.core.Item
import com.k3bora.ultrastalker.core.Media
import com.k3bora.ultrastalker.core.Provider
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/* What the browse screen keeps while you open a movie or a channel and come back. */
class BrowseState {
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    var media by mutableStateOf<Media?>(null)
    var cats by mutableStateOf<List<Category>>(emptyList())
    var catsLoading by mutableStateOf(false)
    var catsError by mutableStateOf<String?>(null)
    var category by mutableStateOf<Category?>(null)
    val items = mutableStateListOf<Item>()
    var total by mutableStateOf(0)
    private var page = 0
    var hasNext by mutableStateOf(false)
    var loading by mutableStateOf(false)
    var error by mutableStateOf<String?>(null)
    var catList = LazyListState()
    var itemList = LazyListState()
    var grid = LazyGridState()
    var focusCat = 0
    var focusItem = -1
    var inItems = false
    var wantItems by mutableStateOf(false)
    private var itemsJob: Job? = null
    private val catCache = HashMap<Media, List<Category>>()
    private val lastCat = HashMap<Media, Category>()

    fun close() = scope.cancel()

    fun openMedia(p: Provider, m: Media, app: AppState) {
        if (media == m && cats.isNotEmpty()) return
        media = m
        app.rememberMedia(p.source.key, m)
        cats = emptyList()
        catsError = null
        category = null
        clearItems()
        catList = LazyListState()
        focusCat = 0
        val cached = catCache[m]
        if (cached != null) {
            cats = cached
            select(p, lastCat[m] ?: cached.first())
            return
        }
        catsLoading = true
        scope.launch {
            try {
                val list = withContext(Dispatchers.IO) { p.categories(m) }
                if (media != m) return@launch
                val all = if (list.any { it.id == "*" }) list else listOf(Category("*", "All")) + list
                catCache[m] = all
                cats = all
                if (all.isNotEmpty()) select(p, all.first())
            } catch (e: Exception) {
                if (media == m) catsError = e.message ?: "The server did not answer"
            } finally {
                if (media == m) catsLoading = false
            }
        }
    }

    private fun clearItems() {
        itemsJob?.cancel()
        items.clear()
        page = 0
        total = 0
        hasNext = false
        loading = false
        error = null
        itemList = LazyListState()
        grid = LazyGridState()
        focusItem = -1
    }

    fun select(p: Provider, c: Category) {
        if (category?.id == c.id && (items.isNotEmpty() || loading)) return
        category = c
        media?.let { lastCat[it] = c }
        clearItems()
        more(p)
    }

    fun more(p: Provider) {
        val c = category ?: return
        val m = media ?: return
        if (loading || (page > 0 && !hasNext) || error != null) return
        loading = true
        itemsJob = scope.launch {
            try {
                val pg = withContext(Dispatchers.IO) { p.page(m, c.id, page + 1) }
                if (category?.id != c.id || media != m) return@launch
                val have = items.map { it.id }.toHashSet()
                items.addAll(pg.items.filter { have.add(it.id) })
                page++
                hasNext = pg.hasNext && page < 400
                total = maxOf(pg.total, items.size)
            } catch (e: Exception) {
                if (category?.id == c.id) error = e.message ?: "The server did not answer"
            } finally {
                if (category?.id == c.id && media == m) loading = false
            }
        }
    }

    fun retry(p: Provider) {
        error = null
        more(p)
    }
}

@Composable
fun BrowseScreen(app: AppState, screen: Screen.Browse) {
    val s = screen.state
    val p = remember(screen) { app.provider(screen.source) }
    val catFocus = remember { HashMap<Int, FocusRequester>() }
    val itemFocus = remember { HashMap<Int, FocusRequester>() }
    fun fr(map: HashMap<Int, FocusRequester>, i: Int) = map.getOrPut(i) { FocusRequester() }
    val tabFocus = remember { FocusRequester() }
    var pending by remember { mutableStateOf<Category?>(null) }

    LaunchedEffect(Unit) {
        if (s.media == null) s.openMedia(p, app.lastMedia(p.source.key), app)
    }
    // a category is opened when the remote rests on it for a moment
    LaunchedEffect(pending) {
        val c = pending ?: return@LaunchedEffect
        delay(420)
        s.select(p, c)
    }
    // back from a movie or a channel: the same place again
    LaunchedEffect(Unit) {
        delay(30)
        runCatching {
            when {
                s.inItems && s.focusItem >= 0 -> fr(itemFocus, s.focusItem).requestFocus()
                s.cats.isNotEmpty() -> fr(catFocus, s.focusCat).requestFocus()
                else -> tabFocus.requestFocus()
            }
        }
    }
    LaunchedEffect(s.cats) {
        if (s.cats.isNotEmpty() && !s.inItems) {
            delay(30)
            runCatching { fr(catFocus, s.focusCat).requestFocus() }
        }
    }
    LaunchedEffect(s.wantItems, s.items.size) {
        if (s.wantItems && s.items.isNotEmpty()) {
            s.wantItems = false
            delay(20)
            runCatching { fr(itemFocus, 0).requestFocus() }
        }
    }

    Box(Modifier.fillMaxSize()) {
        Backdrop()
        Column(Modifier.fillMaxSize().padding(start = 32.dp, end = 32.dp, top = 20.dp)) {
            // header: the server and the three kinds
            Row(Modifier.fillMaxWidth().height(52.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(p.source.kindLabel.uppercase(), style = MaterialTheme.typography.labelSmall, color = Gold.gold)
                    Text(p.source.title(app.sources.indexOfFirst { it.key == p.source.key }), style = MaterialTheme.typography.titleLarge, color = Gold.text, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    for (m in Media.entries) {
                        val on = s.media == m
                        Tile(
                            onClick = {
                                s.inItems = false
                                s.openMedia(p, m, app)
                            },
                            modifier = Modifier.height(42.dp).then(if (on) Modifier.focusRequester(tabFocus) else Modifier),
                            shape = RoundedCornerShape(50), selected = on, scale = 1.06f,
                        ) { focused ->
                            Row(Modifier.padding(horizontal = 18.dp).fillMaxHeight(), verticalAlignment = Alignment.CenterVertically) {
                                Icon(mediaIcon(m), null, Modifier.size(18.dp), tint = if (on || focused) Gold.gold else Gold.dim)
                                Spacer(Modifier.width(8.dp))
                                Text(mediaLabel(m), style = MaterialTheme.typography.labelLarge, color = if (on || focused) Gold.text else Gold.dim)
                            }
                        }
                    }
                }
            }
            Spacer(Modifier.height(14.dp))
            Row(Modifier.fillMaxSize()) {
                // categories
                Box(Modifier.width(236.dp).fillMaxHeight()) {
                    when {
                        s.catsLoading -> Loading(Modifier.fillMaxSize())
                        s.catsError != null -> Problem(s.catsError!!, Modifier.fillMaxSize()) {
                            val m = s.media ?: Media.LIVE
                            s.media = null
                            s.openMedia(p, m, app)
                        }
                        s.cats.isEmpty() && s.media != null -> Empty("Nothing here", Modifier.fillMaxSize())
                        else -> LazyColumn(state = s.catList, verticalArrangement = Arrangement.spacedBy(6.dp), contentPadding = PaddingValues(top = 4.dp, bottom = 40.dp, start = 4.dp, end = 10.dp)) {
                            itemsIndexed(s.cats, key = { i, c -> c.id + "|" + i }) { i, c ->
                                val on = s.category?.id == c.id
                                Tile(
                                    onClick = {
                                        pending = null
                                        s.select(p, c)
                                        s.wantItems = true
                                    },
                                    modifier = Modifier.fillMaxWidth().height(44.dp).focusRequester(fr(catFocus, i)).onFocusChanged {
                                        if (it.isFocused) {
                                            s.focusCat = i
                                            s.inItems = false
                                            if (!on) pending = c
                                        }
                                    },
                                    shape = RoundedCornerShape(10.dp), selected = on, scale = 1.03f,
                                ) { focused ->
                                    Row(Modifier.fillMaxSize().padding(horizontal = 14.dp), verticalAlignment = Alignment.CenterVertically) {
                                        Box(Modifier.width(3.dp).height(18.dp).clip(RoundedCornerShape(2.dp)).background(if (on) Gold.gold else Color.Transparent))
                                        Spacer(Modifier.width(10.dp))
                                        Text(c.title, style = MaterialTheme.typography.titleSmall, color = if (on || focused) Gold.text else Gold.dim, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                    }
                                }
                            }
                        }
                    }
                }
                Spacer(Modifier.width(14.dp))
                // items
                Column(Modifier.weight(1f).fillMaxHeight()) {
                    s.category?.let { c ->
                        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(start = 6.dp, bottom = 8.dp)) {
                            Text(c.title, style = MaterialTheme.typography.titleMedium, color = Gold.text, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            if (s.total > 0) {
                                Spacer(Modifier.width(10.dp))
                                Text(
                                    "${s.total} " + when (s.media) {
                                        Media.LIVE -> "channels"
                                        Media.MOVIES -> "movies"
                                        else -> "series"
                                    },
                                    style = MaterialTheme.typography.bodySmall, color = Gold.dim,
                                )
                            }
                            if (s.loading && s.items.isNotEmpty()) {
                                Spacer(Modifier.width(12.dp))
                                Spinner(16.dp)
                            }
                        }
                    }
                    Box(Modifier.fillMaxSize()) {
                        when {
                            s.items.isEmpty() && s.error != null -> Problem(s.error!!, Modifier.fillMaxSize(), focus = s.inItems) { s.retry(p) }
                            s.items.isEmpty() && (s.loading || s.catsLoading || s.hasNext) -> Loading(Modifier.fillMaxSize())
                            s.items.isEmpty() && s.category != null -> Empty("Nothing here", Modifier.fillMaxSize())
                            s.media == Media.LIVE -> ChannelList(app, screen, p, itemFocus)
                            else -> PosterGrid(app, screen, p, itemFocus)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun ChannelList(app: AppState, screen: Screen.Browse, p: Provider, focus: HashMap<Int, FocusRequester>) {
    val s = screen.state
    val list = s.itemList
    LaunchedEffect(list, s.items.size) {
        snapshotFlow { list.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: -1 }.distinctUntilChanged().collect { last ->
            if (last >= s.items.size - 15) s.more(p)
        }
    }
    LazyColumn(state = list, verticalArrangement = Arrangement.spacedBy(6.dp), contentPadding = PaddingValues(top = 6.dp, bottom = 60.dp, start = 14.dp, end = 14.dp)) {
        itemsIndexed(s.items, key = { _, it -> it.id }) { i, item ->
            Tile(
                onClick = { app.go(Screen.Player(p.source, s.items.toList(), i, live = true)) },
                modifier = Modifier.fillMaxWidth().height(58.dp).focusRequester(focus.getOrPut(i) { FocusRequester() }).onFocusChanged {
                    if (it.isFocused) {
                        s.focusItem = i
                        s.inItems = true
                    }
                },
                shape = RoundedCornerShape(12.dp), scale = 1.02f,
            ) { focused ->
                Row(Modifier.fillMaxSize().padding(horizontal = 14.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(item.number.ifEmpty { "${i + 1}" }, style = MaterialTheme.typography.labelLarge, color = if (focused) Gold.gold else Gold.dim, modifier = Modifier.width(46.dp), maxLines = 1)
                    Box(Modifier.width(64.dp).height(40.dp).clip(RoundedCornerShape(8.dp)).background(Color(0x14FFFFFF)), contentAlignment = Alignment.Center) {
                        Picture(item.image, item.title, Modifier.fillMaxSize().padding(4.dp), ContentScale.Fit, letters = 18.dp)
                    }
                    Spacer(Modifier.width(14.dp))
                    Text(item.title, style = MaterialTheme.typography.titleSmall, color = Gold.text, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                    if (focused) Icon(Ic.play, null, Modifier.size(20.dp), tint = Gold.gold)
                }
            }
        }
    }
}

@Composable
private fun PosterGrid(app: AppState, screen: Screen.Browse, p: Provider, focus: HashMap<Int, FocusRequester>) {
    val s = screen.state
    val grid = s.grid
    LaunchedEffect(grid, s.items.size) {
        snapshotFlow { grid.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: -1 }.distinctUntilChanged().collect { last ->
            if (last >= s.items.size - 12) s.more(p)
        }
    }
    LazyVerticalGrid(
        state = grid, columns = GridCells.Fixed(5),
        horizontalArrangement = Arrangement.spacedBy(14.dp), verticalArrangement = Arrangement.spacedBy(16.dp),
        contentPadding = PaddingValues(top = 16.dp, bottom = 60.dp, start = 10.dp, end = 10.dp),
    ) {
        itemsIndexed(s.items, key = { _, it -> it.id }) { i, item ->
            Tile(
                onClick = { app.go(Screen.Details(p.source, item)) },
                modifier = Modifier.fillMaxWidth().focusRequester(focus.getOrPut(i) { FocusRequester() }).onFocusChanged {
                    if (it.isFocused) {
                        s.focusItem = i
                        s.inItems = true
                    }
                },
                shape = RoundedCornerShape(12.dp), scale = 1.07f,
            ) { focused ->
                Column {
                    Box(Modifier.fillMaxWidth().aspectRatio(2f / 3f)) {
                        Picture(item.image, item.title, Modifier.fillMaxSize())
                        if (item.rating.isNotEmpty()) {
                            Row(
                                Modifier.padding(6.dp).clip(RoundedCornerShape(6.dp)).background(Color(0xCC000000)).padding(horizontal = 6.dp, vertical = 2.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Icon(Ic.star, null, Modifier.size(11.dp), tint = Gold.gold)
                                Spacer(Modifier.width(3.dp))
                                Text(item.rating.take(3), style = MaterialTheme.typography.labelSmall, color = Gold.text)
                            }
                        }
                        Box(Modifier.fillMaxWidth().height(40.dp).align(Alignment.BottomCenter).background(Brush.verticalGradient(listOf(Color.Transparent, Color(0x99000000)))))
                    }
                    Text(
                        item.title, style = MaterialTheme.typography.labelMedium, color = if (focused) Gold.goldLight else Gold.text,
                        maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(horizontal = 8.dp, vertical = 8.dp),
                    )
                }
            }
        }
    }
}
