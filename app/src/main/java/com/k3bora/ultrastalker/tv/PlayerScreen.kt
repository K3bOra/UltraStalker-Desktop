package com.k3bora.ultrastalker.tv

import android.net.Uri
import android.view.KeyEvent as AKey
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.foundation.background
import androidx.compose.foundation.focusable
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.nativeKeyCode
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onKeyEvent
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.tv.material3.Icon
import androidx.tv.material3.MaterialTheme
import androidx.tv.material3.Text
import com.k3bora.ultrastalker.core.Item
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.videolan.libvlc.MediaPlayer
import org.videolan.libvlc.util.VLCVideoLayout
import org.videolan.libvlc.Media as VlcMedia

private enum class Phase { OPENING, PLAYING, PAUSED, ERROR }
private enum class Panel { NONE, CONTROLS, CHANNELS, AUDIO, SUBTITLES, PICTURE }

private val SCALES = listOf(
    MediaPlayer.ScaleType.SURFACE_BEST_FIT to "Fit",
    MediaPlayer.ScaleType.SURFACE_FILL to "Fill the screen",
    MediaPlayer.ScaleType.SURFACE_16_9 to "16:9",
    MediaPlayer.ScaleType.SURFACE_4_3 to "4:3",
    MediaPlayer.ScaleType.SURFACE_ORIGINAL to "Original size",
)

@Composable
fun PlayerScreen(app: AppState, screen: Screen.Player) {
    val p = remember(screen) { app.provider(screen.source) }
    val live = screen.live
    val items = screen.items
    var index by remember { mutableIntStateOf(screen.index) }
    val item = items[index]
    var phase by remember { mutableStateOf(Phase.OPENING) }
    var buffering by remember { mutableFloatStateOf(0f) }
    var problem by remember { mutableStateOf("") }
    var time by remember { mutableLongStateOf(0L) }
    var length by remember { mutableLongStateOf(0L) }
    var panel by remember { mutableStateOf(Panel.NONE) }
    var banner by remember { mutableIntStateOf(1) } // >0: show the info banner (a new value restarts its timer)
    var activity by remember { mutableIntStateOf(0) }
    var digits by remember { mutableStateOf("") }
    var scale by remember { mutableIntStateOf(0) }
    var seekTo by remember { mutableLongStateOf(-1L) }
    val scope = rememberCoroutineScope()
    val root = remember { FocusRequester() }
    var openJob by remember { mutableStateOf<Job?>(null) }
    var url by remember { mutableStateOf("") }
    var start = remember { screen.start }

    val player = remember { MediaPlayer(app.vlc) }

    fun savePosition() {
        if (live) return
        val l = player.length
        val t = player.time
        if (l <= 0) return
        app.rememberPosition(item.id, if (t > 30_000 && t < l - 90_000) t else 0)
    }

    fun open(fresh: Boolean = false) {
        openJob?.cancel()
        phase = Phase.OPENING
        buffering = 0f
        problem = ""
        time = 0
        length = 0
        banner++
        val it = items[index]
        openJob = scope.launch {
            val stream = try {
                withContext(Dispatchers.IO) { app.streamFor(p, it) }
            } catch (e: Exception) {
                phase = Phase.ERROR
                problem = e.message ?: "The server did not give a stream"
                return@launch
            }
            url = stream.url
            val target = if (fresh && stream.url.startsWith("http://127.0.0.1")) stream.url + "?fresh=1" else stream.url
            val m = VlcMedia(app.vlc, Uri.parse(target))
            m.setHWDecoderEnabled(true, false)
            m.addOption(":network-caching=" + if (live) 2000 else 3000)
            if (stream.userAgent.isNotEmpty()) m.addOption(":http-user-agent=" + stream.userAgent)
            if (start > 0) m.addOption(":start-time=" + start / 1000)
            start = 0
            player.media = m
            m.release()
            player.play()
            if (screen.series != null) app.rememberEpisode(screen.series.id, it.id)
        }
    }

    fun go(to: Int) {
        if (to !in items.indices || to == index) return
        savePosition()
        index = to
        open()
    }

    fun zap(step: Int) {
        if (items.size < 2) return
        go((index + step + items.size) % items.size)
    }

    fun seek(by: Long) {
        if (live || length <= 0) return
        val base = if (seekTo >= 0) seekTo else player.time
        val t = (base + by).coerceIn(0, (length - 2000).coerceAtLeast(0))
        seekTo = t
        time = t
        banner++
    }

    fun togglePause() {
        if (phase == Phase.ERROR) return open(fresh = true)
        if (player.isPlaying) player.pause() else player.play()
        banner++
    }

    fun close(p: Panel = Panel.NONE) {
        panel = p
        if (p == Panel.NONE) scope.launch {
            delay(30)
            runCatching { root.requestFocus() }
        }
    }

    DisposableEffect(Unit) {
        player.setEventListener { e ->
            when (e.type) {
                MediaPlayer.Event.Playing -> {
                    phase = Phase.PLAYING
                    player.videoScale = SCALES[scale].first
                }
                MediaPlayer.Event.Paused -> phase = Phase.PAUSED
                MediaPlayer.Event.Buffering -> buffering = e.buffering
                MediaPlayer.Event.TimeChanged -> {
                    if (seekTo < 0) time = e.timeChanged
                    if (phase == Phase.OPENING && e.timeChanged > 0) phase = Phase.PLAYING
                }
                MediaPlayer.Event.LengthChanged -> length = e.lengthChanged
                MediaPlayer.Event.EncounteredError -> {
                    phase = Phase.ERROR
                    problem = "This stream did not open. The server may be busy or the link ended."
                }
                MediaPlayer.Event.EndReached -> {
                    if (live) {
                        phase = Phase.ERROR
                        problem = "The channel stopped sending."
                    } else {
                        app.rememberPosition(items[index].id, 0)
                        if (index < items.lastIndex) {
                            app.toast.value = "Next: " + items[index + 1].title
                            index++
                            open()
                        } else app.back()
                    }
                }
            }
        }
        open()
        onDispose {
            savePosition()
            player.setEventListener(null)
            player.stop()
            player.detachViews()
            player.release()
        }
    }

    // seeking waits a moment so several presses become one jump
    LaunchedEffect(seekTo) {
        if (seekTo < 0) return@LaunchedEffect
        delay(550)
        player.time = seekTo
        seekTo = -1
    }
    // the position is kept while watching
    LaunchedEffect(index) {
        while (!live) {
            delay(10_000)
            savePosition()
        }
    }
    // number keys: the channel with that number
    LaunchedEffect(digits) {
        if (digits.isEmpty()) return@LaunchedEffect
        delay(1600)
        val n = digits
        digits = ""
        val at = items.indexOfFirst { it.number == n }.takeIf { it >= 0 } ?: n.toIntOrNull()?.minus(1)?.takeIf { it in items.indices }
        if (at != null) go(at) else app.toast.value = "No channel $n in this list"
    }
    // controls hide by themselves
    LaunchedEffect(panel, activity) {
        if (panel == Panel.CONTROLS) {
            delay(6000)
            close()
        }
    }
    LaunchedEffect(Unit) { runCatching { root.requestFocus() } }

    BackHandler(enabled = panel != Panel.NONE) { close() }

    Box(
        Modifier.fillMaxSize().background(Color.Black)
            .onPreviewKeyEvent { ev ->
                if (ev.type != KeyEventType.KeyDown) return@onPreviewKeyEvent false
                activity++
                when (ev.key.nativeKeyCode) {
                    AKey.KEYCODE_MEDIA_PLAY_PAUSE -> togglePause().let { true }
                    AKey.KEYCODE_MEDIA_PLAY -> player.play().let { true }
                    AKey.KEYCODE_MEDIA_PAUSE -> player.pause().let { true }
                    AKey.KEYCODE_MEDIA_STOP -> app.back().let { true }
                    AKey.KEYCODE_MEDIA_FAST_FORWARD -> seek(30_000).let { true }
                    AKey.KEYCODE_MEDIA_REWIND -> seek(-30_000).let { true }
                    AKey.KEYCODE_MEDIA_NEXT -> (if (live) zap(1) else go(index + 1)).let { true }
                    AKey.KEYCODE_MEDIA_PREVIOUS -> (if (live) zap(-1) else go(index - 1)).let { true }
                    AKey.KEYCODE_CHANNEL_UP -> (if (live) zap(1) else go(index + 1)).let { true }
                    AKey.KEYCODE_CHANNEL_DOWN -> (if (live) zap(-1) else go(index - 1)).let { true }
                    else -> false
                }
            }
            .focusRequester(root)
            .onKeyEvent { ev ->
                if (ev.type != KeyEventType.KeyDown || panel != Panel.NONE) return@onKeyEvent false
                val code = ev.key.nativeKeyCode
                val repeat = ev.nativeKeyEvent.repeatCount
                when {
                    code in AKey.KEYCODE_0..AKey.KEYCODE_9 && live -> {
                        if (digits.length < 5) digits += (code - AKey.KEYCODE_0).toString()
                        true
                    }
                    code == AKey.KEYCODE_DPAD_CENTER || code == AKey.KEYCODE_ENTER || code == AKey.KEYCODE_NUMPAD_ENTER -> {
                        panel = when {
                            phase == Phase.ERROR -> open(fresh = true).let { Panel.NONE }
                            live -> Panel.CHANNELS
                            else -> Panel.CONTROLS
                        }
                        true
                    }
                    code == AKey.KEYCODE_DPAD_UP -> {
                        if (live) zap(-1) else panel = Panel.CONTROLS
                        true
                    }
                    code == AKey.KEYCODE_DPAD_DOWN -> {
                        if (live) zap(1) else panel = Panel.CONTROLS
                        true
                    }
                    code == AKey.KEYCODE_DPAD_LEFT -> {
                        if (live) panel = Panel.CHANNELS else seek(if (repeat > 6) -60_000 else -10_000)
                        true
                    }
                    code == AKey.KEYCODE_DPAD_RIGHT -> {
                        if (live) panel = Panel.CONTROLS else seek(if (repeat > 6) 60_000 else 10_000)
                        true
                    }
                    code == AKey.KEYCODE_MENU || code == AKey.KEYCODE_INFO || code == AKey.KEYCODE_GUIDE -> {
                        panel = if (live && code == AKey.KEYCODE_GUIDE) Panel.CHANNELS else Panel.CONTROLS
                        true
                    }
                    else -> false
                }
            }
            .focusable(),
    ) {
        AndroidView(
            factory = { ctx ->
                VLCVideoLayout(ctx).also { v ->
                    v.keepScreenOn = true
                    player.attachViews(v, null, true, false)
                }
            },
            modifier = Modifier.fillMaxSize(),
        )

        // waiting / problem
        if (phase == Phase.OPENING || (phase == Phase.PLAYING && buffering in 0.1f..99f && !player.isPlaying)) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Spinner(52.dp)
                    if (buffering > 0f && buffering < 100f) {
                        Spacer(Modifier.height(12.dp))
                        Text("${buffering.toInt()}%", color = Gold.dim, style = MaterialTheme.typography.labelLarge)
                    }
                }
            }
        }
        if (phase == Phase.ERROR) {
            Box(Modifier.fillMaxSize().background(Color(0xAA000000)), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.width(520.dp)) {
                    Text("Can't play this right now", style = MaterialTheme.typography.headlineSmall, color = Gold.text)
                    Spacer(Modifier.height(8.dp))
                    Text(problem, style = MaterialTheme.typography.bodyMedium, color = Gold.dim)
                    Spacer(Modifier.height(18.dp))
                    Text(
                        if (live) "OK: try again  ·  ▲ ▼: another channel" else "OK: try again  ·  Back: return",
                        style = MaterialTheme.typography.labelMedium, color = Gold.gold,
                    )
                }
            }
        }

        // the banner: what is playing
        val showBanner = remember { mutableStateOf(true) }
        LaunchedEffect(banner, phase) {
            showBanner.value = true
            delay(if (phase == Phase.PLAYING) 4000 else 60_000)
            showBanner.value = false
        }
        AnimatedVisibility(
            visible = panel == Panel.CONTROLS || (showBanner.value && panel == Panel.NONE),
            enter = fadeIn(), exit = fadeOut(), modifier = Modifier.align(Alignment.BottomCenter),
        ) {
            Bar(
                item = item, live = live, phase = phase, time = time, length = length,
                controls = panel == Panel.CONTROLS, hasNext = !live && index < items.lastIndex,
                onPlay = { togglePause() }, onBack10 = { seek(-10_000) }, onFwd10 = { seek(10_000) },
                onAudio = { panel = Panel.AUDIO }, onSubs = { panel = Panel.SUBTITLES }, onPicture = { panel = Panel.PICTURE },
                onNext = { go(index + 1) }, onChannels = { panel = Panel.CHANNELS }, onRetry = { open(fresh = true) },
            )
        }

        if (digits.isNotEmpty()) {
            Box(Modifier.align(Alignment.TopEnd).padding(36.dp).clip(RoundedCornerShape(14.dp)).background(Color(0xDD000000)).padding(horizontal = 26.dp, vertical = 12.dp)) {
                Text(digits, color = Gold.gold, fontSize = 44.sp, style = MaterialTheme.typography.displaySmall)
            }
        }

        AnimatedVisibility(panel == Panel.CHANNELS, enter = slideInHorizontally { -it } + fadeIn(), exit = slideOutHorizontally { -it } + fadeOut()) {
            ChannelPanel(items, index) { i ->
                close()
                go(i)
            }
        }
        val tracks = when (panel) {
            Panel.AUDIO -> Triple("Audio", player.audioTracks?.map { it.id to it.name }.orEmpty(), player.audioTrack)
            Panel.SUBTITLES -> Triple("Subtitles", player.spuTracks?.map { it.id to it.name }.orEmpty(), player.spuTrack)
            Panel.PICTURE -> Triple("Picture", SCALES.mapIndexed { i, s -> i to s.second }, scale)
            else -> null
        }
        if (tracks != null) {
            OptionPanel(tracks.first, tracks.second, tracks.third) { id ->
                when (panel) {
                    Panel.AUDIO -> player.audioTrack = id
                    Panel.SUBTITLES -> player.spuTrack = id
                    Panel.PICTURE -> {
                        scale = id
                        player.videoScale = SCALES[id].first
                    }
                    else -> {}
                }
                close()
            }
        }
    }
}

@Composable
private fun Bar(
    item: Item, live: Boolean, phase: Phase, time: Long, length: Long, controls: Boolean, hasNext: Boolean,
    onPlay: () -> Unit, onBack10: () -> Unit, onFwd10: () -> Unit, onAudio: () -> Unit, onSubs: () -> Unit, onPicture: () -> Unit,
    onNext: () -> Unit, onChannels: () -> Unit, onRetry: () -> Unit,
) {
    val first = remember { FocusRequester() }
    Column(
        Modifier.fillMaxWidth().background(Brush.verticalGradient(listOf(Color.Transparent, Color(0xE6000000), Color(0xF2000000))))
            .padding(start = 48.dp, end = 48.dp, top = 70.dp, bottom = 30.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (live) {
                Box(Modifier.width(84.dp).height(52.dp).clip(RoundedCornerShape(10.dp)).background(Color(0x1AFFFFFF)), contentAlignment = Alignment.Center) {
                    Picture(item.image, item.title, Modifier.fillMaxSize().padding(6.dp), ContentScale.Fit, letters = 20.dp)
                }
                Spacer(Modifier.width(16.dp))
            }
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (live) {
                        Chip("LIVE", Gold.red)
                        Spacer(Modifier.width(10.dp))
                        if (item.number.isNotEmpty()) {
                            Text(item.number, style = MaterialTheme.typography.titleMedium, color = Gold.gold)
                            Spacer(Modifier.width(10.dp))
                        }
                    }
                    Text(item.title, style = MaterialTheme.typography.headlineSmall, color = Gold.text, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                if (phase == Phase.PAUSED) Text("Paused", style = MaterialTheme.typography.labelMedium, color = Gold.gold)
            }
        }
        if (!live && length > 0) {
            Spacer(Modifier.height(14.dp))
            val f = (time.toFloat() / length).coerceIn(0f, 1f)
            Box(Modifier.fillMaxWidth().height(5.dp).clip(RoundedCornerShape(3.dp)).background(Color(0x33FFFFFF))) {
                Box(Modifier.fillMaxWidth(f).fillMaxHeight().background(Gold.shine))
            }
            Spacer(Modifier.height(6.dp))
            Row {
                Text(clock(time), style = MaterialTheme.typography.labelMedium, color = Gold.text)
                Spacer(Modifier.weight(1f))
                Text("-" + clock(length - time), style = MaterialTheme.typography.labelMedium, color = Gold.dim)
            }
        }
        if (controls) {
            Spacer(Modifier.height(14.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                if (phase == Phase.ERROR) GoldButton("Try again", Ic.retry, Modifier.focusRequester(first), onClick = onRetry)
                else if (!live) {
                    GoldButton("", Ic.rewind, primary = false, onClick = onBack10)
                    GoldButton("", if (phase == Phase.PAUSED) Ic.play else Ic.pause, Modifier.focusRequester(first), onClick = onPlay)
                    GoldButton("", Ic.forward, primary = false, onClick = onFwd10)
                } else GoldButton("Channels", Ic.list, Modifier.focusRequester(first), onClick = onChannels)
                Spacer(Modifier.width(10.dp))
                GoldButton("Audio", Ic.audio, primary = false, onClick = onAudio)
                GoldButton("Subtitles", Ic.subtitles, primary = false, onClick = onSubs)
                GoldButton("Picture", Ic.aspect, primary = false, onClick = onPicture)
                if (hasNext) GoldButton("Next episode", Ic.next, primary = false, onClick = onNext)
            }
            LaunchedEffect(Unit) { runCatching { first.requestFocus() } }
        }
    }
}

@Composable
private fun ChannelPanel(items: List<Item>, current: Int, onPick: (Int) -> Unit) {
    val list = rememberLazyListState((current - 4).coerceAtLeast(0))
    val fr = remember { FocusRequester() }
    Column(
        Modifier.width(400.dp).fillMaxHeight().background(Brush.horizontalGradient(listOf(Color(0xF7060608), Color(0xE6060608), Color(0x00060608))))
            .padding(start = 26.dp, top = 26.dp, end = 30.dp),
    ) {
        Text("Channels", style = MaterialTheme.typography.titleLarge, color = Gold.text)
        Text("${items.size} in this list", style = MaterialTheme.typography.bodySmall, color = Gold.dim)
        Spacer(Modifier.height(12.dp))
        LazyColumn(state = list, verticalArrangement = Arrangement.spacedBy(5.dp), contentPadding = PaddingValues(bottom = 40.dp, end = 4.dp, start = 2.dp, top = 2.dp)) {
            itemsIndexed(items, key = { _, it -> it.id }) { i, it ->
                Tile(
                    onClick = { onPick(i) },
                    modifier = Modifier.fillMaxWidth().height(50.dp).then(if (i == current) Modifier.focusRequester(fr) else Modifier),
                    shape = RoundedCornerShape(10.dp), selected = i == current, scale = 1.02f,
                ) { focused ->
                    Row(Modifier.fillMaxSize().padding(horizontal = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(it.number.ifEmpty { "${i + 1}" }, style = MaterialTheme.typography.labelMedium, color = if (focused) Gold.gold else Gold.dim, modifier = Modifier.width(40.dp), maxLines = 1)
                        Box(Modifier.width(48.dp).height(32.dp), contentAlignment = Alignment.Center) {
                            Picture(it.image, it.title, Modifier.fillMaxSize(), ContentScale.Fit, letters = 14.dp)
                        }
                        Spacer(Modifier.width(10.dp))
                        Text(it.title, style = MaterialTheme.typography.titleSmall, color = Gold.text, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                        if (i == current) Icon(Ic.play, null, Modifier.size(16.dp), tint = Gold.gold)
                    }
                }
            }
        }
    }
    LaunchedEffect(Unit) {
        delay(30)
        runCatching { fr.requestFocus() }
    }
}

@Composable
private fun OptionPanel(title: String, options: List<Pair<Int, String>>, current: Int, onPick: (Int) -> Unit) {
    val fr = remember { FocusRequester() }
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.CenterEnd) {
        Column(
            Modifier.width(340.dp).fillMaxHeight().background(Brush.horizontalGradient(listOf(Color(0x00060608), Color(0xE6060608), Color(0xF7060608))))
                .padding(start = 40.dp, top = 40.dp, end = 30.dp),
        ) {
            Text(title, style = MaterialTheme.typography.titleLarge, color = Gold.text)
            Spacer(Modifier.height(14.dp))
            if (options.isEmpty()) Text("Nothing to choose here", style = MaterialTheme.typography.bodyMedium, color = Gold.dim)
            val at = options.indexOfFirst { it.first == current }.coerceAtLeast(0)
            LazyColumn(verticalArrangement = Arrangement.spacedBy(6.dp), contentPadding = PaddingValues(2.dp)) {
                itemsIndexed(options) { i, (id, name) ->
                    Tile(
                        onClick = { onPick(id) },
                        modifier = Modifier.fillMaxWidth().height(46.dp).then(if (i == at) Modifier.focusRequester(fr) else Modifier),
                        shape = RoundedCornerShape(10.dp), selected = id == current, scale = 1.03f,
                    ) {
                        Row(Modifier.fillMaxSize().padding(horizontal = 14.dp), verticalAlignment = Alignment.CenterVertically) {
                            Box(Modifier.size(8.dp).clip(RoundedCornerShape(4.dp)).background(if (id == current) Gold.gold else Color.Transparent))
                            Spacer(Modifier.width(10.dp))
                            Text(name.ifBlank { "Track ${i + 1}" }, style = MaterialTheme.typography.titleSmall, color = Gold.text, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                    }
                }
            }
        }
    }
    LaunchedEffect(Unit) {
        delay(30)
        runCatching { fr.requestFocus() }
    }
}
